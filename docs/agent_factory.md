# Octo: The Agent Factory

## Overview

Octo is AutoBuildr's **Agent Factory** — a meta-agent responsible for analyzing project intent and generating specialized, executable Claude Code agents as first-class artifacts.

> **Key Distinction:** A skill factory produces instructions that shape behavior. An agent factory produces fully instantiated agents with identity, capabilities, constraints, and acceptance criteria.

---

## What Octo Produces

An agent factory generates complete agent definitions:

| Component | Description |
|-----------|-------------|
| **Identity** | Name, role, icon, color |
| **Capabilities** | Which tools the agent can use |
| **Cognition Profile** | How the agent reasons and what it optimizes for |
| **Skills** | Which skills the agent should load |
| **Constraints** | Rules the agent must obey |
| **Acceptance Criteria** | Definition of "done" for the agent's outputs |

---

## Octo's Role in the System

```
User / Product Manager
        │
        ▼
      Maestro (orchestrates work)
        │
        ▼
       Octo (architects workers)
        │
        ▼
┌───────────────────────────────┐
│ AgentSpecs (structured, typed)│
└──────────────┬────────────────┘
               ▼
┌───────────────────────────────┐
│ .claude/agents/*.md           │  ← executable agents
│ .claude/skills/* (optional)   │
│ icons / UI metadata           │
└──────────────┬────────────────┘
               ▼
       Claude Code CLI
               │
               ▼
         Autonomous execution
```

**Maestro orchestrates work. Octo architects workers.**

---

## Formal Definition

```
Octo = AgentSpec Compiler + Agent Materializer
```

### Inputs

- Project intent
- App specification
- Feature graph
- Constraints (budget, risk, tooling)
- Environment (web, backend, infra, mobile)

### Outputs

- AgentSpecs (structured, typed)
- Executable agent definitions (Claude Code-compatible markdown)
- Optional UI artifacts (icons, labels)

---

## Why Octo Sits Above the CLI

The Claude CLI **runs** agents but does **not design** them. The `/agents` interactive flow is a human convenience, not a programmable API.

Octo replaces that UI flow with:

- Structured reasoning
- Deterministic output
- Repeatable generation

---

## What Octo Reasons About

Octo explicitly answers questions that humans typically answer implicitly:

- Do we need a testing agent?
- Do we need multiple coding agents?
- Should this agent be frontend-focused or infra-focused?
- Does Playwright access make sense here?
- Should this agent be allowed to run Bash?
- What does "done" mean for this agent?
- How strict should hooks be?

---

## DSPy's Role Inside Octo

DSPy is the **compiler backend** of the factory. Octo uses DSPy to:

- Reason in structured space
- Emit validated schemas
- Adapt output formats cleanly

### Example DSPy Signatures

```python
# Generate agent specs from project context
project_context, feature_graph → list[AgentSpec]

# Convert spec to Claude-compatible markdown
AgentSpec → claude_agent_markdown
```

DSPy ensures:

- **Repeatability** — Same inputs produce same outputs
- **Schema correctness** — Outputs match expected structure
- **Evolution** — Changes without brittle prompt hacks

> **Key insight:** DSPy is how Octo thinks — not what Octo produces.

---

## Maestro vs Octo

| Aspect | Maestro | Octo |
|--------|---------|------|
| Responsibility | Task orchestration | Agent creation |
| Decides | What work happens | Who does the work |
| Manages | Runs | Identities |
| Lifecycle | Lives at runtime | Mostly runs at init/reconfig |
| Orientation | Task-oriented | Architecture-oriented |

Keeping them separate:
- Avoids overloading Maestro
- Maintains clear responsibilities
- Makes evolution easier

---

## Octo's Output is Authoritative

The output of Octo is:

- **Not advisory** — It's the spec
- **Not ephemeral** — It persists
- **Not "for visibility only"** — It executes

Generated artifacts become:

- Versioned artifacts checked into repos
- Executable by Claude Code
- Auditable by humans

This is why `.claude/agents/` matters so much.
