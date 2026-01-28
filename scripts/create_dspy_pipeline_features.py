#!/usr/bin/env python3
"""
Create 22 features for DSPy Pipeline E2E + Agent Definitions + Proof of Scope.

Run: python3 scripts/create_dspy_pipeline_features.py

This script creates features in 4 groups:
  Group 1: Agent Definitions (3 features) — secondary UX deliverable
  Group 2: Mocked Pipeline Unit Tests (10 features)
  Group 3: Proof of Scope — Runtime Wiring (7 features) — the critical additions
  Group 4: Verification (2 features)
"""

import json
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import requests
from registry import list_registered_projects


def find_project_name() -> str:
    """Find the project name registered for this directory."""
    projects = list_registered_projects()
    this_path = str(ROOT.resolve())
    for p in projects:
        if Path(p["path"]).resolve() == Path(this_path).resolve():
            return p["name"]
    # Fallback: try the directory name
    return ROOT.name


def build_features() -> list[dict]:
    """Build all 22 features."""
    features = []

    # =========================================================================
    # GROUP 1: Agent Definitions (Secondary UX Deliverable) — 3 features
    # =========================================================================

    features.append({
        "category": "functional",
        "name": "Create spec-builder agent definition (.claude/agents/spec-builder.md)",
        "description": "Create a Claude Code agent definition file for the spec-builder agent that maps to the DSPy spec builder pipeline. Model: opus, Color: green. Must exercise: detect_task_type() → derive_tool_policy() → derive_budget() → generate_spec_name() → generate_validators_from_steps() → SpecBuilder.build(). This is a secondary UX deliverable — it makes the agent appear in Claude Code's list, but does NOT prove runtime dynamic agent creation.",
        "steps": [
            "Create .claude/agents/spec-builder.md with valid YAML frontmatter (name: spec-builder, model: opus, color: green)",
            "Include description referencing DSPy pipeline compilation of task descriptions into AgentSpecs",
            "Markdown body documents all 6 pipeline stages with key references to api/ modules",
            "File is parseable by Claude Code (valid YAML frontmatter between --- delimiters)"
        ]
    })

    features.append({
        "category": "functional",
        "name": "Create test-runner agent definition (.claude/agents/test-runner.md)",
        "description": "Create a Claude Code agent definition file for the test-runner agent that runs acceptance validators. Model: opus, Color: blue. Must exercise: AcceptanceGate.evaluate(), FileExistsValidator, TestPassValidator, ForbiddenPatternsValidator. Secondary UX deliverable.",
        "steps": [
            "Create .claude/agents/test-runner.md with valid YAML frontmatter (name: test-runner, model: opus, color: blue)",
            "Include description referencing acceptance validator execution and gate verdicts",
            "Markdown body documents validator framework, gate modes, and key references",
            "File is parseable by Claude Code (valid YAML frontmatter between --- delimiters)"
        ]
    })

    features.append({
        "category": "functional",
        "name": "Create auditor agent definition (.claude/agents/auditor.md)",
        "description": "Create a Claude Code agent definition file for the auditor agent that performs security/quality audits with read-only tool policies. Model: opus, Color: yellow. Must exercise: detect_task_type('audit') → derive_tool_policy('audit') → read-only tools → ForbiddenPatternsValidator. Secondary UX deliverable.",
        "steps": [
            "Create .claude/agents/auditor.md with valid YAML frontmatter (name: auditor, model: opus, color: yellow)",
            "Include description referencing security/quality audit with read-only tool policies",
            "Markdown body documents audit pipeline, security scanning capabilities, and tool restrictions",
            "File is parseable by Claude Code (valid YAML frontmatter between --- delimiters)"
        ]
    })

    # =========================================================================
    # GROUP 2: Mocked Pipeline Unit Tests — 10 features
    # =========================================================================

    features.append({
        "category": "functional",
        "name": "E2E test: Task Type Detection (TestStep1 — 6 tests)",
        "description": "Create TestStep1TaskTypeDetection class in tests/test_dspy_pipeline_e2e.py with 6 tests covering Feature → task_type detection. Tests: coding description, testing description, audit description, refactoring description, empty description defaults to custom, detailed detection returns scores with confidence and matched keywords.",
        "steps": [
            "Create test class TestStep1TaskTypeDetection with 6 test methods",
            "Test detect_task_type() returns 'coding' for implement descriptions",
            "Test detect_task_type() returns 'testing' for write tests descriptions",
            "Test detect_task_type() returns 'audit' for security audit descriptions",
            "Test detect_task_type_detailed() returns scores dict with confidence level",
            "All 6 tests pass: python -m pytest tests/test_dspy_pipeline_e2e.py::TestStep1TaskTypeDetection -v"
        ]
    })

    features.append({
        "category": "functional",
        "name": "E2E test: Tool Policy Derivation (TestStep2 — 4 tests)",
        "description": "Create TestStep2ToolPolicyDerivation class with 4 tests covering task_type → tool_policy. Tests: coding policy has tools, policy has forbidden_patterns, policy has version v1, audit policy has restricted tool set.",
        "steps": [
            "Create test class TestStep2ToolPolicyDerivation with 4 test methods",
            "Test derive_tool_policy('coding') returns allowed_tools list",
            "Test policy includes forbidden_patterns array",
            "Test policy has policy_version 'v1'",
            "All 4 tests pass: python -m pytest tests/test_dspy_pipeline_e2e.py::TestStep2ToolPolicyDerivation -v"
        ]
    })

    features.append({
        "category": "functional",
        "name": "E2E test: Budget Derivation (TestStep3 — 4 tests)",
        "description": "Create TestStep3BudgetDerivation class with 4 tests covering task_type → budget. Tests: budget has max_turns/timeout_seconds, budget within bounds (1-500 turns, 60-7200 seconds), coding budget >= testing budget, complexity scaling for longer descriptions.",
        "steps": [
            "Create test class TestStep3BudgetDerivation with 4 test methods",
            "Test derive_budget() returns max_turns and timeout_seconds",
            "Test budget values within allowed bounds",
            "Test coding budget is >= testing budget (coding > testing)",
            "All 4 tests pass: python -m pytest tests/test_dspy_pipeline_e2e.py::TestStep3BudgetDerivation -v"
        ]
    })

    features.append({
        "category": "functional",
        "name": "E2E test: Spec Name Generation (TestStep4 — 4 tests)",
        "description": "Create TestStep4NameGeneration class with 4 tests covering objective → spec name. Tests: name is URL-safe, name length <= 100 chars, name has task_type prefix, name is lowercase.",
        "steps": [
            "Create test class TestStep4NameGeneration with 4 test methods",
            "Test generate_spec_name() returns URL-safe string (lowercase alphanumeric + hyphens)",
            "Test name does not exceed 100 characters even for long objectives",
            "Test name starts with task_type prefix (e.g., 'testing-')",
            "All 4 tests pass: python -m pytest tests/test_dspy_pipeline_e2e.py::TestStep4NameGeneration -v"
        ]
    })

    features.append({
        "category": "functional",
        "name": "E2E test: Validator Generation (TestStep5 — 4 tests)",
        "description": "Create TestStep5ValidatorGeneration class with 4 tests covering steps → validators. Tests: test_pass from run step, file_exists from file step, forbidden_patterns from should-not step, multiple steps generate multiple validators.",
        "steps": [
            "Create test class TestStep5ValidatorGeneration with 4 test methods",
            "Test generate_validators_from_steps() produces test_pass from 'Run pytest' step",
            "Test file_exists validator from 'File should exist' step",
            "Test forbidden_patterns from 'should not contain' step",
            "All 4 tests pass: python -m pytest tests/test_dspy_pipeline_e2e.py::TestStep5ValidatorGeneration -v"
        ]
    })

    features.append({
        "category": "functional",
        "name": "E2E test: Feature Compiler (TestStep6 — 6 tests)",
        "description": "Create TestStep6FeatureCompiler class with 6 tests covering Feature → AgentSpec. Tests: compile produces AgentSpec, correct task_type from category, has tool_policy, has AcceptanceSpec with validators, has traceability (source_feature_id), has budget.",
        "steps": [
            "Create test class TestStep6FeatureCompiler with 6 test methods",
            "Test FeatureCompiler.compile() returns AgentSpec instance",
            "Test compiled spec has correct task_type derived from category",
            "Test compiled spec has tool_policy with allowed_tools",
            "Test compiled spec has AcceptanceSpec with validators array",
            "Test compiled spec source_feature_id links back to feature",
            "All 6 tests pass: python -m pytest tests/test_dspy_pipeline_e2e.py::TestStep6FeatureCompiler -v"
        ]
    })

    features.append({
        "category": "functional",
        "name": "E2E test: SpecBuilder DSPy (TestStep7 — 4 tests)",
        "description": "Create TestStep7SpecBuilderDSPy class with 4 tests covering DSPy mock → AgentSpec. Tests: build() success with mocked DSPy prediction, empty description fails, invalid task_type fails, result carries warnings. Uses mock dspy.LM, dspy.ChainOfThought, dspy.configure.",
        "steps": [
            "Create test class TestStep7SpecBuilderDSPy with 4 test methods",
            "Mock dspy.LM, dspy.ChainOfThought, dspy.configure to avoid real API calls",
            "Test SpecBuilder.build() success returns BuildResult with agent_spec and acceptance_spec",
            "Test empty description returns failed BuildResult",
            "All 4 tests pass: python -m pytest tests/test_dspy_pipeline_e2e.py::TestStep7SpecBuilderDSPy -v"
        ]
    })

    features.append({
        "category": "functional",
        "name": "E2E test: HarnessKernel Execution (TestStep8 — 3 tests)",
        "description": "Create TestStep8HarnessKernelExecution class with 3 tests covering AgentSpec → AgentRun. Tests: kernel creates run, budget tracker tracks turns, kernel records started event. Uses in-memory SQLite.",
        "steps": [
            "Create test class TestStep8HarnessKernelExecution with 3 test methods",
            "Test HarnessKernel.initialize_run() creates BudgetTracker",
            "Test BudgetTracker tracks turns_used and remaining_turns",
            "Test kernel records 'started' AgentEvent in database",
            "All 3 tests pass: python -m pytest tests/test_dspy_pipeline_e2e.py::TestStep8HarnessKernelExecution -v"
        ]
    })

    features.append({
        "category": "functional",
        "name": "E2E test: Acceptance Gate Evaluation (TestStep9 — 3 tests)",
        "description": "Create TestStep9AcceptanceGateEvaluation class with 3 tests covering validators → verdict. Tests: gate passes with empty validators, FileExistsValidator passes for existing file, FileExistsValidator fails for missing file. Uses tmp_path fixture.",
        "steps": [
            "Create test class TestStep9AcceptanceGateEvaluation with 3 test methods",
            "Test AcceptanceGate.evaluate() returns passed for empty validators",
            "Test FileExistsValidator passes when file exists (using tmp_path)",
            "Test FileExistsValidator fails when file is missing",
            "All 3 tests pass: python -m pytest tests/test_dspy_pipeline_e2e.py::TestStep9AcceptanceGateEvaluation -v"
        ]
    })

    # =========================================================================
    # GROUP 3: Proof of Scope — Runtime Wiring — 7 features (CRITICAL)
    # =========================================================================

    features.append({
        "category": "functional",
        "name": "Proof: Orchestrator spec-path compiles Feature→AgentSpec via HarnessKernel.execute()",
        "description": "Prove the orchestrator path calls the spec-driven kernel (HarnessKernel.execute(spec)) when enabled, not legacy hard-coded agents. Create a test that: (1) creates a Feature in DB, (2) compiles it via FeatureCompiler into an AgentSpec, (3) executes via HarnessKernel.execute() with a mocked turn_executor, (4) asserts the spec-driven path was used (AgentRun created with correct agent_spec_id). Boundary mocking only: mock the turn_executor, but do NOT mock compile/execute/persist glue.",
        "steps": [
            "Create test_orchestrator_spec_path() in tests/test_dspy_pipeline_e2e.py",
            "Create a Feature in in-memory DB with category, name, description, steps",
            "Compile Feature → AgentSpec using FeatureCompiler.compile()",
            "Execute via HarnessKernel.execute(spec, turn_executor=mock_executor)",
            "Assert AgentRun was created with status in terminal states",
            "Assert AgentRun.agent_spec_id matches compiled spec ID",
            "Test passes: python -m pytest tests/test_dspy_pipeline_e2e.py -k orchestrator_spec_path -v"
        ]
    })

    features.append({
        "category": "functional",
        "name": "Proof: Dynamic compilation produces materially different AgentSpecs",
        "description": "Prove two different task descriptions compile into materially different AgentSpecs (different task_type, tool_policy, validators, budgets). Test: (1) compile a coding Feature (category='A. Database'), (2) compile an audit Feature (category='Security'), (3) assert task_type differs, tool_policy allowed_tools differ, budgets differ. This proves specs are dynamic, not hard-coded.",
        "steps": [
            "Create test_dynamic_compilation_different_specs() in tests/test_dspy_pipeline_e2e.py",
            "Compile coding Feature (category='A. Database') into AgentSpec",
            "Compile audit Feature (category='Security') into AgentSpec",
            "Assert spec1.task_type != spec2.task_type (coding vs audit)",
            "Assert spec1.tool_policy != spec2.tool_policy (different allowed_tools)",
            "Assert spec1.max_turns != spec2.max_turns or spec1.timeout_seconds != spec2.timeout_seconds (different budgets)",
            "Test passes: python -m pytest tests/test_dspy_pipeline_e2e.py -k dynamic_compilation -v"
        ]
    })

    features.append({
        "category": "data",
        "name": "Proof: Persistence — DB contains AgentSpec/AgentRun/AgentEvent after kernel run",
        "description": "Prove that after one kernel run, the database contains AgentSpec, AgentRun, and AgentEvent records with correct foreign keys and event ordering. Test: (1) create spec + run in DB, (2) execute via kernel with mocked executor, (3) query DB for AgentSpec, AgentRun, AgentEvent records, (4) verify foreign keys and event sequence ordering. Boundary mocking only: mock executor, not DB persistence.",
        "steps": [
            "Create test_persistence_after_kernel_run() in tests/test_dspy_pipeline_e2e.py",
            "Create AgentSpec and persist to in-memory SQLite",
            "Execute via HarnessKernel with mocked turn_executor that completes after 2 turns",
            "Query DB: AgentSpec exists with correct ID",
            "Query DB: AgentRun exists with agent_spec_id FK pointing to spec",
            "Query DB: AgentEvent records exist with run_id FK and ascending sequence numbers",
            "Test passes: python -m pytest tests/test_dspy_pipeline_e2e.py -k persistence_after_kernel -v"
        ]
    })

    features.append({
        "category": "functional",
        "name": "Proof: Acceptance gate PASS case — deterministic validators only",
        "description": "Prove acceptance gate returns verdict='passed' when all deterministic validators pass. No llm_judge. Test: (1) create file at tmp_path, (2) create AcceptanceSpec with file_exists validator pointing to that file, (3) evaluate via AcceptanceGate, (4) assert verdict='passed', gate_mode='all_pass'. Only deterministic validators: test_pass, file_exists, forbidden_patterns.",
        "steps": [
            "Create test_acceptance_gate_pass_deterministic() in tests/test_dspy_pipeline_e2e.py",
            "Create a real file at tmp_path/test_output.txt",
            "Create AcceptanceSpec with file_exists validator for that path",
            "Evaluate via AcceptanceGate.evaluate(run, acceptance_spec, context)",
            "Assert result.passed is True and result.verdict == 'passed'",
            "Assert only deterministic validators used (no llm_judge)",
            "Test passes: python -m pytest tests/test_dspy_pipeline_e2e.py -k acceptance_gate_pass -v"
        ]
    })

    features.append({
        "category": "functional",
        "name": "Proof: Acceptance gate FAIL case — missing file fails deterministically",
        "description": "Prove acceptance gate returns verdict='failed' when a required file_exists validator fails. Test: (1) do NOT create the expected file, (2) create AcceptanceSpec with file_exists validator pointing to missing path, (3) evaluate via AcceptanceGate, (4) assert verdict='failed'. Deterministic — no LLM involvement.",
        "steps": [
            "Create test_acceptance_gate_fail_deterministic() in tests/test_dspy_pipeline_e2e.py",
            "Create AcceptanceSpec with file_exists validator pointing to non-existent file",
            "Evaluate via AcceptanceGate.evaluate(run, acceptance_spec, context)",
            "Assert result.passed is False",
            "Assert result.verdict == 'failed'",
            "Test passes: python -m pytest tests/test_dspy_pipeline_e2e.py -k acceptance_gate_fail -v"
        ]
    })

    features.append({
        "category": "functional",
        "name": "Proof: Smoke test — full Feature→Spec→Kernel→DB→Gate without API key",
        "description": "Single runnable smoke test proving complete end-to-end wiring with NO real API key. Flow: (1) create Feature in DB, (2) compile to AgentSpec via FeatureCompiler, (3) execute via HarnessKernel with mocked turn_executor only, (4) assert DB has AgentSpec+AgentRun+AgentEvents, (5) evaluate AcceptanceGate. Boundary mocking only: mock the executor/session, NOT the compile/execute/persist glue code.",
        "steps": [
            "Create test_smoke_full_wiring_no_api_key() in tests/test_dspy_pipeline_e2e.py",
            "Create Feature in in-memory SQLite (no API key needed)",
            "Compile Feature → AgentSpec via FeatureCompiler (no mock)",
            "Persist AgentSpec to DB",
            "Execute via HarnessKernel.execute(spec, turn_executor=mock) (mock only at boundary)",
            "Assert DB contains AgentSpec, AgentRun, AgentEvent records with correct FKs",
            "Evaluate AcceptanceGate and assert GateResult returned",
            "Test passes: python -m pytest tests/test_dspy_pipeline_e2e.py -k smoke_full_wiring -v"
        ]
    })

    features.append({
        "category": "security",
        "name": "Proof: ForbiddenPatternsValidator catches forbidden output deterministically",
        "description": "Prove ForbiddenPatternsValidator works deterministically against agent run events containing forbidden patterns. Test: (1) create AgentRun with tool_result events containing 'rm -rf /', (2) configure ForbiddenPatternsValidator with standard patterns, (3) evaluate validator, (4) assert passed=False. No LLM involvement.",
        "steps": [
            "Create test_forbidden_patterns_catches_violations() in tests/test_dspy_pipeline_e2e.py",
            "Create AgentRun with AgentEvent(event_type='tool_result') containing forbidden text",
            "Configure ForbiddenPatternsValidator with patterns ['rm -rf']",
            "Evaluate validator with run context",
            "Assert result.passed is False (forbidden pattern detected)",
            "Assert result.details contains match information",
            "Test passes: python -m pytest tests/test_dspy_pipeline_e2e.py -k forbidden_patterns_catches -v"
        ]
    })

    # =========================================================================
    # GROUP 4: Verification — 2 features
    # =========================================================================

    features.append({
        "category": "functional",
        "name": "Verification: All pytest tests pass for test_dspy_pipeline_e2e.py",
        "description": "All tests in tests/test_dspy_pipeline_e2e.py pass when run with pytest. This includes all 9 test classes (Steps 1-9), the full pipeline E2E test, and all 7 Proof of Scope runtime wiring tests. Total ~39 tests.",
        "steps": [
            "Run: python -m pytest tests/test_dspy_pipeline_e2e.py -v",
            "All tests pass (0 failures, 0 errors)",
            "No warnings that indicate test logic issues",
            "Tests run without requiring a real ANTHROPIC_API_KEY"
        ]
    })

    features.append({
        "category": "functional",
        "name": "Verification: ruff lint clean on test_dspy_pipeline_e2e.py",
        "description": "The test file tests/test_dspy_pipeline_e2e.py passes ruff lint check with no errors. This ensures code quality and style consistency.",
        "steps": [
            "Run: ruff check tests/test_dspy_pipeline_e2e.py",
            "No lint errors reported",
            "No unused imports",
            "No formatting issues"
        ]
    })

    return features


def main():
    project_name = find_project_name()
    print(f"Found project: {project_name}")

    features = build_features()
    print(f"Creating {len(features)} features...")

    # Try REST API first
    url = f"http://127.0.0.1:8888/api/projects/{project_name}/features/bulk"
    payload = {"features": features}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            print(f"SUCCESS: Created {data.get('created', '?')} features via REST API")
            return
        else:
            print(f"REST API returned {resp.status_code}: {resp.text}")
            print("Falling back to direct DB insertion...")
    except Exception as e:
        print(f"REST API unreachable ({e}), falling back to direct DB insertion...")

    # Fallback: direct DB insertion
    from api.database import Feature, create_database

    project_dir = ROOT
    engine, SessionLocal = create_database(project_dir)
    session = SessionLocal()

    try:
        # Find max priority
        max_priority = session.query(Feature.priority).order_by(Feature.priority.desc()).first()
        next_priority = (max_priority[0] + 1) if max_priority else 1

        for i, f in enumerate(features):
            feature = Feature(
                priority=next_priority + i,
                category=f["category"],
                name=f["name"],
                description=f["description"],
                steps=f["steps"],
                passes=False,
                in_progress=False,
            )
            session.add(feature)

        session.commit()
        print(f"SUCCESS: Created {len(features)} features via direct DB insertion")
    except Exception as e:
        session.rollback()
        print(f"FAILED: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
