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
