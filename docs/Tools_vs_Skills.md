# Tools vs Skills

## The Core Distinction

> **Tools do things. Skills teach how to do things.**

This is an architectural boundary, not just a slogan.

---

## Tools: Execution Primitives

Tools are capabilities the agent invokes to act on the world.

**Examples:**
- Read
- Write
- Edit
- Bash
- WebFetch
- Playwright
- MCP tools (feature_get_by_id, etc.)

**Properties:**
- Deterministic
- Side-effecting
- Machine-level
- Enforced by the runtime
- Security-governed (permissions, hooks)

**A tool:**
- Does not explain why
- Does not contain best practices
- Does not guide decision-making
- Just executes

> Think of tools as syscalls.

---

## Skills: Conditional Knowledge + Workflow Patterns

Skills are structured instruction bundles that tell the agent how and when to use tools.

**A skill provides:**
- Reasoning guidance
- Workflow logic
- Conventions
- Domain expertise

**Examples:**
- "How we write React components in this repo"
- "How to run the test suite correctly"
- "How to review a PR for security issues"
- "How to migrate a database schema safely"

**Properties:**
- Declarative
- Contextual
- Lazily loaded
- Human-authored or AI-generated
- No side effects on their own

**A skill:**
- Does not execute code
- Does not directly modify files
- Does not enforce rules
- Instructs the agent on how to act

> Think of skills as playbooks or recipes.

---

## Why Claude Code Splits Them

Claude Code intentionally separates **power** from **judgment**.

**If tools had knowledge:**
- Context would explode
- Everything would load all the time
- Mistakes would be harder to correct

**If skills could execute:**
- Security would be impossible
- Determinism would break
- Hooks couldn't intercept behavior

### The Split

| Aspect | Tools | Skills |
|--------|-------|--------|
| Executes code | Yes | No |
| Writes files | Yes | No |
| Contains reasoning | No | Yes |
| Teaches conventions | No | Yes |
| Lazy-loaded | No | Yes |
| Security-guarded | Yes | No |
| Versioned as docs | No | Yes |

---

## Progressive Disclosure

Skills scale through progressive loading:

1. Claude Code indexes all available skills (cheap metadata)
2. Exposes that index to the model
3. Loads only the relevant skill when reasoning demands it

This avoids:
- Bloated system prompts
- Irrelevant instructions
- Cross-domain contamination

Skills live in folders, not prompts.

---

## Hooks vs Skills

Easy to confuse, but distinct:

| Aspect | Skills | Hooks |
|--------|--------|-------|
| Role | Advise | Enforce |
| Nature | Guidance | Law |

**A skill says:** "After editing code, run tests."

**A hook says:** "You must run tests, or I block you."

---

## Mapping to AutoBuildr

### Tools in AutoBuildr
- Claude Code tools
- MCP feature tools
- Playwright
- Bash
- SDK executor

### Skills in AutoBuildr
- Agent personas (coder, auditor, test-runner)
- Project conventions
- Testing strategies
- Security practices
- Architectural patterns

### Agent Markdown Files Are Skill Bundles

The `.claude/agents/*.md` files are compound skills containing:
- Role definition
- Constraints
- Tool usage guidance
- Acceptance expectations

They do not execute anything themselves. They shape behavior.

---

## Where DSPy Fits

DSPy is neither a tool system nor a skill system.

> DSPy is a compiler for structured reasoning.

**In the architecture:**
- DSPy reasons over specs
- DSPy outputs structured artifacts
- Those artifacts become skills (agent definitions, test specs, workflows)

**DSPy should never:**
- Run Bash
- Write files directly
- Enforce security

**DSPy's job:** Produce correct, structured instructions.

---

## Why Octo Makes Sense

Octo is not a tool. Octo is not a skill.

> Octo is a skill factory.

It:
- Reasons about the project
- Decides what skills/agents are needed
- Emits agent definitions (markdown)
- Installs them into `.claude/agents/`

This is a higher-order capability that Claude Code explicitly supports.

---

## Summary

> **Tools give agents hands.**
> **Skills give agents judgment.**
> **Specs decide which judgment is needed.**

**AutoBuildr's job:** Generate the judgment (skills/agents)

**Claude Code's job:** Safely execute the hands (tools)
