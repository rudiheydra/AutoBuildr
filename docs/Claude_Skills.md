# Claude Code Skills

## Definition

> Skills are modular, discoverable capability bundles that Claude can load dynamically when relevant.

A Skill is not just text — it's a package:

```
.claude/skills/<skill-name>/
├── SKILL.md          # Instructions + YAML frontmatter
├── scripts/          # Optional executable helpers
└── resources/        # Optional reference files
```

---

## Key Properties

### Progressive Disclosure (Anti-Context-Bloat)

Claude does not load all skills into context. Instead:

1. Scans only YAML frontmatter for all skills (cheap)
2. Decides which skill is relevant
3. Only then loads the full SKILL.md
4. Only when executing does it run `!command` blocks

This scales agentic systems without blowing context windows.

### Filesystem-Based Discovery

Claude automatically builds an `<available_skills>` index from:
- `.claude/skills/` (project)
- `~/.claude/skills/` (user)
- Managed/plugin skill locations

No registration. No API call. No SDK glue.

> **Filesystem = capability registry**

### Live Context Injection

The `!command` syntax runs shell commands at activation time:

```markdown
!command git status
!command npm test -- --listTests
```

The stdout is injected into the model before reasoning, providing:
- Live build state
- Live test lists
- Live architecture signals

...without bloating the base prompt.

---

## What Skills Are NOT

Skills are **not**:
- Long-running agents
- State machines
- Orchestrators
- Schedulers
- Replacements for Maestro or Octo

They are **capability augmenters**, not actors.

> "When you're doing this kind of work, here's how to do it correctly in this project."

---

## AutoBuildr Role Separation

### Maestro (Orchestrator)

Reasons about:
- Project intent
- Features
- What agents are needed
- What skills are needed

Never writes files directly. Delegates spec creation.

### Octo (Spec Generator)

Uses DSPy to transform inputs into structured specs:

**Inputs:**
- AppSpec
- Feature graph
- Tech stack
- Acceptance criteria

**Outputs:**
- AgentSpec
- SkillSpec
- TestIntentSpec

Octo does reasoning, not execution.

### Materializers (Deterministic)

| Materializer | Transformation |
|--------------|----------------|
| Agent Materializer | AgentSpec → `.claude/agents/*.md` |
| Skill Materializer | SkillSpec → `.claude/skills/<name>/SKILL.md` |
| Hook Materializer | Governance hooks → `.claude/hooks/` |

No LLM here. Pure rendering + validation.

### Claude Code (Execution Substrate)

**Discovers:** agents, skills, hooks

**Executes:** tools, scripts, tests

**Enforces:** sandbox, permissions, hooks

Claude does not decide architecture. It executes within it.

---

## Where DSPy Fits

**DSPy is NOT ideal for:**
- Runtime enforcement
- CLI orchestration
- Filesystem mutation

**DSPy IS ideal for:**
- Generating correctly structured artifacts
- Enforcing schemas
- Separating reasoning from templating
- Producing reproducible specs

### Example DSPy Signature

```python
class SkillSpecSignature(dspy.Signature):
    project_context: str
    feature_set: list[str]
    task_type: str

    # Outputs
    skill_name: str
    when_to_use: str
    instructions: str
    commands: list[str]
```

Output → Materializer → `SKILL.md`

---

## The Skill Factory Pattern

Because Skills are filesystem-based and discoverable:

1. AutoBuildr can generate skills
2. Install them to `.claude/skills/`
3. Claude immediately sees them
4. Future agents benefit automatically

This enables:
- Self-improving pipelines
- Reduction of repeated failures
- Institutional memory encoded as skills

---

## Layer Responsibilities

| Layer | Contract |
|-------|----------|
| Markdown | What Claude understands |
| Specs | What AutoBuildr understands |
| DSPy | Compiler between human intent and machine-readable specs |
| Skills + Hooks | Enforcement, not generation |

Each layer has one job. No overlap. No magic.
