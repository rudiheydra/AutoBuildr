"""
Spec-Driven Orchestrator
========================

Orchestrates feature execution through the AgentSpec pipeline:
  Feature -> FeatureCompiler -> AgentSpec -> HarnessKernel -> AgentRun -> verdict -> Feature state sync

This module replaces the legacy prompt-based path (agent.py + parallel_orchestrator.py)
when --spec or AUTOBUILDR_MODE=spec is enabled.

The SpecOrchestrator:
- Loads pending features (dependency-aware)
- Compiles each Feature into an AgentSpec via FeatureCompiler
- Persists AgentSpec + AcceptanceSpec to the database
- Executes via HarnessKernel.execute(spec)
- Syncs verdict back to Feature.passes
- Logs evidence (DB counts, task_type distribution)

Usage:
    from api.spec_orchestrator import SpecOrchestrator

    orchestrator = SpecOrchestrator(project_dir=Path("/my/project"), session=db_session)
    orchestrator.run_loop()
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, inspect as sa_inspect
from sqlalchemy.orm import Session

from api.agentspec_models import (
    AcceptanceSpec,
    AgentEvent,
    AgentRun,
    AgentSpec,
    Artifact,
    generate_uuid,
)
from api.database import Base, Feature, create_database
from api.feature_compiler import FeatureCompiler, extract_task_type_from_category
from api.harness_kernel import HarnessKernel, commit_with_retry
from api.spec_builder import SpecBuilder, BuildResult

_logger = logging.getLogger(__name__)


# =============================================================================
# Table migration
# =============================================================================

def ensure_spec_tables(engine) -> list[str]:
    """
    Ensure all AgentSpec-related tables exist in the database.

    Runs as an additive migration — creates missing tables without
    dropping or altering existing ones.

    Args:
        engine: SQLAlchemy engine

    Returns:
        List of table names that were created (empty if all existed)
    """
    inspector = sa_inspect(engine)
    existing = set(inspector.get_table_names())

    needed = {"agent_specs", "acceptance_specs", "agent_runs", "agent_events", "artifacts"}
    missing = needed - existing

    if missing:
        _logger.info("Creating missing spec tables: %s", sorted(missing))
        # create_all is additive — it skips tables that already exist
        Base.metadata.create_all(bind=engine, tables=[
            t for t in Base.metadata.sorted_tables
            if t.name in needed
        ])
        _logger.info("Spec tables created successfully")
    else:
        _logger.info("All spec tables already exist: %s", sorted(needed))

    return sorted(missing)


# =============================================================================
# Snapshot materializer (optional visibility)
# =============================================================================

def materialize_spec(spec: AgentSpec, project_dir: Path) -> Path | None:
    """
    Write an AgentSpec as a markdown snapshot file for inspection.

    Creates .claude/agents/generated/<spec.name>.md with YAML frontmatter
    and a body summarizing objective, tool policy, and acceptance criteria.

    These files are for visibility only — not used during execution.

    Args:
        spec: The AgentSpec to materialize
        project_dir: Root project directory

    Returns:
        Path to created file, or None on error
    """
    try:
        output_dir = project_dir / ".claude" / "agents" / "generated"
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{spec.name}.md"
        filepath = output_dir / filename

        # Build YAML frontmatter
        tools = []
        if spec.tool_policy and isinstance(spec.tool_policy, dict):
            tools = spec.tool_policy.get("allowed_tools", [])

        lines = [
            "---",
            f"name: {spec.display_name}",
            f"task_type: {spec.task_type}",
            f"spec_id: {spec.id}",
            f"source_feature_id: {spec.source_feature_id}",
            f"max_turns: {spec.max_turns}",
            f"timeout_seconds: {spec.timeout_seconds}",
            f"tools: {json.dumps(tools[:10])}",  # Cap at 10 for readability
            "---",
            "",
            f"# {spec.display_name}",
            "",
            "## Objective",
            "",
            spec.objective or "(no objective)",
            "",
            "## Tool Policy",
            "",
            f"- **Allowed tools:** {len(tools)} tools",
        ]

        if spec.tool_policy and isinstance(spec.tool_policy, dict):
            forbidden = spec.tool_policy.get("forbidden_patterns", [])
            if forbidden:
                lines.append(f"- **Forbidden patterns:** {len(forbidden)} patterns")

        # Acceptance criteria summary
        if spec.acceptance_spec:
            validators = spec.acceptance_spec.validators or []
            lines += [
                "",
                "## Acceptance Criteria",
                "",
                f"- **Gate mode:** {spec.acceptance_spec.gate_mode}",
                f"- **Validators:** {len(validators)}",
            ]

        lines.append("")

        filepath.write_text("\n".join(lines), encoding="utf-8")
        _logger.debug("Materialized spec snapshot: %s", filepath)
        return filepath

    except Exception as e:
        _logger.warning("Failed to materialize spec %s: %s", spec.name, e)
        return None


# =============================================================================
# Verification output
# =============================================================================

def print_verification_summary(session: Session, project_dir: Path | None = None) -> dict[str, Any]:
    """
    Print and return database table counts and task_type distribution.

    This is the hard proof that spec mode populated the database.

    Args:
        session: SQLAlchemy session
        project_dir: Optional project dir to write summary file

    Returns:
        Dict with table counts and task_type distribution
    """
    tables = {
        "features": Feature,
        "agent_specs": AgentSpec,
        "agent_runs": AgentRun,
        "agent_events": AgentEvent,
        "acceptance_specs": AcceptanceSpec,
        "artifacts": Artifact,
    }

    counts = {}
    for name, model in tables.items():
        try:
            counts[name] = session.query(func.count(model.id)).scalar() or 0
        except Exception:
            counts[name] = -1  # Table missing

    # Task type distribution
    task_types = {}
    try:
        rows = (
            session.query(AgentSpec.task_type, func.count(AgentSpec.id))
            .group_by(AgentSpec.task_type)
            .order_by(func.count(AgentSpec.id).desc())
            .all()
        )
        task_types = {row[0]: row[1] for row in rows}
    except Exception as e:
        _logger.warning("Failed to query task_type distribution: %s", e)

    # Print summary
    print("\n" + "=" * 60)
    print("SPEC MODE VERIFICATION SUMMARY")
    print("=" * 60)
    for name, count in counts.items():
        status = "OK" if count > 0 else "EMPTY" if count == 0 else "MISSING"
        print(f"  {name:20s}: {count:6d}  [{status}]")

    print(f"\n  Task type distribution:")
    for tt, cnt in task_types.items():
        print(f"    {tt:20s}: {cnt}")
    print(f"  Distinct task types: {len(task_types)}")

    # Acceptance criteria check
    print("\n  Acceptance criteria:")
    checks = {
        "agent_specs >= 1": counts.get("agent_specs", 0) >= 1,
        "agent_runs >= 1": counts.get("agent_runs", 0) >= 1,
        "agent_events >= 1": counts.get("agent_events", 0) >= 1,
        "task_types >= 2": len(task_types) >= 2,
    }
    for check, passed in checks.items():
        print(f"    {'PASS' if passed else 'FAIL'}: {check}")
    print("=" * 60 + "\n")

    result = {"counts": counts, "task_types": task_types, "checks": checks}

    # Write to file if project_dir provided
    if project_dir:
        try:
            summary_path = project_dir / "spec_run_summary.txt"
            summary_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            _logger.info("Verification summary written to %s", summary_path)
        except Exception as e:
            _logger.warning("Failed to write summary file: %s", e)

    return result


# =============================================================================
# SpecOrchestrator
# =============================================================================

class SpecOrchestrator:
    """
    Orchestrates feature execution through the AgentSpec pipeline.

    Core loop:
        1. get_next_feature() — find ready feature (deps satisfied, not in_progress)
        2. compile_feature() — Feature → AgentSpec via FeatureCompiler
        3. persist_spec() — save AgentSpec + AcceptanceSpec to DB
        4. execute_spec() — run via HarnessKernel.execute()
        5. sync_verdict() — update Feature.passes from AgentRun.final_verdict
    """

    def __init__(
        self,
        project_dir: Path,
        session: Session,
        engine=None,
        *,
        yolo_mode: bool = False,
        materialize_agents: bool = False,
    ):
        """
        Initialize the SpecOrchestrator.

        Args:
            project_dir: Absolute path to the target project
            session: SQLAlchemy session for the project database
            engine: SQLAlchemy engine (for table migration)
            yolo_mode: Skip testing-related features
            materialize_agents: Write AgentSpec snapshots to .claude/agents/generated/
        """
        self.project_dir = Path(project_dir).resolve()
        self.session = session
        self.engine = engine
        self.yolo_mode = yolo_mode
        self.materialize_agents = materialize_agents
        self.compiler = FeatureCompiler()
        self._shutdown = False
        self._feature_attempts: dict[int, int] = {}  # feature_id -> attempt count
        self.max_retries_per_feature = 2  # max attempts before skipping

        # Initialize DSPy SpecBuilder if API key is available
        self._dspy_builder: SpecBuilder | None = None
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            try:
                self._dspy_builder = SpecBuilder(api_key=api_key, auto_initialize=True)
                _logger.info("DSPy SpecBuilder initialized — using DSPy for spec generation")
                print("[SPEC] DSPy SpecBuilder active", flush=True)
            except Exception as e:
                _logger.warning("DSPy SpecBuilder init failed, falling back to FeatureCompiler: %s", e)
                self._dspy_builder = None
        else:
            _logger.info("No API key — using FeatureCompiler (no DSPy)")

        # Validate DB path is under project dir
        db_path = self.project_dir / "features.db"
        _logger.info("Spec mode: project_dir=%s, db_path=%s", self.project_dir, db_path)
        print(f"[SPEC] project_dir={self.project_dir}", flush=True)
        print(f"[SPEC] db_path={db_path}", flush=True)

        # Ensure spec tables exist
        if engine:
            ensure_spec_tables(engine)

        # Auto-scaffold .claude/ for projects registered before this feature
        claude_dir = self.project_dir / ".claude"
        if not claude_dir.exists():
            from prompts import scaffold_claude_dir
            scaffold_claude_dir(self.project_dir)

        # Auto-enable materialize_agents when SDK executor is active
        from api.executor_config import is_sdk_executor
        if is_sdk_executor() and not self.materialize_agents:
            self.materialize_agents = True

    # -----------------------------------------------------------------
    # Feature selection
    # -----------------------------------------------------------------

    def get_next_feature(self) -> Feature | None:
        """
        Get next pending feature with all dependencies satisfied.

        Returns:
            Feature ready for execution, or None if none available.
        """
        all_features = self.session.query(Feature).all()
        passing_ids = {f.id for f in all_features if f.passes}

        ready = []
        for f in all_features:
            if f.passes or f.in_progress:
                continue
            # Skip features that have exceeded retry limit
            if self._feature_attempts.get(f.id, 0) >= self.max_retries_per_feature:
                continue
            deps = f.get_dependencies_safe()
            if all(dep_id in passing_ids for dep_id in deps):
                ready.append(f)

        if not ready:
            return None

        # Sort by priority, then id
        ready.sort(key=lambda f: (f.priority, f.id))
        return ready[0]

    # -----------------------------------------------------------------
    # Compile → persist → execute → sync
    # -----------------------------------------------------------------

    def compile_feature(self, feature: Feature) -> AgentSpec:
        """Compile a Feature into an AgentSpec.

        Uses DSPy SpecBuilder when available (API key set),
        falls back to FeatureCompiler otherwise.
        """
        _logger.info(
            "Compiling Feature #%d '%s' (category=%s) -> AgentSpec",
            feature.id, feature.name, feature.category,
        )

        # Try DSPy SpecBuilder first
        if self._dspy_builder is not None:
            print(f"[SPEC] Compiling Feature #{feature.id} -> AgentSpec (DSPy)", flush=True)
            task_type = extract_task_type_from_category(feature.category)
            steps = feature.get_steps_safe() if hasattr(feature, 'get_steps_safe') else []
            task_desc = (
                f"Feature #{feature.id}: {feature.name}\n"
                f"Category: {feature.category}\n"
                f"Description: {feature.description}\n"
                f"Steps:\n" + "\n".join(f"  - {s}" for s in steps)
            )
            context = {
                "feature_id": feature.id,
                "feature_name": feature.name,
                "feature_category": feature.category,
            }

            result: BuildResult = self._dspy_builder.build(
                task_description=task_desc,
                task_type=task_type,
                context=context,
                source_feature_id=feature.id,
            )

            if result.success and result.agent_spec:
                _logger.info(
                    "DSPy compiled: spec=%s, task_type=%s",
                    result.agent_spec.name, result.agent_spec.task_type,
                )
                print(f"[SPEC] DSPy generated spec: {result.agent_spec.name}", flush=True)
                return result.agent_spec
            else:
                _logger.warning(
                    "DSPy compilation failed for Feature #%d: %s — falling back to FeatureCompiler",
                    feature.id, result.error,
                )
                print(f"[SPEC] DSPy fallback -> FeatureCompiler (error: {result.error})", flush=True)

        # Fallback: FeatureCompiler (no API needed)
        print(f"[SPEC] Compiling Feature #{feature.id} -> AgentSpec (FeatureCompiler)", flush=True)
        spec = self.compiler.compile(feature)
        _logger.info(
            "Compiled: spec=%s, task_type=%s",
            spec.name, spec.task_type,
        )
        return spec

    def persist_spec(self, spec: AgentSpec) -> str:
        """
        Persist AgentSpec and its AcceptanceSpec to the database.

        If a spec with the same name already exists (retry scenario),
        the old spec is deleted first (cascades to runs/acceptance).

        Returns:
            The spec ID
        """
        # Handle retry: delete existing spec with same name
        existing = (
            self.session.query(AgentSpec)
            .filter(AgentSpec.name == spec.name)
            .first()
        )
        if existing:
            _logger.info(
                "Replacing existing spec '%s' (id=%s) for retry",
                existing.name, existing.id,
            )
            self.session.delete(existing)
            self.session.flush()

        self.session.add(spec)
        if spec.acceptance_spec:
            self.session.add(spec.acceptance_spec)

        self.session.commit()
        _logger.info("Persisted AgentSpec %s (id=%s)", spec.name, spec.id)

        # Optional: materialize snapshot file
        if self.materialize_agents:
            materialize_spec(spec, self.project_dir)

        return spec.id

    def execute_spec(self, spec: AgentSpec) -> AgentRun:
        """
        Execute an AgentSpec via HarnessKernel.

        Uses ClaudeSDKTurnExecutor when ANTHROPIC_API_KEY is available,
        otherwise falls back to immediate completion (infra proof mode).
        """
        _logger.info(
            "HarnessKernel.execute(spec_id=%s, name=%s)",
            spec.id, spec.name,
        )
        print(f"[SPEC] HarnessKernel.execute(spec_id={spec.id})", flush=True)

        # Create executor via factory (respects AUTOBUILDR_EXECUTOR env var)
        from api.executor_config import create_executor_for_spec, get_executor_type
        executor = create_executor_for_spec(project_dir=self.project_dir, spec=spec)
        executor_type = get_executor_type()
        if executor:
            _logger.info("Using %s executor for real execution", executor_type)
        else:
            _logger.info("No executor available — using infra-proof mode (immediate completion)")

        kernel = HarnessKernel(db=self.session)
        run = kernel.execute(
            spec,
            turn_executor=executor,
            context={
                "project_dir": str(self.project_dir),
                "feature_id": spec.source_feature_id,
            },
        )

        _logger.info(
            "Execution complete: run_id=%s, status=%s, verdict=%s, turns=%d",
            run.id, run.status, run.final_verdict, run.turns_used,
        )
        print(
            f"[SPEC] Acceptance verdict: {run.final_verdict} "
            f"(run_id={run.id}, status={run.status})",
            flush=True,
        )
        return run

    def sync_verdict(self, feature: Feature, run: AgentRun) -> None:
        """
        Update Feature.passes based on AgentRun verdict.

        Mapping:
            verdict == "passed"  -> Feature.passes = True
            verdict != "passed"  -> Feature.passes = False
        Always clears in_progress.
        """
        passed = run.final_verdict == "passed"
        feature.passes = passed
        feature.in_progress = False
        self.session.commit()

        _logger.info(
            "Feature #%d state synced: passes=%s (verdict=%s)",
            feature.id, passed, run.final_verdict,
        )

    # -----------------------------------------------------------------
    # Run one feature end-to-end
    # -----------------------------------------------------------------

    def run_one_feature(self, feature: Feature) -> AgentRun | None:
        """
        Process a single feature through the full spec pipeline.

        Steps: claim -> compile -> persist -> execute -> sync verdict
        """
        # Capture identity before entering try block (avoids lazy-load
        # issues if the session enters a PendingRollbackError state).
        feat_id = feature.id
        feat_name = feature.name

        # Track attempt count
        self._feature_attempts[feat_id] = self._feature_attempts.get(feat_id, 0) + 1
        attempt = self._feature_attempts[feat_id]
        _logger.info("Feature #%d attempt %d/%d", feat_id, attempt, self.max_retries_per_feature)

        # Mark in-progress
        feature.in_progress = True
        self.session.commit()

        try:
            # Compile
            spec = self.compile_feature(feature)

            # Persist
            self.persist_spec(spec)

            # Execute
            run = self.execute_spec(spec)

            # Sync
            self.sync_verdict(feature, run)

            return run

        except Exception as e:
            # Rollback first to clear any pending transaction errors
            self.session.rollback()

            _logger.error(
                "Failed to process Feature #%d '%s': %s",
                feat_id, feat_name, e,
            )
            # Mark feature as not-in-progress on failure
            try:
                feature.in_progress = False
                feature.passes = False
                self.session.commit()
            except Exception:
                self.session.rollback()
            return None

    # -----------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------

    def run_loop(self, max_features: int | None = None) -> int:
        """
        Main orchestration loop: process features until done or limit reached.

        Args:
            max_features: Maximum number of features to process (None = all)

        Returns:
            Number of features processed
        """
        # Install signal handler for graceful shutdown
        original_sigint = signal.getsignal(signal.SIGINT)

        def _handle_signal(signum, frame):
            _logger.info("Shutdown signal received, finishing current feature...")
            print("[SPEC] Shutdown requested, finishing current feature...", flush=True)
            self._shutdown = True

        signal.signal(signal.SIGINT, _handle_signal)

        processed = 0
        successes = 0
        failures = 0

        try:
            while True:
                if self._shutdown:
                    _logger.info("Shutting down after %d features", processed)
                    break

                if max_features is not None and processed >= max_features:
                    _logger.info("Reached max_features limit: %d", max_features)
                    break

                feature = self.get_next_feature()
                if feature is None:
                    _logger.info("No more ready features")
                    break

                _logger.info(
                    "Processing feature %d/%s: #%d '%s'",
                    processed + 1,
                    max_features or "all",
                    feature.id,
                    feature.name,
                )

                run = self.run_one_feature(feature)
                processed += 1

                if run and run.final_verdict == "passed":
                    successes += 1
                else:
                    failures += 1

                # Progress
                total = self.session.query(Feature).count()
                passing = self.session.query(Feature).filter(Feature.passes == True).count()
                _logger.info(
                    "Progress: %d/%d features passing (%d processed this run, %d ok, %d fail)",
                    passing, total, processed, successes, failures,
                )

        finally:
            signal.signal(signal.SIGINT, original_sigint)

        # Print verification summary
        print_verification_summary(self.session, self.project_dir)

        print(
            f"\n[SPEC] Done. Processed {processed} features "
            f"({successes} passed, {failures} failed)",
            flush=True,
        )

        return processed
