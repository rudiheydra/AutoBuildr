"""
DSPy Signatures for AutoBuildr
==============================

This module defines DSPy signatures for compiling tasks into AgentSpecs.

DSPy signatures are declarative specifications of input/output behavior for
language model calls. They define WHAT the model should accomplish, not HOW
to accomplish it.

Feature #50: DSPy SpecGenerationSignature Definition
"""
from __future__ import annotations

import dspy


class SpecGenerationSignature(dspy.Signature):
    """
    DSPy signature for compiling a task description into an AgentSpec.

    This signature enables a language model to analyze a task and generate
    all components needed for an AgentSpec, including:
    - A clear objective statement
    - Task-specific context as JSON
    - Tool policy defining allowed tools and forbidden patterns
    - Execution budget (turns and timeout)
    - Acceptance validators for verification

    The signature uses chain-of-thought reasoning to ensure high-quality
    spec generation by requiring the model to explain its decisions.

    Input Fields:
        task_description: Natural language description of the task to accomplish.
            Example: "Implement user authentication with email/password login"

        task_type: The category of task being performed. Must be one of:
            - coding: Implementation tasks (new features, bug fixes)
            - testing: Test creation and verification tasks
            - refactoring: Code restructuring without behavior change
            - documentation: Documentation creation/updates
            - audit: Code review and security analysis
            - custom: Tasks that don't fit other categories

        project_context: JSON string containing project-specific information such as:
            - project_name: Name of the project
            - file_paths: Relevant file paths for the task
            - feature_id: ID of the feature being implemented
            - existing_tools: Tools already available in the project
            - constraints: Any project-specific constraints

    Output Fields:
        reasoning: Chain-of-thought explanation of how the spec was derived.
            This helps ensure the model considers all aspects of the task
            before generating the spec components.

        objective: A clear, actionable goal statement for the agent.
            Should be specific enough to be verifiable but not prescriptive
            about implementation details.
            Example: "Implement secure user authentication with email/password
            credentials, including input validation and error handling."

        context_json: JSON string containing task-specific context data.
            Structure depends on task_type but typically includes:
            - target_files: Files the agent should modify
            - reference_files: Files for context (read-only)
            - feature_id: Linked feature ID if applicable
            - additional_instructions: Extra guidance

        tool_policy_json: JSON string defining the tool access policy.
            Structure:
            {
                "policy_version": "v1",
                "allowed_tools": ["tool_name", ...],
                "forbidden_patterns": ["pattern", ...],
                "tool_hints": {"tool_name": "usage hint", ...}
            }

        max_turns: Maximum number of API round-trips allowed.
            Typical ranges:
            - coding: 50-150 turns
            - testing: 30-100 turns
            - documentation: 20-50 turns
            - audit: 20-50 turns

        timeout_seconds: Maximum wall-clock time for execution.
            Range: 60-7200 seconds (1 minute to 2 hours)
            Typical: 1800 seconds (30 minutes)

        validators_json: JSON string containing acceptance validators.
            Array of validator objects, each with:
            {
                "type": "test_pass|file_exists|lint_clean|forbidden_patterns|custom",
                "config": {...},
                "weight": 1.0,
                "required": false
            }

    Example Usage:
        >>> import dspy
        >>> from api.dspy_signatures import SpecGenerationSignature
        >>>
        >>> # Configure DSPy with a language model
        >>> lm = dspy.LM("anthropic/claude-sonnet")
        >>> dspy.configure(lm=lm)
        >>>
        >>> # Create a ChainOfThought module with the signature
        >>> spec_generator = dspy.ChainOfThought(SpecGenerationSignature)
        >>>
        >>> # Generate a spec for a task
        >>> result = spec_generator(
        ...     task_description="Add user logout functionality",
        ...     task_type="coding",
        ...     project_context='{"project_name": "MyApp", "feature_id": 42}'
        ... )
        >>>
        >>> print(result.reasoning)  # Shows chain-of-thought
        >>> print(result.objective)   # The generated objective
    """

    # -------------------------------------------------------------------------
    # Input Fields
    # -------------------------------------------------------------------------

    task_description: str = dspy.InputField(
        desc=(
            "Natural language description of the task to accomplish. "
            "Should describe what needs to be done, not how to do it. "
            "Example: 'Implement user authentication with email/password login'"
        )
    )

    task_type: str = dspy.InputField(
        desc=(
            "The category of task: coding, testing, refactoring, documentation, "
            "audit, or custom. This determines default tool policies and budgets."
        )
    )

    project_context: str = dspy.InputField(
        desc=(
            "JSON string with project-specific context including project_name, "
            "file_paths, feature_id, existing_tools, and any constraints. "
            "Example: '{\"project_name\": \"AutoBuildr\", \"feature_id\": 50}'"
        )
    )

    # -------------------------------------------------------------------------
    # Output Fields
    # -------------------------------------------------------------------------

    reasoning: str = dspy.OutputField(
        desc=(
            "Chain-of-thought reasoning explaining the spec generation process. "
            "Should cover: 1) Understanding of the task, 2) Tool selection rationale, "
            "3) Budget considerations, 4) Acceptance criteria design. "
            "This ensures thorough analysis before generating spec components."
        )
    )

    objective: str = dspy.OutputField(
        desc=(
            "Clear, actionable goal statement for the agent. Should be specific "
            "enough to verify completion but not prescriptive about implementation. "
            "Example: 'Implement secure user authentication with email/password "
            "credentials, including input validation and error handling.'"
        )
    )

    context_json: str = dspy.OutputField(
        desc=(
            "JSON string with task-specific context. Structure: "
            "{\"target_files\": [...], \"reference_files\": [...], "
            "\"feature_id\": int|null, \"additional_instructions\": str|null}. "
            "Include any data the agent needs to accomplish the task."
        )
    )

    tool_policy_json: str = dspy.OutputField(
        desc=(
            "JSON string defining tool access policy. Structure: "
            "{\"policy_version\": \"v1\", \"allowed_tools\": [...], "
            "\"forbidden_patterns\": [...], \"tool_hints\": {...}}. "
            "Allowed tools should match task requirements; forbidden patterns "
            "should block dangerous operations."
        )
    )

    max_turns: int = dspy.OutputField(
        desc=(
            "Maximum API round-trips allowed (1-500). Consider task complexity: "
            "coding tasks typically need 50-150 turns, testing 30-100, "
            "documentation 20-50. Err on the side of more turns to avoid timeouts."
        )
    )

    timeout_seconds: int = dspy.OutputField(
        desc=(
            "Maximum wall-clock time in seconds (60-7200). Standard is 1800 (30 min). "
            "Complex coding tasks may need 3600 (1 hour). "
            "Simple documentation tasks may only need 900 (15 min)."
        )
    )

    validators_json: str = dspy.OutputField(
        desc=(
            "JSON array of acceptance validators. Each validator: "
            "{\"type\": \"test_pass|file_exists|lint_clean|forbidden_patterns|custom\", "
            "\"config\": {...}, \"weight\": 1.0, \"required\": false}. "
            "Include at least one validator. test_pass is common for coding tasks."
        )
    )


# =============================================================================
# Utility Functions
# =============================================================================

def get_spec_generator(
    lm: dspy.LM | None = None,
    use_chain_of_thought: bool = True
) -> dspy.Module:
    """
    Create a spec generator module using the SpecGenerationSignature.

    Args:
        lm: Optional language model to configure. If None, uses the
            currently configured DSPy language model.
        use_chain_of_thought: If True (default), use ChainOfThought for
            enhanced reasoning. If False, use basic Predict.

    Returns:
        A DSPy module configured for spec generation.

    Example:
        >>> generator = get_spec_generator()
        >>> result = generator(
        ...     task_description="Add logout button",
        ...     task_type="coding",
        ...     project_context='{}'
        ... )
    """
    if lm is not None:
        dspy.configure(lm=lm)

    if use_chain_of_thought:
        return dspy.ChainOfThought(SpecGenerationSignature)
    else:
        return dspy.Predict(SpecGenerationSignature)


def validate_spec_output(result: dspy.Prediction) -> dict[str, list[str]]:
    """
    Validate the output from a spec generation call.

    Args:
        result: The Prediction object from a spec generator call.

    Returns:
        Dictionary with 'errors' and 'warnings' lists.
        Empty lists indicate valid output.

    Example:
        >>> result = spec_generator(task_description="...", ...)
        >>> validation = validate_spec_output(result)
        >>> if validation['errors']:
        ...     print("Errors:", validation['errors'])
    """
    import json

    errors: list[str] = []
    warnings: list[str] = []

    # Check required string fields
    if not result.objective or not result.objective.strip():
        errors.append("objective is empty or missing")

    if not result.reasoning or not result.reasoning.strip():
        warnings.append("reasoning is empty (may indicate poor generation)")

    # Validate JSON fields
    json_fields = [
        ("context_json", result.context_json),
        ("tool_policy_json", result.tool_policy_json),
        ("validators_json", result.validators_json),
    ]

    for field_name, field_value in json_fields:
        if not field_value:
            errors.append(f"{field_name} is empty or missing")
            continue

        try:
            parsed = json.loads(field_value)

            # Field-specific validation
            if field_name == "tool_policy_json":
                if not isinstance(parsed.get("allowed_tools"), list):
                    errors.append(f"{field_name} must have 'allowed_tools' array")

            if field_name == "validators_json":
                if not isinstance(parsed, list):
                    errors.append(f"{field_name} must be an array")
                elif len(parsed) == 0:
                    warnings.append(f"{field_name} is empty (no validators defined)")

        except json.JSONDecodeError as e:
            errors.append(f"{field_name} is not valid JSON: {e}")

    # Validate numeric fields
    max_turns = result.max_turns
    if isinstance(max_turns, str):
        try:
            max_turns = int(max_turns)
        except ValueError:
            errors.append(f"max_turns must be an integer, got: {max_turns}")
            max_turns = None

    if max_turns is not None:
        if max_turns < 1:
            errors.append(f"max_turns must be >= 1, got: {max_turns}")
        elif max_turns > 500:
            errors.append(f"max_turns must be <= 500, got: {max_turns}")

    timeout_seconds = result.timeout_seconds
    if isinstance(timeout_seconds, str):
        try:
            timeout_seconds = int(timeout_seconds)
        except ValueError:
            errors.append(f"timeout_seconds must be an integer, got: {timeout_seconds}")
            timeout_seconds = None

    if timeout_seconds is not None:
        if timeout_seconds < 60:
            errors.append(f"timeout_seconds must be >= 60, got: {timeout_seconds}")
        elif timeout_seconds > 7200:
            errors.append(f"timeout_seconds must be <= 7200, got: {timeout_seconds}")

    return {"errors": errors, "warnings": warnings}


# =============================================================================
# OctoSpecGenerationSignature - Agent Definition Generation (Feature #182)
# =============================================================================


class OctoSpecGenerationSignature(dspy.Signature):
    """
    DSPy signature for Octo agent generation from project context.

    Feature #182: Octo DSPy signature for AgentSpec generation

    This signature enables Octo to analyze project context and generate
    complete AgentSpec definitions. Unlike SpecGenerationSignature which
    compiles individual tasks, this signature creates agent definitions
    from higher-level project requirements and capability analysis.

    The signature produces all fields needed to create specialized agents:
    - agent_name: Unique identifier for the agent (machine-readable)
    - role: Human-readable description of the agent's purpose
    - tools: List of MCP tools the agent can use
    - skills: Domain-specific capabilities the agent brings
    - model: Recommended Claude model for the agent
    - responsibilities: Key duties and behaviors
    - acceptance_contract: How to verify the agent's work

    Input Fields:
        project_context: JSON string containing:
            - name: Project name
            - tech_stack: List of technologies used
            - app_spec_summary: Overview of what the app does
            - existing_features: Summary of features to implement
            - execution_environment: Runtime context (browser, api, cli)

        capabilities_needed: JSON array of capabilities the agent must have.
            Example: ["playwright_e2e", "browser_automation", "screenshot_verification"]
            These map to specific tool policies and skill requirements.

        constraints: JSON string containing limits and restrictions:
            - max_turns: Maximum turns for agent execution
            - timeout_seconds: Maximum wall-clock time
            - model_preference: Preferred Claude model (sonnet, opus, haiku)
            - forbidden_patterns: Patterns to block in tool arguments
            - allowed_directories: Sandboxed paths for file operations

    Output Fields:
        reasoning: Chain-of-thought explanation of agent design decisions.
            Covers: capability analysis, tool selection, model choice, acceptance design.
            Ensures auditability of how the agent spec was derived.

        agent_name: Unique machine-readable identifier for the agent.
            Format: lowercase with hyphens, e.g., "playwright-e2e-tester"
            Must be URL-safe and <= 100 characters.

        role: Human-readable description of what the agent does.
            Example: "End-to-end UI testing agent using Playwright for browser automation"
            Shown in UI and used for display_name derivation.

        tools_json: JSON array of MCP tool names the agent can use.
            Example: ["mcp__playwright__browser_navigate", "mcp__playwright__browser_click"]
            These form the agent's tool_policy.allowed_tools.

        skills_json: JSON array of domain skills/capabilities.
            Example: ["browser_automation", "visual_regression", "accessibility_testing"]
            Used for capability matching and agent selection.

        model: Recommended Claude model for execution.
            One of: "sonnet", "opus", "haiku"
            Consider task complexity: opus for complex reasoning, haiku for simple tasks.

        responsibilities_json: JSON array of key duties and behaviors.
            Example: ["Execute E2E test scenarios", "Capture screenshots", "Report failures"]
            Informs the agent's objective and system prompt.

        acceptance_contract_json: JSON object defining verification criteria.
            Structure: {
                "gate_mode": "all_pass|any_pass|weighted",
                "validators": [
                    {"type": "test_pass|file_exists|...", "config": {...}, "weight": 1.0, "required": false}
                ],
                "min_score": null  # for weighted mode
            }
            Used to create AcceptanceSpec for the agent.

    Example Usage:
        >>> import dspy
        >>> from api.dspy_signatures import OctoSpecGenerationSignature
        >>>
        >>> lm = dspy.LM("anthropic/claude-sonnet")
        >>> dspy.configure(lm=lm)
        >>>
        >>> agent_generator = dspy.ChainOfThought(OctoSpecGenerationSignature)
        >>> result = agent_generator(
        ...     project_context='{"name": "MyApp", "tech_stack": ["React", "FastAPI"]}',
        ...     capabilities_needed='["e2e_testing", "browser_automation"]',
        ...     constraints='{"max_turns": 100, "model_preference": "sonnet"}'
        ... )
        >>>
        >>> print(result.agent_name)  # "playwright-e2e-tester"
        >>> print(result.role)  # "End-to-end UI testing agent..."
    """

    # -------------------------------------------------------------------------
    # Input Fields
    # -------------------------------------------------------------------------

    project_context: str = dspy.InputField(
        desc=(
            "JSON string with project context: name (project name), tech_stack "
            "(list of technologies), app_spec_summary (what the app does), "
            "existing_features (summary of features), execution_environment "
            "(browser, api, cli). Example: '{\"name\": \"MyApp\", \"tech_stack\": [\"React\"]}'"
        )
    )

    capabilities_needed: str = dspy.InputField(
        desc=(
            "JSON array of capabilities the agent must provide. Each capability "
            "maps to specific tools and skills. Examples: 'e2e_testing', "
            "'browser_automation', 'api_testing', 'security_audit'. "
            "Example: '[\"playwright_e2e\", \"visual_regression\"]'"
        )
    )

    constraints: str = dspy.InputField(
        desc=(
            "JSON string with execution constraints: max_turns (1-500), "
            "timeout_seconds (60-7200), model_preference (sonnet|opus|haiku), "
            "forbidden_patterns (list of blocked patterns), allowed_directories "
            "(sandboxed paths). Example: '{\"max_turns\": 100, \"model_preference\": \"sonnet\"}'"
        )
    )

    # -------------------------------------------------------------------------
    # Output Fields
    # -------------------------------------------------------------------------

    reasoning: str = dspy.OutputField(
        desc=(
            "Chain-of-thought reasoning explaining agent design decisions. "
            "Cover: 1) Capability analysis and gaps, 2) Tool selection rationale, "
            "3) Model choice based on task complexity, 4) Acceptance criteria design, "
            "5) How constraints affect the design. This ensures full auditability."
        )
    )

    agent_name: str = dspy.OutputField(
        desc=(
            "Unique machine-readable identifier for the agent. Must be lowercase "
            "with hyphens, URL-safe, and <= 100 characters. Follow pattern: "
            "[capability]-[role]-[suffix]. Examples: 'playwright-e2e-tester', "
            "'api-integration-tester', 'security-audit-agent'"
        )
    )

    role: str = dspy.OutputField(
        desc=(
            "Human-readable description of the agent's purpose (1-2 sentences). "
            "Explains what the agent does and its primary responsibility. "
            "Example: 'End-to-end UI testing agent using Playwright for browser "
            "automation, screenshot capture, and visual regression testing.'"
        )
    )

    tools_json: str = dspy.OutputField(
        desc=(
            "JSON array of MCP tool names the agent can use. Include full MCP "
            "prefixes (mcp__server__tool_name). Match tools to capabilities. "
            "Example: '[\"mcp__playwright__browser_navigate\", \"mcp__playwright__browser_click\"]'. "
            "For feature management: '[\"mcp__features__feature_get_by_id\"]'"
        )
    )

    skills_json: str = dspy.OutputField(
        desc=(
            "JSON array of domain skills/capabilities the agent possesses. "
            "These are semantic labels for what the agent can do, used for "
            "capability matching. Examples: 'browser_automation', 'visual_testing', "
            "'api_integration', 'security_scanning'. Example: '[\"e2e_testing\", \"screenshots\"]'"
        )
    )

    model: str = dspy.OutputField(
        desc=(
            "Recommended Claude model for this agent. One of: 'sonnet', 'opus', 'haiku'. "
            "Choose based on task complexity: opus for complex multi-step reasoning, "
            "sonnet for balanced tasks, haiku for simple/fast operations. "
            "Default to 'sonnet' unless constraints specify otherwise."
        )
    )

    responsibilities_json: str = dspy.OutputField(
        desc=(
            "JSON array of key duties and expected behaviors. Each item is a "
            "concise statement of what the agent must do. These inform the agent's "
            "objective and system prompt. Example: '[\"Execute E2E test scenarios\", "
            "\"Capture screenshots at key states\", \"Report test failures clearly\"]'"
        )
    )

    acceptance_contract_json: str = dspy.OutputField(
        desc=(
            "JSON object defining how to verify the agent's work. Structure: "
            "{\"gate_mode\": \"all_pass|any_pass|weighted\", \"validators\": "
            "[{\"type\": \"test_pass|file_exists|...\", \"config\": {...}, "
            "\"weight\": 1.0, \"required\": false}], \"min_score\": null}. "
            "Must include at least one validator."
        )
    )


# =============================================================================
# Octo Utility Functions
# =============================================================================

def get_octo_spec_generator(
    lm: dspy.LM | None = None,
    use_chain_of_thought: bool = True
) -> dspy.Module:
    """
    Create an agent spec generator module using OctoSpecGenerationSignature.

    Args:
        lm: Optional language model to configure. If None, uses the
            currently configured DSPy language model.
        use_chain_of_thought: If True (default), use ChainOfThought for
            enhanced reasoning. If False, use basic Predict.

    Returns:
        A DSPy module configured for Octo agent spec generation.

    Example:
        >>> generator = get_octo_spec_generator()
        >>> result = generator(
        ...     project_context='{"name": "MyApp"}',
        ...     capabilities_needed='["e2e_testing"]',
        ...     constraints='{}'
        ... )
    """
    if lm is not None:
        dspy.configure(lm=lm)

    if use_chain_of_thought:
        return dspy.ChainOfThought(OctoSpecGenerationSignature)
    else:
        return dspy.Predict(OctoSpecGenerationSignature)


def validate_octo_spec_output(result: dspy.Prediction) -> dict[str, list[str]]:
    """
    Validate the output from an Octo spec generation call.

    Validates that all output fields conform to the AgentSpec schema
    requirements, including JSON parsing and constraint validation.

    Args:
        result: The Prediction object from an Octo spec generator call.

    Returns:
        Dictionary with 'errors' and 'warnings' lists.
        Empty lists indicate valid output.

    Example:
        >>> result = octo_generator(project_context="...", ...)
        >>> validation = validate_octo_spec_output(result)
        >>> if validation['errors']:
        ...     print("Errors:", validation['errors'])
    """
    import json
    import re

    errors: list[str] = []
    warnings: list[str] = []

    # -------------------------------------------------------------------------
    # Validate reasoning (chain-of-thought)
    # -------------------------------------------------------------------------
    if not result.reasoning or not result.reasoning.strip():
        warnings.append("reasoning is empty (may indicate poor generation)")

    # -------------------------------------------------------------------------
    # Validate agent_name
    # -------------------------------------------------------------------------
    agent_name = getattr(result, 'agent_name', None)
    if not agent_name or not agent_name.strip():
        errors.append("agent_name is empty or missing")
    else:
        # Must be URL-safe: lowercase, hyphens, underscores, digits
        if not re.match(r'^[a-z0-9][a-z0-9\-_]*[a-z0-9]$|^[a-z0-9]$', agent_name):
            errors.append(
                f"agent_name must be lowercase alphanumeric with hyphens/underscores, got: {agent_name}"
            )
        if len(agent_name) > 100:
            errors.append(f"agent_name must be <= 100 characters, got: {len(agent_name)}")

    # -------------------------------------------------------------------------
    # Validate role
    # -------------------------------------------------------------------------
    role = getattr(result, 'role', None)
    if not role or not role.strip():
        errors.append("role is empty or missing")

    # -------------------------------------------------------------------------
    # Validate model
    # -------------------------------------------------------------------------
    model = getattr(result, 'model', None)
    valid_models = {'sonnet', 'opus', 'haiku'}
    if not model:
        errors.append("model is empty or missing")
    elif model.lower() not in valid_models:
        errors.append(f"model must be one of {valid_models}, got: {model}")

    # -------------------------------------------------------------------------
    # Validate JSON array fields
    # -------------------------------------------------------------------------
    json_array_fields = [
        ("tools_json", result.tools_json, "tools"),
        ("skills_json", result.skills_json, "skills"),
        ("responsibilities_json", result.responsibilities_json, "responsibilities"),
    ]

    for field_name, field_value, display_name in json_array_fields:
        if not field_value:
            errors.append(f"{field_name} is empty or missing")
            continue

        try:
            parsed = json.loads(field_value)
            if not isinstance(parsed, list):
                errors.append(f"{field_name} must be a JSON array")
            elif len(parsed) == 0:
                warnings.append(f"{field_name} is empty (no {display_name} defined)")
            else:
                # Validate each item is a string
                for i, item in enumerate(parsed):
                    if not isinstance(item, str):
                        errors.append(f"{field_name}[{i}] must be a string")
        except json.JSONDecodeError as e:
            errors.append(f"{field_name} is not valid JSON: {e}")

    # -------------------------------------------------------------------------
    # Validate acceptance_contract_json (complex object)
    # -------------------------------------------------------------------------
    acceptance_json = getattr(result, 'acceptance_contract_json', None)
    if not acceptance_json:
        errors.append("acceptance_contract_json is empty or missing")
    else:
        try:
            contract = json.loads(acceptance_json)
            if not isinstance(contract, dict):
                errors.append("acceptance_contract_json must be a JSON object")
            else:
                # Validate gate_mode
                gate_mode = contract.get("gate_mode")
                valid_gate_modes = {"all_pass", "any_pass", "weighted"}
                if gate_mode not in valid_gate_modes:
                    errors.append(
                        f"acceptance_contract_json.gate_mode must be one of {valid_gate_modes}, got: {gate_mode}"
                    )

                # Validate validators array
                validators = contract.get("validators")
                if not isinstance(validators, list):
                    errors.append("acceptance_contract_json.validators must be an array")
                elif len(validators) == 0:
                    warnings.append("acceptance_contract_json has no validators defined")
                else:
                    valid_validator_types = {
                        "test_pass", "file_exists", "lint_clean", "forbidden_patterns", "custom"
                    }
                    for i, v in enumerate(validators):
                        if not isinstance(v, dict):
                            errors.append(f"validators[{i}] must be an object")
                            continue
                        v_type = v.get("type")
                        if v_type not in valid_validator_types:
                            errors.append(
                                f"validators[{i}].type must be one of {valid_validator_types}, got: {v_type}"
                            )
                        if "config" not in v:
                            warnings.append(f"validators[{i}] missing 'config' field")

                # Validate min_score for weighted mode
                if gate_mode == "weighted":
                    min_score = contract.get("min_score")
                    if min_score is None:
                        warnings.append("weighted gate_mode should have min_score set")
                    elif not isinstance(min_score, (int, float)) or not (0.0 <= min_score <= 1.0):
                        errors.append(
                            f"min_score must be a number between 0.0 and 1.0, got: {min_score}"
                        )

        except json.JSONDecodeError as e:
            errors.append(f"acceptance_contract_json is not valid JSON: {e}")

    return {"errors": errors, "warnings": warnings}


def convert_octo_output_to_agent_spec_dict(result: dspy.Prediction) -> dict:
    """
    Convert validated Octo output to an AgentSpec-compatible dictionary.

    This function transforms the DSPy signature output into the format
    expected by AgentSpec creation APIs.

    Args:
        result: A validated Prediction from OctoSpecGenerationSignature

    Returns:
        Dictionary suitable for AgentSpec creation with keys:
        - name, display_name, icon, objective, task_type, context,
        - tool_policy, max_turns, timeout_seconds, tags
        - acceptance_spec (nested dict with validators, gate_mode, etc.)

    Raises:
        ValueError: If the result has not been validated or contains errors

    Example:
        >>> result = octo_generator(...)
        >>> validation = validate_octo_spec_output(result)
        >>> if not validation['errors']:
        ...     spec_dict = convert_octo_output_to_agent_spec_dict(result)
        ...     # Use spec_dict to create AgentSpec
    """
    import json

    # Parse JSON fields
    tools = json.loads(result.tools_json)
    skills = json.loads(result.skills_json)
    responsibilities = json.loads(result.responsibilities_json)
    acceptance_contract = json.loads(result.acceptance_contract_json)

    # Build objective from role and responsibilities
    objective = f"{result.role}\n\nKey responsibilities:\n"
    objective += "\n".join(f"- {r}" for r in responsibilities)

    # Map model name to task_type (best effort)
    model_to_task_type = {
        "opus": "coding",      # Complex tasks
        "sonnet": "testing",   # Balanced tasks
        "haiku": "audit",      # Simple/fast tasks
    }
    task_type = model_to_task_type.get(result.model.lower(), "custom")

    # Build tool policy
    tool_policy = {
        "policy_version": "v1",
        "allowed_tools": tools,
        "forbidden_patterns": [],
        "tool_hints": {},
    }

    # Build result dictionary
    spec_dict = {
        "name": result.agent_name,
        "display_name": result.role[:255] if len(result.role) > 255 else result.role,
        "icon": _derive_icon_from_skills(skills),
        "objective": objective,
        "task_type": task_type,
        "context": {
            "skills": skills,
            "reasoning": result.reasoning,
            "model_preference": result.model,
        },
        "tool_policy": tool_policy,
        "max_turns": 100,  # Default, can be overridden by constraints
        "timeout_seconds": 1800,  # Default
        "tags": skills[:5],  # Use first 5 skills as tags
        "acceptance_spec": {
            "gate_mode": acceptance_contract.get("gate_mode", "all_pass"),
            "validators": acceptance_contract.get("validators", []),
            "min_score": acceptance_contract.get("min_score"),
            "retry_policy": "none",
            "max_retries": 0,
        }
    }

    return spec_dict


def _derive_icon_from_skills(skills: list[str]) -> str:
    """
    Derive an appropriate icon/emoji from agent skills.

    Args:
        skills: List of skill strings

    Returns:
        Emoji or icon identifier appropriate for the agent
    """
    skill_set = {s.lower() for s in skills}

    # Check for specific skill patterns
    if any("test" in s or "e2e" in s for s in skill_set):
        return "🧪"  # Test tube for testing agents
    if any("browser" in s or "playwright" in s or "ui" in s for s in skill_set):
        return "🌐"  # Globe for browser/UI agents
    if any("api" in s or "http" in s or "rest" in s for s in skill_set):
        return "🔌"  # Plug for API agents
    if any("security" in s or "audit" in s or "scan" in s for s in skill_set):
        return "🔒"  # Lock for security agents
    if any("doc" in s or "readme" in s or "wiki" in s for s in skill_set):
        return "📝"  # Memo for documentation agents
    if any("refactor" in s or "clean" in s for s in skill_set):
        return "🔧"  # Wrench for refactoring agents
    if any("deploy" in s or "release" in s or "ci" in s for s in skill_set):
        return "🚀"  # Rocket for deployment agents
    if any("monitor" in s or "alert" in s or "metrics" in s for s in skill_set):
        return "📊"  # Chart for monitoring agents

    return "🤖"  # Default robot emoji


# =============================================================================
# Constants
# =============================================================================

# Valid task types (must match api/agentspec_models.py)
VALID_TASK_TYPES = frozenset([
    "coding",
    "testing",
    "refactoring",
    "documentation",
    "audit",
    "custom",
])

# Default budgets by task type
DEFAULT_BUDGETS: dict[str, dict[str, int]] = {
    "coding": {"max_turns": 100, "timeout_seconds": 1800},
    "testing": {"max_turns": 75, "timeout_seconds": 1200},
    "refactoring": {"max_turns": 100, "timeout_seconds": 1800},
    "documentation": {"max_turns": 40, "timeout_seconds": 900},
    "audit": {"max_turns": 50, "timeout_seconds": 1200},
    "custom": {"max_turns": 75, "timeout_seconds": 1800},
}

# Valid models for Octo agent generation
VALID_AGENT_MODELS = frozenset(["sonnet", "opus", "haiku"])

# Valid gate modes for acceptance contracts
VALID_GATE_MODES = frozenset(["all_pass", "any_pass", "weighted"])

# Valid validator types for acceptance contracts
VALID_OCTO_VALIDATOR_TYPES = frozenset([
    "test_pass",
    "file_exists",
    "lint_clean",
    "forbidden_patterns",
    "custom",
])
