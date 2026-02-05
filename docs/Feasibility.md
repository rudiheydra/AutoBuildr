# Architecture Feasibility Analysis

## Overview

This document establishes that the AutoBuildr architecture is grounded in proven primitives that already exist and work today.

---

## Four Foundational Primitives

### 1. Task State Machines

- Explicit lifecycle: `pending → in_progress → completed`
- Dependency resolution
- Parallelization once blockers resolve

### 2. Deterministic Hooks as Governance

- Hooks convert "prompt guidance" into enforced invariants
- `PreToolUse` / `PostToolUse` create a correction loop
- Exit codes + stderr/stdout feedback close the loop

### 3. Skills as Progressive, Discoverable Context

- YAML frontmatter = cheap index
- Full SKILL.md loaded only when needed
- Runtime `!command` injection = live context

### 4. DSPy as a Compiler, Not a Runtime

- Structured IO contracts
- Optimized reasoning over what to generate, not how to act

> The insight is in how these primitives compose.

---

## The Critical Architectural Conclusion

> Claude Code is not the system of record. It is the execution substrate.

Claude Code serves as:
- A deterministic executor
- A tool + hook + skill runtime
- A place where agents act

Claude Code is **not**:
- The source of truth for specs
- The owner of task state
- The authority on architecture

**That authority lives in AutoBuildr.**

---

## Mapping to AutoBuildr

### Task System → Features + Dependencies

AutoBuildr provides:
- Persistent state
- Acceptance criteria
- Retry loops (Ralph Wiggum pattern)
- Parallel execution
- Dependency edges
- Blocked/unblocked scheduling
- Explicit "ready" semantics

Claude Tasks become an optional projection, not the backbone.

### Hydration / Sync-back → Explicit Phase Boundaries

| Phase | Owner | Artifact |
|-------|-------|----------|
| Hydration | AutoBuildr | DB ← specs / markdown |
| Execution | Claude Code | tools, hooks, skills |
| Sync-back | AutoBuildr | DB → markdown / git |

This approach:
- Survives crashes
- Supports multiple executors
- Is auditable

### Hooks → Enforcement, Not Orchestration

Hooks are governors, not planners. They:
- Block bad actions
- Enforce conventions
- Trigger validation
- Feed errors back

They do **not** decide what to do next. That's Maestro's job.

### Skills → Modular, Late-Bound Expertise

Skills are capability lenses, not agents. AutoBuildr:
- Generates skills deliberately (via Octo)
- Installs them into `.claude/skills/`
- Lets Claude Code discover them naturally

This avoids prompt bloat, hard-coded system prompts, and brittle monolith agents.

---

## DSPy's Purpose

**DSPy is NOT for:**
- Running agents
- Managing sessions
- Calling tools directly

**DSPy IS for:**
- Turning messy context into structured artifacts
- Guaranteeing schema correctness
- Optimizing generation consistency over time

> DSPy compiles intent. Claude Code executes intent.

This division is necessary, not accidental.

---

## The Skill Factory Pattern

The most powerful architectural element:

> An agent that can identify its own capability gaps and generate skills to close them.

In AutoBuildr terms:
1. Maestro detects repeated friction
2. Octo synthesizes a SkillSpec
3. Materializer installs it
4. Next run improves automatically

This is a self-extending toolchain.

---

## Architectural Summary

> AutoBuildr is a spec compiler and governance engine that materializes deterministic agent ecosystems, executed by Claude Code under enforced constraints, with DSPy providing structured reasoning and continuous improvement.

### Design Decisions Validated

- Keep AutoBuildr as the authoritative environment
- Use agent-playground as a sandbox
- Treat Claude Code as a programmable substrate
- Move away from ad-hoc prompts toward specs + hooks + skills
- Don't blindly mirror Claude's internal abstractions

The system is stronger because it owns the truth.
