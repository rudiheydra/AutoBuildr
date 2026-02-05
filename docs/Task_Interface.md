# Claude Code Task Interface

## Overview

Claude Code evolved from "Todos" to "Tasks" because **prompts collapse, but state machines don't**.

> AutoBuildr is the persistent, spec-backed version of Claude Code's ephemeral Task system.

---

## Why Todos Failed

Early Claude Code used TODO lists embedded in prompts:
- Lost during compaction
- Duplicated
- Reordered incorrectly
- Impossible to reason about dependencies

---

## The Task State Machine

Claude Code introduced proper task management:

**Operations:**
- `TaskCreate`
- `TaskUpdate`
- `TaskList`
- `TaskGet`

**Task Properties:**
- `status`: pending | in_progress | completed
- `blocked_by`: dependency edges
- `blocks`: downstream dependencies

This transforms the LLM from "a chatty assistant" into "a workflow engine that happens to speak English."

---

## Tasks Are Intentionally Ephemeral

Claude Tasks:
- Live only inside a session
- Are not meant to be long-term memory
- Exist to manage current execution, not project truth

This is a deliberate design choice, not a limitation.

---

## Hydration and Sync-back

Because tasks are ephemeral, Claude Code relies on:

| Pattern | Direction | Purpose |
|---------|-----------|---------|
| **Hydration** | Markdown → Tasks | Recreate tasks from files at session start |
| **Sync-back** | Tasks → Markdown | Persist completed work at session end |

**Implication:** Markdown is the source of truth. Tasks are the execution projection.

---

## Claude Code vs AutoBuildr Mapping

| Claude Code | AutoBuildr |
|-------------|------------|
| Tasks (session-scoped) | AgentRuns / FeatureRuns |
| TaskCreate | Feature → AgentSpec compilation |
| TaskUpdate | EventRecorder + verdicts |
| Tasks.md | AppSpec / Feature DB |
| Hydration | SpecOrchestrator boot |
| Sync-back | Acceptance + artifact persistence |

> Claude Code cannot persist Tasks by design. AutoBuildr exists to persist them.

---

## Maestro and Octo Validation

### Maestro = Task Orchestrator++

- Claude Tasks manage within a session
- Maestro manages across sessions, repos, agents, and environments

Maestro is what Claude Tasks would become if they were allowed to persist.

### Octo = Task → Spec Compiler

- Claude Code creates Tasks manually or heuristically
- AutoBuildr derives agents, skills, and tests as specs **before execution even begins**

This is strictly more powerful.

---

## Why DSPy Belongs Above Tasks

The distinction:
- Tasks are **operational**
- Specs are **architectural**

**DSPy is good at:**
- Reasoning
- Structure
- Repeatability

**DSPy is bad at:**
- Real-time tool arbitration
- Lifecycle hooks
- Sandbox enforcement

> Use DSPy for spec generation, not runtime control.

---

## Two Planes of Operation

Claude Code has two distinct planes:

1. **Ephemeral execution plane** — Tasks, hooks, tools
2. **Persistent specification plane** — Markdown files

Claude Code only officially owns plane #1.

AutoBuildr owns plane #2.

Together, they form a complete autonomous development system.

---

## Key Clarifications

| Question | Answer |
|----------|--------|
| Who creates agents? | Octo + Maestro |
| Does the CLI take specs? | No, it discovers `.md` files |
| Why is everything markdown? | It's Claude's native contract |
| Why does `.claude/agents/generated` feel different? | Claude Code discovers, not generates |

---

## Summary

> Claude Code is a runtime. AutoBuildr is the compiler.

Tasks are the runtime IR (intermediate representation).

**Design principles:**
1. Treat Claude Tasks as execution-only
2. Treat AutoBuildr Specs as canonical truth
3. Tasks are never persisted
4. Specs are never inferred at runtime
5. Maestro generates specs that hydrate execution-time Tasks
