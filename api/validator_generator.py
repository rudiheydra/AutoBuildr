"""
Validator Generator Module
==========================

Generate AcceptanceSpec validators from feature verification steps by parsing step text.

This module implements Feature #55 - intelligent parsing of feature step text to
automatically generate appropriate validators:
- test_pass: When step contains run/execute keywords
- file_exists: When step mentions file/path
- forbidden_patterns: When step mentions "should not"/"must not"

The generator analyzes step text using regex patterns to:
1. Identify validator type from step semantics
2. Extract commands, paths, or patterns from step text
3. Set appropriate timeouts for test_pass validators
4. Return an array of validator configs ready for AcceptanceSpec

Example:
    ```python
    from api.validator_generator import generate_validators_from_steps

    steps = [
        "Run pytest tests/ to verify functionality",
        "File config.json should exist in project root",
        "Output should not contain any hardcoded passwords"
    ]

    validators = generate_validators_from_steps(steps)
    # Returns: [
    #     {"type": "test_pass", "config": {"command": "pytest tests/", ...}},
    #     {"type": "file_exists", "config": {"path": "config.json", ...}},
    #     {"type": "forbidden_patterns", "config": {"patterns": [...], ...}}
    # ]
    ```
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants - Keywords and Patterns
# =============================================================================

# Keywords that indicate a command should be run (test_pass validator)
EXECUTE_KEYWORDS = [
    r"\brun\b",
    r"\bexecute\b",
    r"\bexec\b",
    r"\binvoke\b",
    r"\bcall\b",
    r"\bstart\b",
    r"\blaunch\b",
    r"\btrigger\b",
    # Test-related
    r"\btest\b",
    r"\bpytest\b",
    r"\bvitest\b",
    r"\bjest\b",
    r"\bmocha\b",
    r"\bnpm test\b",
    r"\bnpm run\b",
    r"\byarn test\b",
    r"\byarn run\b",
    r"\bpnpm test\b",
    r"\bpnpm run\b",
    # Build-related
    r"\bbuild\b",
    r"\bcompile\b",
    r"\bmake\b",
    # Check-related
    r"\bcheck\b",
    r"\bverify\b",
    r"\bvalidate\b",
    r"\blint\b",
    r"\bformat\b",
    r"\btypecheck\b",
    r"\btype-check\b",
]

# Keywords that indicate a file/path check (file_exists validator)
FILE_KEYWORDS = [
    r"\bfile\b",
    r"\bpath\b",
    r"\bdirectory\b",
    r"\bfolder\b",
    r"\bexist[s]?\b",
    r"\bcreated?\b",
    r"\bgenerated?\b",
    r"\bpresent\b",
    r"\bfound\b",
    r"\.py\b",
    r"\.ts\b",
    r"\.tsx\b",
    r"\.js\b",
    r"\.jsx\b",
    r"\.json\b",
    r"\.yaml\b",
    r"\.yml\b",
    r"\.md\b",
    r"\.txt\b",
    r"\.sh\b",
    r"\.css\b",
    r"\.html\b",
    r"\.sql\b",
]

# Keywords that indicate forbidden content (forbidden_patterns validator)
FORBIDDEN_KEYWORDS = [
    r"\bshould\s+not\b",
    r"\bmust\s+not\b",
    r"\bshouldn'?t\b",
    r"\bmustn'?t\b",
    r"\bcannot\b",
    r"\bcan'?t\b",
    r"\bno\s+",
    r"\bnot\s+contain\b",
    r"\bnot\s+include\b",
    r"\bnot\s+have\b",
    r"\bwithout\b",
    r"\bforbidden\b",
    r"\bprohibited\b",
    r"\bban(?:ned)?\b",
    r"\bdisallow(?:ed)?\b",
    r"\bdanger(?:ous)?\b",
    r"\bsecret\b",
    r"\bpassword\b",
    r"\bcredential\b",
    r"\bhardcoded?\b",
    r"\bhard-?coded?\b",
]

# Patterns to extract commands from step text
COMMAND_PATTERNS = [
    # Backtick-enclosed commands: `npm run test`
    r"`([^`]+)`",
    # Single-quoted commands: 'npm run test'
    r"'([^']+)'",
    # Double-quoted commands: "npm run test"
    r'"([^"]+)"',
    # Run/execute followed by command: run pytest tests/
    r"\b(?:run|execute|exec)\s+([a-zA-Z0-9_.\-\/\s]+?)(?:\s+(?:to|for|and|with)|$|\.|,)",
    # npm/yarn/pnpm commands: npm test, yarn run build
    r"\b((?:npm|yarn|pnpm)\s+(?:run\s+)?[a-zA-Z0-9_\-]+)",
    # pytest commands: pytest tests/ -v
    r"\b(pytest\s+[a-zA-Z0-9_.\/\-\s]+)",
    # python commands: python -m pytest
    r"\b(python\s+[\-\w\.\/\s]+)",
    # make commands: make build
    r"\b(make\s+[a-zA-Z0-9_\-]+)",
    # Bash scripts: ./init.sh
    r"\b(\./[a-zA-Z0-9_\-\.]+\.sh)",
]

# Patterns to extract file paths from step text
PATH_PATTERNS = [
    # Backtick-enclosed paths: `src/config.json`
    r"`([^`]+\.\w+)`",
    # Paths with common extensions
    r"([a-zA-Z0-9_./\-]+\.(?:py|ts|tsx|js|jsx|json|yaml|yml|md|txt|sh|css|html|sql|toml|cfg|ini|env|gitignore))\b",
    # Directory paths: src/components/, api/models/
    r"\b([a-zA-Z0-9_./\-]+/)(?:\s|$|\.|,)",
    # Paths starting with ./ or /
    r"([./][a-zA-Z0-9_./\-]+)",
    # Common project files
    r"\b((?:init|setup|config|package|tsconfig|pyproject|requirements)\.(?:sh|py|js|ts|json|toml|txt))\b",
]

# Patterns to extract forbidden content from step text
FORBIDDEN_CONTENT_PATTERNS = [
    # "should not contain X"
    r"(?:should|must)\s+not\s+(?:contain|include|have)\s+(.+?)(?:\s+in\s|\s*$|\.|,)",
    # "no X"
    r"\bno\s+(.+?)(?:\s+in\s|\s+should|\s*$|\.|,)",
    # "without X"
    r"\bwithout\s+(.+?)(?:\s+in\s|\s*$|\.|,)",
    # "forbidden X"
    r"\bforbidden\s+(.+?)(?:\s+in\s|\s*$|\.|,)",
    # Quoted forbidden content
    r'"([^"]+)"',
    r"'([^']+)'",
    r"`([^`]+)`",
]


# =============================================================================
# Default Timeout Configuration
# =============================================================================

# Default timeouts for different command types (in seconds)
DEFAULT_TIMEOUT = 60

COMMAND_TIMEOUTS = {
    # Fast commands
    "lint": 30,
    "format": 30,
    "typecheck": 60,
    "type-check": 60,
    # Medium commands
    "test": 120,
    "pytest": 120,
    "jest": 120,
    "vitest": 60,
    "mocha": 120,
    # Slow commands
    "build": 180,
    "compile": 180,
    "install": 300,
}


# =============================================================================
# ValidatorConfig Dataclass
# =============================================================================

@dataclass
class ValidatorConfig:
    """
    Configuration for a generated validator.

    Attributes:
        validator_type: Type of validator (test_pass, file_exists, forbidden_patterns)
        config: Validator-specific configuration
        weight: Weight for weighted gate mode (0.0 to 1.0)
        required: Whether this validator is required to pass
        step_index: Original step index (0-based)
        step_text: Original step text
        confidence: Confidence score for this match (0.0 to 1.0)
    """
    validator_type: str
    config: dict[str, Any]
    weight: float = 1.0
    required: bool = False
    step_index: int = 0
    step_text: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for AcceptanceSpec validators array."""
        return {
            "type": self.validator_type,
            "config": self.config,
            "weight": self.weight,
            "required": self.required,
        }


# =============================================================================
# ValidatorGenerator Class
# =============================================================================

class ValidatorGenerator:
    """
    Generate validators from feature verification steps.

    The ValidatorGenerator parses feature step text to automatically
    create appropriate validators based on the step semantics:

    1. **test_pass**: For steps mentioning run/execute commands
    2. **file_exists**: For steps mentioning file paths
    3. **forbidden_patterns**: For steps with "should not" / "must not"

    The generator uses regex patterns to:
    - Identify validator type from keywords
    - Extract commands, paths, or patterns
    - Set appropriate timeouts

    Example:
        ```python
        generator = ValidatorGenerator()

        validators = generator.generate_from_steps([
            "Run pytest tests/ to verify all tests pass",
            "File api/models.py should exist",
            "Output should not contain passwords"
        ])

        for v in validators:
            print(f"{v.validator_type}: {v.config}")
        ```
    """

    def __init__(
        self,
        *,
        default_timeout: int = DEFAULT_TIMEOUT,
        include_fallback: bool = True,
    ):
        """
        Initialize the ValidatorGenerator.

        Args:
            default_timeout: Default timeout for test_pass validators
            include_fallback: Whether to include a fallback generic validator
                            for steps that don't match any pattern
        """
        self._default_timeout = default_timeout
        self._include_fallback = include_fallback

    def generate_from_steps(
        self,
        steps: list[str],
        *,
        feature_id: int | None = None,
    ) -> list[ValidatorConfig]:
        """
        Generate validators from a list of feature steps.

        This is the main entry point. It analyzes each step and generates
        the most appropriate validator based on the step text.

        Args:
            steps: List of feature verification step strings
            feature_id: Optional feature ID for context

        Returns:
            List of ValidatorConfig objects for each step
        """
        validators = []

        for index, step in enumerate(steps):
            step_validators = self._analyze_step(step, index, feature_id)
            validators.extend(step_validators)

        _logger.info(
            "Generated %d validators from %d steps",
            len(validators),
            len(steps)
        )

        return validators

    def _analyze_step(
        self,
        step: str,
        index: int,
        feature_id: int | None,
    ) -> list[ValidatorConfig]:
        """
        Analyze a single step and generate appropriate validators.

        The step is analyzed with refined priority logic:
        1. Check for file existence patterns FIRST (including "should not exist")
        2. Check for forbidden patterns keywords (excluding file existence)
        3. Check for command execution patterns ("run", "execute")
        4. Fall back to generic validators

        Args:
            step: The step text to analyze
            index: Step index (0-based)
            feature_id: Optional feature ID

        Returns:
            List of ValidatorConfig objects (usually 1, but may be 0 or more)
        """
        step_lower = step.lower()
        validators = []

        # Step 1: Analyze for validator hints (Feature #55 Step 1)
        has_forbidden = self._has_forbidden_keywords(step_lower)
        has_execute = self._has_execute_keywords(step_lower)
        has_file = self._has_file_keywords(step_lower)

        # Additional refined checks
        is_file_existence_check = self._is_file_existence_step(step_lower)
        is_command_execution = self._is_command_execution_step(step_lower)

        _logger.debug(
            "Step %d analysis: forbidden=%s, execute=%s, file=%s, file_existence=%s, cmd_exec=%s - '%s'",
            index, has_forbidden, has_execute, has_file, is_file_existence_check, is_command_execution, step[:50]
        )

        # PRIORITY 1: Check for file existence patterns
        # This handles both "should exist" and "should not exist"
        # Step 3: If step mentions file/path with existence check, create file_exists validator
        if is_file_existence_check:
            validator = self._create_file_exists_validator(
                step, index, feature_id
            )
            if validator:
                validators.append(validator)
                _logger.debug("Created file_exists validator for step %d", index)
                return validators  # File existence takes priority, exit early

        # PRIORITY 2: If step mentions "should not"/"must not" (but not file existence),
        # create forbidden_patterns
        # Step 4: If step mentions should not/must not, create forbidden_patterns
        if has_forbidden and not is_file_existence_check:
            validator = self._create_forbidden_patterns_validator(
                step, index, feature_id
            )
            if validator:
                validators.append(validator)
                _logger.debug("Created forbidden_patterns validator for step %d", index)
                return validators  # Forbidden patterns, exit early

        # PRIORITY 3: If step is clearly a command execution, create test_pass validator
        # Step 2: If step contains run/execute, create test_pass validator
        if is_command_execution:
            validator = self._create_test_pass_validator(
                step, index, feature_id
            )
            if validator:
                validators.append(validator)
                _logger.debug("Created test_pass validator for step %d", index)
                return validators  # Command execution, exit early

        # PRIORITY 4: If step mentions file/path without specific action
        if has_file and not has_execute:
            validator = self._create_file_exists_validator(
                step, index, feature_id
            )
            if validator:
                validators.append(validator)
                _logger.debug("Created file_exists validator for step %d", index)
                return validators

        # If no specific validator was created and fallback is enabled,
        # create a generic validator for manual verification
        if not validators and self._include_fallback:
            validators.append(self._create_fallback_validator(
                step, index, feature_id
            ))
            _logger.debug("Created fallback validator for step %d", index)

        return validators

    def _is_file_existence_step(self, step_lower: str) -> bool:
        """
        Check if the step is specifically about file/directory existence.

        This detects patterns like:
        - "file X should exist"
        - "file X should not exist"
        - "X exists"
        - "verify X exists"
        """
        # Patterns that indicate file existence checks
        existence_patterns = [
            r"\bexist[s]?\b",
            r"\bpresent\b",
            r"\bfound\b",
            r"\bcreated\b",
            r"\bgenerated\b",
            r"\bfile\s+\S+\s+should",  # "file X should"
            r"\bpath\s+\S+\s+should",   # "path X should"
            r"\bdirectory\s+\S+\s+should",  # "directory X should"
            r"\bfolder\s+\S+\s+should",     # "folder X should"
        ]

        for pattern in existence_patterns:
            if re.search(pattern, step_lower):
                return True
        return False

    def _is_command_execution_step(self, step_lower: str) -> bool:
        """
        Check if the step is specifically about running a command.

        This detects explicit command execution patterns like:
        - "run pytest ..."
        - "execute npm ..."
        - Commands in backticks
        """
        # Strong indicators of command execution
        command_patterns = [
            r"\brun\s+[`'\"]?[a-z]",      # "run X" where X starts with a letter
            r"\bexecute\s+[`'\"]?[a-z]",  # "execute X"
            r"\bexec\s+[`'\"]?[a-z]",     # "exec X"
            r"\binvoke\s+[`'\"]?[a-z]",   # "invoke X"
            r"`[^`]+`",                    # Backtick-enclosed commands
            r"\bnpm\s+(?:run\s+)?test",   # npm test or npm run test
            r"\byarn\s+(?:run\s+)?test",  # yarn test
            r"\bpnpm\s+(?:run\s+)?test",  # pnpm test
            r"\bpytest\s+",               # pytest with args
            r"\bpython\s+[`\-\w]",        # python with script/args
            r"\bmake\s+\w",               # make target
            r"\./\w+\.sh\b",              # ./script.sh
        ]

        for pattern in command_patterns:
            if re.search(pattern, step_lower):
                return True
        return False

    def _has_execute_keywords(self, step_lower: str) -> bool:
        """Check if step contains execute-related keywords."""
        for pattern in EXECUTE_KEYWORDS:
            if re.search(pattern, step_lower):
                return True
        return False

    def _has_file_keywords(self, step_lower: str) -> bool:
        """Check if step contains file/path-related keywords."""
        for pattern in FILE_KEYWORDS:
            if re.search(pattern, step_lower):
                return True
        return False

    def _has_forbidden_keywords(self, step_lower: str) -> bool:
        """Check if step contains forbidden-related keywords."""
        for pattern in FORBIDDEN_KEYWORDS:
            if re.search(pattern, step_lower):
                return True
        return False

    # =========================================================================
    # test_pass Validator Creation
    # =========================================================================

    def _create_test_pass_validator(
        self,
        step: str,
        index: int,
        feature_id: int | None,
    ) -> ValidatorConfig | None:
        """
        Create a test_pass validator from a step.

        Extracts the command from the step text and sets appropriate timeout.

        Args:
            step: The step text
            index: Step index
            feature_id: Optional feature ID

        Returns:
            ValidatorConfig or None if command extraction fails
        """
        # Step 5: Extract command from step text
        command = self._extract_command(step)

        if not command:
            _logger.debug("Could not extract command from step: %s", step[:50])
            return None

        # Step 6: Set appropriate timeout for test_pass validators
        timeout = self._determine_timeout(command)

        config = {
            "command": command,
            "expected_exit_code": 0,
            "timeout_seconds": timeout,
            "description": step,
        }

        return ValidatorConfig(
            validator_type="test_pass",
            config=config,
            weight=1.0,
            required=False,
            step_index=index,
            step_text=step,
            confidence=0.8,  # Medium-high confidence for command extraction
        )

    def _extract_command(self, step: str) -> str | None:
        """
        Extract a command from step text.

        Tries multiple patterns to find the most likely command.

        Args:
            step: The step text

        Returns:
            Extracted command string or None
        """
        for pattern in COMMAND_PATTERNS:
            match = re.search(pattern, step, re.IGNORECASE)
            if match:
                command = match.group(1).strip()
                # Clean up the command
                command = self._clean_command(command)
                if command and len(command) > 2:
                    return command

        return None

    def _clean_command(self, command: str) -> str:
        """Clean up an extracted command string."""
        # Remove trailing punctuation
        command = command.rstrip(".,;:")

        # Remove common trailing words
        command = re.sub(r"\s+(?:to|for|and|with|in|on)\s*$", "", command, flags=re.IGNORECASE)

        # Normalize whitespace
        command = " ".join(command.split())

        return command

    def _determine_timeout(self, command: str) -> int:
        """
        Determine appropriate timeout based on command type.

        Args:
            command: The command string

        Returns:
            Timeout in seconds
        """
        command_lower = command.lower()

        for keyword, timeout in COMMAND_TIMEOUTS.items():
            if keyword in command_lower:
                return timeout

        return self._default_timeout

    # =========================================================================
    # file_exists Validator Creation
    # =========================================================================

    def _create_file_exists_validator(
        self,
        step: str,
        index: int,
        feature_id: int | None,
    ) -> ValidatorConfig | None:
        """
        Create a file_exists validator from a step.

        Extracts the file path from the step text.

        Args:
            step: The step text
            index: Step index
            feature_id: Optional feature ID

        Returns:
            ValidatorConfig or None if path extraction fails
        """
        # Step 5: Extract path from step text
        path = self._extract_path(step)

        if not path:
            _logger.debug("Could not extract path from step: %s", step[:50])
            return None

        # Determine if it should exist or not exist
        step_lower = step.lower()
        should_exist = True

        # Check for negation
        if re.search(r"\b(?:should\s+not|must\s+not|shouldn't|mustn't|not)\s+exist", step_lower):
            should_exist = False

        config = {
            "path": path,
            "should_exist": should_exist,
            "description": step,
        }

        return ValidatorConfig(
            validator_type="file_exists",
            config=config,
            weight=1.0,
            required=False,
            step_index=index,
            step_text=step,
            confidence=0.9,  # High confidence for file path extraction
        )

    def _extract_path(self, step: str) -> str | None:
        """
        Extract a file path from step text.

        Args:
            step: The step text

        Returns:
            Extracted path string or None
        """
        for pattern in PATH_PATTERNS:
            match = re.search(pattern, step)
            if match:
                path = match.group(1).strip()
                # Validate it looks like a path
                if self._is_valid_path(path):
                    return path

        return None

    def _is_valid_path(self, path: str) -> bool:
        """Check if a string looks like a valid file path."""
        # Must have at least 2 characters
        if len(path) < 2:
            return False

        # Should contain path-like characters
        if not re.match(r"^[a-zA-Z0-9_./-]+$", path):
            return False

        # Shouldn't be just a single word without extension or slash
        if "/" not in path and "." not in path:
            return False

        return True

    # =========================================================================
    # forbidden_patterns Validator Creation
    # =========================================================================

    def _create_forbidden_patterns_validator(
        self,
        step: str,
        index: int,
        feature_id: int | None,
    ) -> ValidatorConfig | None:
        """
        Create a forbidden_patterns validator from a step.

        Extracts the forbidden content/pattern from the step text.

        Args:
            step: The step text
            index: Step index
            feature_id: Optional feature ID

        Returns:
            ValidatorConfig or None if pattern extraction fails
        """
        # Extract forbidden content from step
        patterns = self._extract_forbidden_patterns(step)

        if not patterns:
            _logger.debug("Could not extract forbidden patterns from step: %s", step[:50])
            return None

        config = {
            "patterns": patterns,
            "case_sensitive": False,  # Usually we want case-insensitive matching
            "description": step,
        }

        return ValidatorConfig(
            validator_type="forbidden_patterns",
            config=config,
            weight=1.0,
            required=False,
            step_index=index,
            step_text=step,
            confidence=0.7,  # Medium confidence for pattern extraction
        )

    def _extract_forbidden_patterns(self, step: str) -> list[str]:
        """
        Extract forbidden patterns from step text.

        Converts natural language descriptions into regex patterns.

        Args:
            step: The step text

        Returns:
            List of regex pattern strings
        """
        patterns = []

        # Try to extract quoted content first
        for pattern_regex in FORBIDDEN_CONTENT_PATTERNS:
            matches = re.findall(pattern_regex, step, re.IGNORECASE)
            for match in matches:
                clean_match = match.strip()
                if clean_match and len(clean_match) > 1:
                    # Escape special regex characters but keep the pattern usable
                    escaped = re.escape(clean_match)
                    patterns.append(escaped)

        # If we couldn't find patterns, create generic ones based on keywords
        if not patterns:
            step_lower = step.lower()

            # Check for common forbidden content types
            if any(kw in step_lower for kw in ["password", "secret", "credential", "key"]):
                patterns.extend([
                    r"password\s*[=:]\s*['\"]?[^'\"]+['\"]?",
                    r"secret\s*[=:]\s*['\"]?[^'\"]+['\"]?",
                    r"api[_-]?key\s*[=:]\s*['\"]?[^'\"]+['\"]?",
                ])

            if any(kw in step_lower for kw in ["console", "debug", "log"]):
                patterns.extend([
                    r"console\.(log|debug|warn|error)\s*\(",
                ])

            if "hardcod" in step_lower:
                patterns.extend([
                    r"['\"][a-zA-Z0-9]{20,}['\"]",  # Long hardcoded strings
                ])

            if any(kw in step_lower for kw in ["error", "exception", "stack trace"]):
                patterns.extend([
                    r"Traceback \(most recent call last\)",
                    r"Error:",
                    r"Exception:",
                ])

        return patterns

    # =========================================================================
    # Fallback Validator
    # =========================================================================

    def _create_fallback_validator(
        self,
        step: str,
        index: int,
        feature_id: int | None,
    ) -> ValidatorConfig:
        """
        Create a fallback validator for steps that don't match specific patterns.

        The fallback validator is a manual verification checkpoint.

        Args:
            step: The step text
            index: Step index
            feature_id: Optional feature ID

        Returns:
            ValidatorConfig for manual verification
        """
        config = {
            "name": f"step_{index + 1}",
            "description": step,
            "step_number": index + 1,
            "feature_id": feature_id,
            # No automatic command - requires manual verification
            "command": None,
        }

        return ValidatorConfig(
            validator_type="manual",
            config=config,
            weight=1.0,
            required=False,
            step_index=index,
            step_text=step,
            confidence=0.5,  # Low confidence - this is a fallback
        )


# =============================================================================
# Module-level Convenience Functions
# =============================================================================

_default_generator: ValidatorGenerator | None = None


def get_validator_generator() -> ValidatorGenerator:
    """Get or create the default ValidatorGenerator."""
    global _default_generator

    if _default_generator is None:
        _default_generator = ValidatorGenerator()

    return _default_generator


def reset_validator_generator() -> None:
    """Reset the default generator (for testing)."""
    global _default_generator
    _default_generator = None


def generate_validators_from_steps(
    steps: list[str],
    *,
    feature_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Generate validators from feature steps using the default generator.

    This is the main entry point for feature step parsing.

    Args:
        steps: List of feature verification step strings
        feature_id: Optional feature ID for context

    Returns:
        List of validator config dictionaries ready for AcceptanceSpec
    """
    generator = get_validator_generator()
    configs = generator.generate_from_steps(steps, feature_id=feature_id)

    # Convert to dictionary format (Step 7: Return array of validator configs)
    return [config.to_dict() for config in configs]


def analyze_step(step: str) -> dict[str, Any]:
    """
    Analyze a single step and return validator hint information.

    Useful for debugging and understanding how steps are parsed.

    Args:
        step: The step text to analyze

    Returns:
        Dictionary with analysis results
    """
    generator = get_validator_generator()
    step_lower = step.lower()

    return {
        "step": step,
        "has_execute_keywords": generator._has_execute_keywords(step_lower),
        "has_file_keywords": generator._has_file_keywords(step_lower),
        "has_forbidden_keywords": generator._has_forbidden_keywords(step_lower),
        "extracted_command": generator._extract_command(step),
        "extracted_path": generator._extract_path(step),
        "extracted_patterns": generator._extract_forbidden_patterns(step),
    }
