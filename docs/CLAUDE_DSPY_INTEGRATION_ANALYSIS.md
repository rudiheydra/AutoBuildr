# AutoBuildr: Claude CLI + DSPy Integration Analysis

**Date:** 2026-02-06
**Analyst:** Codebase Analysis Agent
**Scope:** How AutoBuildr leverages Claude Code CLI features alongside DSPy for dynamic agent creation

---

## Executive Summary

AutoBuildr implements a sophisticated **Spec-Driven Agent Pipeline** that transforms human intent into executable Claude Code agents. The system uses DSPy as a **structured reasoning compiler** and Claude Code CLI as the **execution substrate**. This separation follows the core architectural insight from the project's documentation:

> "Claude Code is a runtime. AutoBuildr is the compiler."

The pipeline implements a three-tier architecture:
1. **Reasoning Layer (DSPy)** — Compiles natural language into structured AgentSpecs
2. **Persistence Layer (AutoBuildr)** — Manages specs, runs, and artifacts in SQLite
3. **Execution Layer (Claude CLI)** — Runs agents with enforced constraints via hooks

---

## 1. Claude Code CLI Features Used

### 1.1 Agent Definition Files (`.claude/agents/*.md`)

The project stores executable agents in `.claude/agents/`:

```
.claude/agents/
├── maestro.md       # Orchestrator - delegates to Octo
├── octo.md          # AgentSpec generator using DSPy
├── spec-builder.md  # 6-stage DSPy pipeline coordinator
├── coder.md         # Implementation agent
├── test-runner.md   # Test execution agent
├── auditor.md       # Security audit agent (read-only)
├── code-review.md   # Quality review agent
└── deep-dive.md     # Investigation agent
```

Each agent file follows Claude Code conventions:
- **YAML frontmatter**: `name`, `description`, `model`, `color`
- **Markdown body**: Instructions, constraints, tool policies

**Implementation file:** `api/agent_materializer.py:75-112`

### 1.2 Skills System (`.claude/skills/`)

The project uses the Claude Skills progressive disclosure pattern:

```
.claude/skills/
├── frontend-design/
│   └── SKILL.md     # UI/UX expertise
└── gsd-to-autobuildr-spec/
    ├── SKILL.md
    └── references/
        └── app-spec-format.md
```

Skills are **capability lenses** that augment agents without bloating context. The project leverages:
- **YAML frontmatter** for cheap skill indexing
- **Level 2 loading** only when relevant
- **Reference files** for domain-specific patterns

### 1.3 Task State Machine

AutoBuildr extends Claude Code's ephemeral Task system with persistent state:

| Claude Code Tasks | AutoBuildr Extension |
|-------------------|----------------------|
| Session-scoped | Persisted to SQLite |
| No cross-session | Full audit trail |
| Simple status | State machine with validators |
| No dependencies | Feature dependency graphs |

**Key insight from docs:** *"Tasks are the stack. Specs are the heap."*

### 1.4 Model Selection

The project implements intelligent model selection in `api/octo.py:129-204`:

```python
HAIKU_CAPABILITIES = {"documentation", "lint", "format", "smoke_testing", ...}
OPUS_CAPABILITIES = {"architecture_design", "security_audit", "complex_refactoring", ...}

TASK_TYPE_MODEL_DEFAULTS = {
    "coding": "sonnet",
    "testing": "sonnet",
    "documentation": "haiku",
    "audit": "opus",
}
```

### 1.5 MCP Server Integration

The Agent Materializer generates `settings.local.json` for MCP server configuration:

```python
# api/agent_materializer.py:135-156
MCP_SERVER_CONFIGS = {
    "features": {
        "command": "uv",
        "args": ["run", "--with", "mcp", "mcp_features_server"],
    },
    "playwright": {
        "command": "npx",
        "args": ["@anthropic/mcp-server-playwright", "--headless"],
    },
}
```

---

## 2. DSPy Integration Architecture

### 2.1 The SpecGenerationSignature

The core DSPy signature is defined in `api/dspy_signatures.py:18-212`:

```python
class SpecGenerationSignature(dspy.Signature):
    # Inputs
    task_description: str = dspy.InputField(...)
    task_type: str = dspy.InputField(...)  # coding|testing|refactoring|...
    project_context: str = dspy.InputField(...)  # JSON

    # Outputs
    reasoning: str = dspy.OutputField(...)      # Chain-of-thought
    objective: str = dspy.OutputField(...)       # Clear goal
    context_json: str = dspy.OutputField(...)    # Task context
    tool_policy_json: str = dspy.OutputField(...)# Allowed/forbidden tools
    max_turns: int = dspy.OutputField(...)       # Budget
    timeout_seconds: int = dspy.OutputField(...) # Timeout
    validators_json: str = dspy.OutputField(...) # Acceptance criteria
```

**Usage pattern:**
```python
lm = dspy.LM("anthropic/claude-sonnet")
dspy.configure(lm=lm)
generator = dspy.ChainOfThought(SpecGenerationSignature)
result = generator(task_description=..., task_type=..., project_context=...)
```

### 2.2 The 6-Stage Pipeline

The SpecBuilder (`api/spec_builder.py`) orchestrates 6 stages:

```
Task Description (natural language)
       │
       ▼
[Stage 1] detect_task_type()
       → task_type (coding|testing|refactoring|documentation|audit|custom)
       │
       ├─────────────────────────────────┐
       ▼                                 ▼
[Stage 2] derive_tool_policy()    [Stage 3] derive_budget()
       → tool_policy dict                → {max_turns, timeout_seconds}
       │                                 │
       ▼                                 │
[Stage 4] generate_spec_name()           │
       → unique URL-safe name            │
       │                                 │
       ▼                                 │
[Stage 5] generate_validators_from_steps()
       → acceptance validators           │
       │                                 │
       ├─────────────────────────────────┘
       ▼
[Stage 6] SpecBuilder.build()
       → BuildResult { agent_spec, acceptance_spec }
```

**Module references:**
| Stage | Module | Function |
|-------|--------|----------|
| 1 | `api/task_type_detector.py` | `detect_task_type()` |
| 2 | `api/tool_policy.py` | `derive_tool_policy()` |
| 3 | `api/tool_policy.py` | `derive_budget()` |
| 4 | `api/spec_name_generator.py` | `generate_spec_name()` |
| 5 | `api/validator_generator.py` | `generate_validators_from_steps()` |
| 6 | `api/spec_builder.py` | `SpecBuilder.build()` |

### 2.3 DSPy Module Types Used

The project leverages multiple DSPy patterns:

1. **ChainOfThought** — Primary reasoning module for spec generation
2. **Predict** — Simple structured output when reasoning isn't needed
3. **Signature validation** — Schema-validated outputs via Pydantic integration

---

## 3. The Maestro → Octo → Materializer Pipeline

### 3.1 Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  MAESTRO (Orchestrator)                                         │
│  - Analyzes project context and requirements                    │
│  - Decomposes specs into features with dependencies             │
│  - Decides when new agents are needed vs using existing ones    │
│  - Produces OctoRequestPayload when agent generation required   │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼ OctoRequestPayload
┌─────────────────────────────────────────────────────────────────┐
│  OCTO (Agent Factory)                                           │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  DSPy Pipeline                                          │    │
│  │  ├── Analyze required_capabilities                      │    │
│  │  ├── Select tools, model, budget                        │    │
│  │  ├── Generate objective and instructions                │    │
│  │  └── Output structured AgentSpec objects                │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  Output: List[AgentSpec] + Optional[List[TestContract]]         │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼ AgentSpec objects
┌─────────────────────────────────────────────────────────────────┐
│  AGENT MATERIALIZER (api/agent_materializer.py)                 │
│  ├── Renders YAML frontmatter + Markdown body                   │
│  ├── Validates template output (required sections)              │
│  ├── Writes to .claude/agents/generated/{name}.md               │
│  ├── Generates settings.local.json if MCP needed                │
│  └── Records audit event                                        │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼ .md files
┌─────────────────────────────────────────────────────────────────┐
│  CLAUDE CLI                                                     │
│  ├── Loads agents from .claude/agents/*.md                      │
│  ├── Applies tool policies and permissions                      │
│  ├── Executes with configured model and constraints             │
│  └── Returns structured results                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 OctoRequestPayload Schema

```python
@dataclass
class OctoRequestPayload:
    project_context: dict[str, Any]  # name, tech_stack, environment
    required_capabilities: list[str]  # e2e_testing, api_testing, etc.
    existing_agents: list[str]        # To avoid duplication
    constraints: dict[str, Any]       # max_agents, model, tools
    source_feature_ids: list[int]     # Traceability
    request_id: str                   # UUID
```

### 3.3 AgentSpec Model

```python
@dataclass
class AgentSpec:
    # Identity
    id: str                    # UUID
    name: str                  # "e2e-browser-tester"
    display_name: str          # "E2E Browser Tester"
    icon: str | None           # Emoji

    # Task Definition
    objective: str             # What to accomplish
    task_type: str             # coding|testing|refactoring|...
    context: dict | None       # Task-specific data

    # Tool Policy
    tool_policy: dict          # allowed_tools, forbidden_patterns, hints

    # Execution Budget
    max_turns: int             # 1-500
    timeout_seconds: int       # 60-7200

    # Metadata
    priority: int              # 1-9999
    tags: list[str] | None
    source_feature_id: int | None
```

---

## 4. Tool Policy Enforcement

### 4.1 Defense-in-Depth Strategy

The tool policy system (`api/tool_policy.py`) implements multiple protection layers:

1. **Allowed Tools Whitelist** — Only permitted tools can execute
2. **Forbidden Tools Blacklist** — Explicit tool blocking (takes precedence)
3. **Forbidden Patterns** — Regex-based argument validation
4. **Directory Sandbox** — File operations restricted to allowed paths
5. **Path Traversal Blocking** — Prevents `..` escape attempts

### 4.2 Task-Type-Specific Tool Sets

```python
TOOL_SETS = {
    "coding": ["Read", "Write", "Edit", "Bash", "Glob", "Grep", ...],
    "testing": ["Read", "Bash", "Glob", "Grep", ...],  # No Write
    "audit": ["Read", "Glob", "Grep"],                 # Read-only
    "documentation": ["Read", "Write", "Glob", ...],
}
```

### 4.3 Security Baseline Patterns

```python
SECURITY_BASELINE_PATTERNS = [
    r"rm\s+(-[rf]+\s+)*[/~]",     # Destructive rm commands
    r"curl.*\|.*sh",              # Remote code execution
    r"\.env",                      # Credential files
    r"(password|secret|api[_-]?key)",  # Secrets in args
]
```

---

## 5. Agent Playground Integration

The project includes a separate testing environment (`/home/rudih/workspace/agent-playground/`) with three components:

### 5.1 Architecture

```
agent-playground/
├── ui/              # React + Vite (port 5173)
├── dspy-backend/    # FastAPI (port 8100)
│   └── app/
│       ├── routers/pipelines.py   # Pipeline CRUD
│       ├── routers/executions.py  # Execution + Sandbox
│       └── services/sandbox.py    # Git worktree isolation
└── agent-executor/  # Express/TS (port 8200)
    └── src/
        ├── routes/execute.ts         # Claude CLI execution
        └── services/claudeExecutor.ts  # Subprocess management
```

### 5.2 Key Features

1. **Pipeline Configuration** — Visual DSPy signature builder
2. **Git Worktree Sandbox** — Isolated execution with diff review
3. **SSE Streaming** — Real-time execution updates
4. **Tool Configuration** — Dynamic tool selection per pipeline

### 5.3 Sandbox Flow

```
Execution starts → Create git worktree
       ↓
Agent runs in sandbox directory
       ↓
Capture unified diff
       ↓
User reviews → Apply (cherry-pick) or Discard (cleanup)
```

---

## 6. Key Architectural Insights

### 6.1 Separation of Concerns

| Layer | Responsibility | Tool |
|-------|---------------|------|
| Reasoning | Structured spec generation | DSPy |
| Compilation | Intent → AgentSpec | SpecBuilder |
| Persistence | State, audit, artifacts | SQLite |
| Materialization | Spec → .md files | Agent Materializer |
| Execution | Running agents safely | Claude CLI |
| Enforcement | Tool policies, hooks | Claude Code runtime |

### 6.2 DSPy Role: Compiler, Not Runtime

From the documentation:

> "DSPy is the compiler backend of the factory. It reasons in structured space, emits validated schemas, and adapts output formats cleanly. DSPy is how Octo thinks — not what Octo produces."

DSPy is used for:
- ✅ Generating correctly structured artifacts
- ✅ Enforcing schemas via signatures
- ✅ Separating reasoning from templating

DSPy is NOT used for:
- ❌ Runtime tool arbitration
- ❌ Lifecycle hooks
- ❌ Sandbox enforcement

### 6.3 Hydration & Sync-back Pattern

The project implements the Claude Code hydration pattern:

```
[Session Start]
    │
    ▼
Hydration: Read specs/features from SQLite
    │
    ▼
Create session-scoped Tasks for current work
    │
    ▼
Execute with tool policies and validators
    │
    ▼
Sync-back: Persist results, update specs, commit artifacts
    │
    ▼
[Session End]
```

### 6.4 The "Ralph Wiggum" Correction Loop

From the documentation:

> "This iterative, failure-driven refinement process forces the agent to keep working on a task until it passes all predefined success criteria."

Implementation via acceptance validators:
- `test_pass` — Run command and check exit code
- `file_exists` — Verify expected files
- `forbidden_patterns` — Ensure no banned patterns in output

---

## 7. Files Summary

### Core Pipeline Files

| File | Purpose |
|------|---------|
| `api/octo.py` | DSPy-powered agent factory |
| `api/spec_builder.py` | 6-stage compilation pipeline |
| `api/dspy_signatures.py` | SpecGenerationSignature definition |
| `api/agent_materializer.py` | AgentSpec → .md file converter |
| `api/tool_policy.py` | Tool enforcement and sandboxing |
| `api/agentspec_models.py` | AgentSpec, AgentRun, AgentEvent models |

### Agent Definitions

| File | Role |
|------|------|
| `.claude/agents/maestro.md` | Orchestrator |
| `.claude/agents/octo.md` | Agent factory |
| `.claude/agents/spec-builder.md` | DSPy pipeline |
| `.claude/agents/coder.md` | Implementation |
| `.claude/agents/test-runner.md` | Test execution |
| `.claude/agents/auditor.md` | Security audit |

### Agent Playground

| File | Purpose |
|------|---------|
| `dspy-backend/app/routers/pipelines.py` | Pipeline CRUD |
| `dspy-backend/app/services/sandbox.py` | Git worktree isolation |
| `agent-executor/src/services/claudeExecutor.ts` | CLI subprocess |

---

## 8. Conclusion

AutoBuildr demonstrates a mature implementation of the "Spec-Driven Development" paradigm:

1. **DSPy as Compiler** — Transforms natural language into validated AgentSpecs
2. **Claude Code as Runtime** — Executes agents with full tool access under constraints
3. **Persistent State** — SQLite-backed specs, runs, and artifacts for auditability
4. **Defense-in-Depth** — Multiple security layers from tool policies to sandbox isolation
5. **Agent Factory Pattern** — Octo dynamically generates specialized agents on demand

The architecture cleanly separates:
- **What to do** (Specs) from **How to execute** (Claude CLI)
- **Reasoning** (DSPy) from **Enforcement** (Hooks/Policies)
- **Ephemeral state** (Tasks) from **Persistent state** (SQLite)

This design enables autonomous software development with appropriate guardrails and full traceability.
