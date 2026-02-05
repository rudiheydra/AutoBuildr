# Claude Code State Management

## Overview

Claude Code separates "fancy chat" from "execution engine" through deliberate state management. The core principle: **Claude Code does not trust LLM memory**.

LLM memory is lossy:
- Context gets compacted
- Turns get summarized
- Long sessions drift
- Parallel agents can't share a brain

Therefore, Claude Code **externalizes state** wherever correctness matters.

---

## The Three Layers of State

### Layer 1: Ephemeral Reasoning State (LLM-only)

The classic scratch space:
- Chain-of-thought
- Short-lived plans
- Temporary reasoning

**Properties:**
- Exists only in the model
- Disappears on compaction
- Never relied on for correctness

Claude Code explicitly treats this as **unsafe for project control**.

---

### Layer 2: Session-Scoped Operational State (Tasks)

Claude Code introduced a Task state machine for:
- Dependency tracking
- Ownership assignment
- Parallel subagents
- Deterministic progression

**Task Operations:**
- `TaskCreate` — Define a task
- `TaskUpdate` — Change status
- `TaskList` / `TaskGet` — Query tasks

**Task Properties:**
```
id: string
status: pending | in_progress | completed
blocked_by: [task_ids]
blocks: [task_ids]
owner: string
```

> **Critical:** Tasks exist only for the lifetime of a Claude session.

Tasks are:
- Not written to disk
- Not restored automatically
- Not shared unless explicitly rehydrated

This is intentional. Tasks are meant to be:
- Fast
- Flexible
- Disposable
- Immune to long-term drift

**Think of Tasks as runtime registers, not memory.**

---

### Layer 3: Persistent Project State (Filesystem)

The real source of truth:
- `CLAUDE.md`
- `.claude/agents/*.md`
- `.claude/skills/*`
- Project files
- Test outputs
- Git history

When Claude Code needs durability, it **reads, writes, and diffs files**. It never "remembers" them.

---

## Hydration: Bridging Sessions

Because Tasks are ephemeral, Claude Code uses **hydration** at session start:

1. Read markdown/files
2. Identify unfinished work
3. Create fresh Tasks that mirror that work

**Example:**
```markdown
- [ ] Implement auth middleware
- [ ] Add unit tests
```

Becomes:
```python
TaskCreate(id="auth_middleware")
TaskCreate(id="auth_tests", blocked_by=["auth_middleware"])
```

> **Hydration:** persistent text → session Tasks

---

## Sync-back: Surviving Session End

When the agent finishes:
1. Tasks are updated (completed)
2. Hooks or final steps write results back to disk

Examples:
- Checking a checkbox
- Updating status sections
- Committing code
- Writing test results

> **Sync-back:** session Tasks → persistent artifacts

Claude Code never tries to serialize Tasks themselves.

---

## Why Tasks Are Session-Scoped

Claude Code deliberately does not persist Tasks. Why?

1. **Avoids split-brain** — Two sessions with stale task graphs is worse than none
2. **Keeps Tasks cheap** — No migrations, versioning, or schema evolution
3. **Forces filesystem truth** — If it's not written down, it doesn't exist

This is a discipline, not a limitation.

---

## Hooks: Deterministic State Enforcement

Hooks enforce correctness without trusting the model.

| Hook | Purpose |
|------|---------|
| `SessionStart` | Inject context, run hydration, load constraints |
| `PreToolUse` | Block invalid actions, enforce policies, prevent state corruption |
| `PostToolUse` | Run tests, validate outputs, update artifacts |
| `Stop` | Final sync-back, commits, notifications |

**Key distinction:**
- Tasks are "what should happen"
- Hooks are "what must happen"

Hooks are outside the model, deterministic, and authoritative.

---

## Skills: Conditional State Expansion

Skills solve context bloat by enabling progressive disclosure:

1. Claude Code loads skill metadata (cheap)
2. Only loads full skill instructions when needed

**Levels:**
- Level 1: Awareness (YAML frontmatter)
- Level 2: Instructions (full SKILL.md)
- Level 3: Execution resources (scripts, references)

Skills are not stateful — they're **state injectors**.

---

## What Claude Code Intentionally Leaves Open

Claude Code does **not**:
- Persist Tasks
- Version workflows
- Reason about agent creation
- Manage cross-session orchestration
- Guarantee test-driven convergence

This is not an omission — it's a boundary.

---

## Where AutoBuildr Fits

AutoBuildr fills the gaps Claude Code intentionally leaves:

| Claude Code | AutoBuildr |
|-------------|------------|
| Tasks (ephemeral) | AgentSpecs (persistent) |
| Session state | Project state |
| Runtime orchestration | Compile-time orchestration |
| Hooks enforce | Validators verify |
| Hydration manual | Hydration automated |

AutoBuildr:
- Compiles specs
- Persists intent
- Hydrates execution
- Audits outcomes

Claude Code:
- Executes safely

Together: **a compiler + a runtime**

---

## Mental Models

> Claude Code manages execution state. AutoBuildr manages architectural state.

Or more concisely:

> **Tasks are the stack. Specs are the heap.**
