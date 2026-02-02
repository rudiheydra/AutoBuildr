# AutoBuildr Project Status

**Date:** 2026-01-30
**Branch:** master
**Feature Completion:** 133/133 (100%)

---

## What Is AutoBuildr?

AutoBuildr is a declarative, spec-driven agentic build system. Instead of hard-coding agent behavior, each task is compiled at runtime into a structured **AgentSpec** that defines the agent's objective, constraints, tools, acceptance criteria, and execution budget. A lightweight **HarnessKernel** executes these specs, manages state, enforces verification gates, and persists all artifacts for traceability.

**Stack:** Python/FastAPI backend, React/Vite frontend, SQLite/SQLAlchemy database, Claude SDK + DSPy for AI, WebSocket for real-time updates.

---

## Where We Are

All 133 backlog features have passing tests. The four implementation phases defined in `prompts/app_spec.txt` are substantially built out:

| Phase | Name | Status | Summary |
|-------|------|--------|---------|
| 0 | Kernel Wiring | Complete | HarnessKernel, AgentRun lifecycle, event recording, validators, artifacts, static adapter |
| 1 | DSPy SpecBuilder | Complete | DSPy signatures, template registry, feature compiler, display derivation, migration flag |
| 2 | ToolProvider Expansion | Complete | Tool filtering, forbidden patterns, directory sandboxing, path traversal blocking, policy violation logging |
| 3 | UI Dynamic Cards | Complete | WebSocket events, DynamicAgentCard, RunInspector, AcceptanceResults, keyboard navigation, accessibility |

---

## Recent Development (Latest Session)

The final stretch (Features #107-#133) focused on end-to-end proof tests across the full pipeline:

- **Feature #107-#123:** DSPy pipeline E2E tests covering all 9 stages (task type detection, tool policy derivation, budget derivation, spec name generation, validator generation, signature definition, feature compiler, spec builder, full pipeline)
- **Feature #125-#126:** `--spec` flag CLI entry point and turn executor bridge connecting HarnessKernel to Claude SDK
- **Feature #127-#132:** Proof tests for compiler output, budget enforcement, tool policy enforcement, acceptance gate evaluation, verdict sync, and spec-path persistence
- **Feature #133 (capstone):** End-to-end integration test proving `--spec` flag drives the complete pipeline for multiple features across 4 task types

---

## Spec Compliance Audit Results

A thorough audit against `prompts/app_spec.txt` was conducted on 2026-01-30. Overall compliance: **~90%**. The implementation is strong with targeted gaps remaining.

### What's Working Well

- **HarnessKernel** core execution loop with max_turns and timeout_seconds budget enforcement
- **AgentRun state machine** with validated transitions (pending, running, paused, completed, failed, timeout)
- **Event recording** with sequential ordering, 4KB payload cap, and artifact overflow
- **Three core validators** (test_pass, file_exists, forbidden_patterns) with AcceptanceGate (all_pass/any_pass)
- **Artifact storage** with inline (<=4KB) and file-based (>4KB) modes, SHA256 hashing, deduplication
- **StaticSpecAdapter** wrapping legacy initializer/coding/testing agents as AgentSpecs
- **DSPy SpecGenerationSignature** with chain-of-thought reasoning
- **FeatureCompiler** converting Feature records to AgentSpecs with full traceability
- **Migration flag** (AUTOBUILDR_USE_KERNEL) with graceful fallback to legacy path
- **Tool policy enforcement** (filtering, forbidden patterns, directory sandbox, symlink validation, path traversal blocking)
- **All 7 Agent Runs API endpoints** (list, get, events, artifacts, pause, resume, cancel)
- **All 6 Agent Specs API endpoints** (create, list, get, update, delete, execute)
- **UI components** (DynamicAgentCard, RunInspector, AcceptanceResults, EventTimeline, ArtifactList)
- **104 test files + 78 verification scripts** providing extensive coverage

### Issues Found (by severity)

#### HIGH (5 items)

| # | Issue | Location |
|---|---|---|
| 1 | `spec_path` column missing from `agent_specs` table | `api/agentspec_models.py` |
| 2 | `agent_specs.name` lacks UNIQUE constraint | `api/agentspec_models.py:183` |
| 3 | `"timeout"` missing from `EVENT_TYPES` constant and Pydantic schema (kernel records it but API rejects it) | `api/agentspec_models.py:72`, `server/schemas/agentspec.py:1016` |
| 4 | Spec Builder API endpoints missing (`POST /api/spec-builder/compile`, `GET /api/spec-builder/templates`) — backend modules exist but no HTTP routes | No router file exists |
| 5 | Execute endpoint is a placeholder — creates run record but does not invoke HarnessKernel | `server/routers/agent_specs.py:667` |

#### MEDIUM (8 items)

| # | Issue | Location |
|---|---|---|
| 1 | `final_verdict` enum uses `"partial"` instead of spec's `"error"` | `api/agentspec_models.py:63` |
| 2 | `lint_clean` validator listed in types but no class exists | `api/validators.py` |
| 3 | Validator naming mismatch: `"forbidden_output"` in types vs `"forbidden_patterns"` in registry | `api/agentspec_models.py:89` vs `api/validators.py:871` |
| 4 | Missing composite index `agent_runs(agent_spec_id, status)` | `api/agentspec_models.py` |
| 5 | Missing composite index `agent_events(run_id, event_type)` | `api/agentspec_models.py` |
| 6 | `agent_events.artifact_ref` is plain String, not a Foreign Key | `api/agentspec_models.py:679` |
| 7 | Missing `GET /api/artifacts/:id` metadata endpoint | `server/routers/artifacts.py` |
| 8 | `agent_spec_created` WebSocket event not handled in frontend | `ui/src/lib/types.ts:303` |

#### LOW (7 items)

| # | Issue |
|---|---|
| 1 | Extra columns not in spec (`spec_version`, `created_at` on runs, `path` on artifacts) |
| 2 | `artifacts.content_hash` and `size_bytes` nullable (spec implies NOT NULL) |
| 3 | `artifacts.metadata` renamed to `artifact_metadata` (SQLAlchemy reserved word avoidance) |
| 4 | Agent Specs API prefix is project-scoped (`/api/projects/{project_name}/agent-specs`) vs spec's flat `/api/agent-specs` |
| 5 | Display derivation logic duplicated across 3 modules with inconsistent icon values |
| 6 | Template Registry not integrated into DSPy SpecBuilder pipeline |
| 7 | Kernel truncates >4KB payloads without creating artifact references (data loss for oversized tool events) |

---

## Test Coverage

| Area | Files | Depth |
|------|-------|-------|
| HarnessKernel (execute, budget, timeout) | 5 test files | Comprehensive |
| AgentRun state machine | 4 test files | Comprehensive |
| API endpoints (specs, runs, artifacts) | 10+ test files | Comprehensive (unit), some require running server |
| Acceptance gate + validators | 4 test files | Comprehensive |
| Tool policy + security | 9 test files | Comprehensive |
| DSPy pipeline (all 9 stages) | 10 test files + E2E | Comprehensive |
| Event recording + WebSocket | 5 test files | Comprehensive |
| Database + schema | 4 test files | Comprehensive |
| Dependency graph | 14 test files | Exceptionally thorough |
| UI components | 10 test files | Structural (Python-based file verification, not browser-rendered) |

**Gaps:** No React component unit tests (JSDOM/testing-library), no concurrent execution tests, several E2E tests require a running server rather than using FastAPI TestClient.

---

## What We're Working On Next

### Priority 1: Fix HIGH Issues

These are the items that would cause runtime failures or missing functionality:

1. Add `"timeout"` to `EVENT_TYPES` and Pydantic schema validator — without this, timeout events break API serialization
2. Create `server/routers/spec_builder.py` with compile and templates endpoints — backend code is ready, just needs HTTP plumbing
3. Wire the execute endpoint to actually call `HarnessKernel.execute()` — currently a placeholder
4. Add `spec_path` column to `AgentSpec` model
5. Add `unique=True` to `agent_specs.name` column

### Priority 2: Fix MEDIUM Issues

6. Add missing composite database indexes (`agent_runs(spec_id, status)`, `agent_events(run_id, event_type)`)
7. Implement `LintCleanValidator` or remove from types
8. Align `forbidden_output` / `forbidden_patterns` naming across validator types and registry
9. Add `GET /api/artifacts/:id` metadata endpoint
10. Handle `agent_spec_created` in frontend WebSocket handler
11. Add ForeignKey constraint to `agent_events.artifact_ref`
12. Align `final_verdict` enum values with spec (`error` vs `partial`)

### Priority 3: Quality Improvements

13. Convert server-dependent tests to use FastAPI TestClient for CI compatibility
14. Add React component unit tests using `@testing-library/react`
15. Consolidate display derivation logic into single source of truth (`display_derivation.py`)
16. Integrate Template Registry into DSPy SpecBuilder pipeline
17. Fix kernel payload truncation to create artifact references instead of losing data

---

## Architecture Overview

```
prompts/app_spec.txt          -- Project specification (source of truth)
prompts/*.md                  -- Agent prompt templates

api/
  harness_kernel.py           -- Core execution engine (2300+ lines)
  agentspec_models.py         -- SQLAlchemy models (5 tables)
  agentspec_crud.py           -- CRUD operations
  validators.py               -- Acceptance validators + AcceptanceGate
  artifact_storage.py          -- Content-addressable artifact store
  event_recorder.py           -- Sequential event recording
  tool_policy.py              -- Tool filtering, sandboxing, policy enforcement (3700+ lines)
  static_spec_adapter.py      -- Legacy agent -> AgentSpec adapter
  dspy_signatures.py          -- DSPy SpecGenerationSignature
  spec_builder.py             -- DSPy-based spec generation
  feature_compiler.py         -- Feature -> AgentSpec compiler
  template_registry.py        -- Prompt template loading + caching
  display_derivation.py       -- Display name, icon, mascot derivation
  migration_flag.py           -- AUTOBUILDR_USE_KERNEL flag + execution dispatch
  spec_orchestrator.py        -- Spec-driven orchestration loop
  websocket_events.py         -- WebSocket event broadcasting

server/
  main.py                     -- FastAPI app setup
  routers/
    agent_specs.py            -- /api/projects/{name}/agent-specs endpoints
    agent_runs.py             -- /api/agent-runs endpoints
    artifacts.py              -- /api/artifacts endpoints
    features.py               -- /api/features endpoints (existing)
    ...                       -- Other existing routers

ui/src/
  components/
    DynamicAgentCard.tsx       -- Agent card with spec/run data
    RunInspector.tsx           -- Event timeline + artifact viewer
    AcceptanceResults.tsx      -- Validator status display
    EventTimeline.tsx          -- Chronological event viewer
    ArtifactList.tsx           -- Artifact browser + download
    TurnsProgressBar.tsx       -- Budget progress indicator
    ValidatorTypeIcon.tsx      -- Validator type icons
  hooks/
    useAgentRunUpdates.ts      -- Real-time run update hook
    useWebSocket.ts            -- WebSocket connection management

tests/                        -- 104 test files + 78 verification scripts
```

---

## Key Design Decisions

1. **Agent-Agnostic Kernel:** HarnessKernel has zero knowledge of task semantics. It only understands objective, tools, budget, and acceptance criteria.

2. **Callback-Based Execution:** The kernel delegates Claude SDK interaction to a `turn_executor` callback, improving testability and decoupling.

3. **Two Execution Paths:** Migration flag (`AUTOBUILDR_USE_KERNEL`) allows gradual transition from legacy hard-coded agents to spec-driven kernel execution, with automatic fallback on kernel errors.

4. **Deterministic Validators Only (v1):** Only `test_pass`, `file_exists`, and `forbidden_patterns` validators. No LLM-as-judge until later phases.

5. **Content-Addressable Artifacts:** All artifacts stored with SHA256 hash. Content <= 4KB stored inline, > 4KB stored as files at `.autobuildr/artifacts/{run_id}/{hash}.blob`.

---

## Existing Documentation

| File | Contents |
|------|----------|
| `docs/PHASE3_SPEC.md` | Mid-session command approval specification (not yet implemented, separate from the kernel phases) |
| `docs/SAMPLE_PROMPT.md` | Sample app prompt for testing |
| `prompts/app_spec.txt` | Full project specification (source of truth) |
| `CLAUDE.md` | AI assistant instructions and project context |
| `claude-progress.txt` | Detailed feature-by-feature progress log |
