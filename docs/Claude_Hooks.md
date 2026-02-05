# Claude Code Hooks

## Definition

> Hooks are deterministic lifecycle interceptors that run shell commands or prompts at well-defined points in the Claude Code execution flow.

---

## Why Hooks Matter

Hooks are a **first-class governance mechanism**, not a workaround. They:

- Receive structured JSON context via stdin
- Can block execution via exit codes
- Can inject corrective feedback back into the model
- Run outside the LLM (not hallucinated)

> **Key insight:** Hooks convert polite suggestions into guaranteed actions.

---

## Hook Events for AutoBuildr

| Hook | Purpose |
|------|---------|
| `SessionStart` | Hydration: inject spec summaries, project context, current feature |
| `UserPromptSubmit` | Validate or enrich prompts before reasoning begins |
| `PreToolUse` | Enforce tool policy, sandbox boundaries, security |
| `PostToolUse` | Run tests, linters, formatters (TDD layer) |
| `Stop` | Sync-back: persist deltas, commit, emit artifacts |
| `PreCompact` | Snapshot state before context compaction |

---

## Blocking and Feedback Loop

The hook system creates a closed learning loop:

- **Exit code 0** = Allow
- **Exit code 2** = Deny
- **stderr text** is fed back to the model
- Structured JSON responses (`permissionDecision`, `permissionDecisionReason`) improve self-correction

This implements the **Ralph Wiggum correction loop** at the runtime boundary:

> The agent keeps retrying until tests pass.

Hooks are the correct place to enforce this — not DSPy, not prompts.

---

## Separation of Responsibility

### AutoBuildr (Authoritative Layer)
- Owns specs (features, agents, skills)
- Owns task state and dependencies
- Owns acceptance criteria
- Owns orchestration (Maestro)

### Claude Code (Execution Substrate)
- Executes actions
- Applies hooks
- Discovers skills
- Runs tools
- Provides feedback loops

### DSPy (Compiler Layer)
- Transforms messy context → structured artifacts
- Produces AgentSpecs, SkillSpecs, test intents
- Never enforces policy at runtime

---

## Functional vs Visibility Artifacts

Functional behavior lives in:
- Hooks
- Skills
- Agent markdown (real agents)

Visibility artifacts (generated specs) are intentionally inert.

---

## The Architectural Principle

> Autonomous systems only work when reasoning, execution, and enforcement are separated.

| Component | Role |
|-----------|------|
| DSPy | Reasons |
| AutoBuildr | Orchestrates |
| Claude Code | Executes |
| Hooks | Enforce |
| Skills | Specialize |

This alignment with Claude Code's design makes the architecture robust and maintainable.
