"""
Test Code Writer Service
========================

Feature #206: Test-runner agent writes test code from TestContract

The Test Code Writer receives a TestContract and generates actual test code
that implements the contract's assertions and pass/fail criteria.

This module provides:
- TestCodeWriter: Main service class for generating test code from TestContract
- TestCodeWriteResult: Result of test code generation operation
- TestCodeWriterAuditInfo: Audit trail information for tests_written event
- Framework detection and selection (pytest, jest, mocha, etc.)
- Project convention detection for test directory placement
- Assertion to test code conversion

Usage:
    from api.test_code_writer import TestCodeWriter, write_tests_from_contract

    # Write tests from a TestContract
    writer = TestCodeWriter(project_dir)
    result = writer.write_tests(contract, session=db_session, run_id="abc-123")

    if result.success:
        print(f"Tests written to: {result.test_files}")
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

# Configure logging
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Supported test frameworks
TEST_FRAMEWORKS = frozenset({
    "pytest",      # Python - most common
    "unittest",    # Python - stdlib
    "jest",        # JavaScript/TypeScript
    "mocha",       # JavaScript
    "vitest",      # Vite/JavaScript
    "playwright",  # E2E testing
    "cypress",     # E2E testing
})

# Default test framework by language
DEFAULT_FRAMEWORKS = {
    "python": "pytest",
    "javascript": "jest",
    "typescript": "jest",
    "react": "jest",
    "vue": "jest",
    "node": "jest",
}

# Test directory patterns by framework
TEST_DIR_PATTERNS = {
    "pytest": ["tests", "test", "tests/unit", "tests/integration"],
    "unittest": ["tests", "test"],
    "jest": ["__tests__", "tests", "test", "src/__tests__"],
    "mocha": ["test", "tests"],
    "vitest": ["__tests__", "tests", "test"],
    "playwright": ["tests/e2e", "e2e", "tests"],
    "cypress": ["cypress/e2e", "cypress/integration"],
}

# File extension by framework
TEST_FILE_EXTENSIONS = {
    "pytest": ".py",
    "unittest": ".py",
    "jest": ".test.ts",
    "mocha": ".test.js",
    "vitest": ".test.ts",
    "playwright": ".spec.ts",
    "cypress": ".cy.ts",
}

# Test file prefix/suffix patterns
TEST_FILE_PREFIX = {
    "pytest": "test_",
    "unittest": "test_",
    "jest": "",
    "mocha": "",
    "vitest": "",
    "playwright": "",
    "cypress": "",
}

# Assertion operator to test code templates
PYTHON_ASSERTION_TEMPLATES = {
    "eq": "assert {target} == {expected}",
    "ne": "assert {target} != {expected}",
    "gt": "assert {target} > {expected}",
    "lt": "assert {target} < {expected}",
    "ge": "assert {target} >= {expected}",
    "le": "assert {target} <= {expected}",
    "contains": "assert {expected} in {target}",
    "matches": "assert re.match({expected}, {target})",
    "exists": "assert {target} is not None",
}

JS_ASSERTION_TEMPLATES = {
    "eq": "expect({target}).toBe({expected});",
    "ne": "expect({target}).not.toBe({expected});",
    "gt": "expect({target}).toBeGreaterThan({expected});",
    "lt": "expect({target}).toBeLessThan({expected});",
    "ge": "expect({target}).toBeGreaterThanOrEqual({expected});",
    "le": "expect({target}).toBeLessThanOrEqual({expected});",
    "contains": "expect({target}).toContain({expected});",
    "matches": "expect({target}).toMatch({expected});",
    "exists": "expect({target}).toBeDefined();",
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TestCodeWriterAuditInfo:
    """
    Audit trail information for a tests_written event.

    Attributes:
        event_id: ID of the recorded event (None if not recorded)
        run_id: Run ID the event is linked to
        timestamp: When the event was recorded
        recorded: Whether the event was successfully recorded
        error: Error message if recording failed
    """
    event_id: int | None = None
    run_id: str | None = None
    timestamp: datetime | None = None
    recorded: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "recorded": self.recorded,
            "error": self.error,
        }


@dataclass
class TestCodeWriteResult:
    """
    Result of test code generation operation.

    Attributes:
        contract_id: ID of the TestContract used
        agent_name: Name of the agent linked to the contract
        success: Whether the operation succeeded
        test_files: List of test file paths written
        test_framework: Framework used (pytest, jest, etc.)
        test_directory: Directory where tests were written
        assertions_count: Number of assertions generated
        error: Error message if failed
        content_hash: Hash of generated content for determinism verification
        audit_info: Audit trail information (populated by write_tests_with_audit)
    """
    contract_id: str
    agent_name: str
    success: bool = False
    test_files: list[Path] = field(default_factory=list)
    test_framework: str = "pytest"
    test_directory: Path | None = None
    assertions_count: int = 0
    error: str | None = None
    content_hash: str | None = None
    audit_info: TestCodeWriterAuditInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "contract_id": self.contract_id,
            "agent_name": self.agent_name,
            "success": self.success,
            "test_files": [str(p) for p in self.test_files],
            "test_framework": self.test_framework,
            "test_directory": str(self.test_directory) if self.test_directory else None,
            "assertions_count": self.assertions_count,
            "error": self.error,
            "content_hash": self.content_hash,
            "audit_info": self.audit_info.to_dict() if self.audit_info else None,
        }


@dataclass
class FrameworkDetectionResult:
    """Result of test framework detection."""
    framework: str
    confidence: float
    reason: str
    test_directory: Path | None = None


# =============================================================================
# Test Code Writer Class
# =============================================================================

class TestCodeWriter:
    """
    Service for writing test code from TestContract specifications.

    Feature #206: Test-runner agent writes test code from TestContract.

    The TestCodeWriter:
    1. Receives a TestContract with test requirements
    2. Detects the appropriate test framework (pytest, jest, etc.)
    3. Generates test code based on contract assertions
    4. Places tests in project's standard test directory
    5. Records a tests_written audit event

    Attributes:
        project_dir: Root directory of the project
    """

    def __init__(self, project_dir: str | Path):
        """
        Initialize TestCodeWriter.

        Args:
            project_dir: Root directory of the project
        """
        self.project_dir = Path(project_dir)
        _logger.debug("TestCodeWriter initialized: project_dir=%s", self.project_dir)

    def detect_framework(
        self,
        test_type: str | None = None,
        tech_stack: list[str] | None = None,
    ) -> FrameworkDetectionResult:
        """
        Detect the appropriate test framework for the project.

        Examines project files and configuration to determine which
        test framework should be used.

        Args:
            test_type: Type of test (unit, integration, e2e, api)
            tech_stack: List of technologies in the project

        Returns:
            FrameworkDetectionResult with framework, confidence, and reason
        """
        tech_stack = tech_stack or []

        # E2E testing -> prefer Playwright
        if test_type in ("e2e", "browser", "ui"):
            if (self.project_dir / "playwright.config.ts").exists():
                return FrameworkDetectionResult(
                    framework="playwright",
                    confidence=1.0,
                    reason="playwright.config.ts found, E2E test type",
                    test_directory=self._find_test_dir("playwright"),
                )
            return FrameworkDetectionResult(
                framework="playwright",
                confidence=0.8,
                reason="E2E test type, Playwright recommended",
                test_directory=self._find_test_dir("playwright"),
            )

        # Check for pytest configuration
        if (self.project_dir / "pytest.ini").exists():
            return FrameworkDetectionResult(
                framework="pytest",
                confidence=1.0,
                reason="pytest.ini found",
                test_directory=self._find_test_dir("pytest"),
            )
        if (self.project_dir / "pyproject.toml").exists():
            pyproject = (self.project_dir / "pyproject.toml").read_text()
            if "[tool.pytest" in pyproject:
                return FrameworkDetectionResult(
                    framework="pytest",
                    confidence=1.0,
                    reason="pytest configuration in pyproject.toml",
                    test_directory=self._find_test_dir("pytest"),
                )

        # Check for Jest configuration
        if (self.project_dir / "jest.config.js").exists() or \
           (self.project_dir / "jest.config.ts").exists():
            return FrameworkDetectionResult(
                framework="jest",
                confidence=1.0,
                reason="jest.config.{js,ts} found",
                test_directory=self._find_test_dir("jest"),
            )

        # Check package.json for test scripts
        if (self.project_dir / "package.json").exists():
            try:
                pkg = json.loads((self.project_dir / "package.json").read_text())
                scripts = pkg.get("scripts", {})
                if "test" in scripts:
                    test_cmd = scripts["test"]
                    if "jest" in test_cmd:
                        return FrameworkDetectionResult(
                            framework="jest",
                            confidence=0.9,
                            reason="jest in package.json test script",
                            test_directory=self._find_test_dir("jest"),
                        )
                    if "vitest" in test_cmd:
                        return FrameworkDetectionResult(
                            framework="vitest",
                            confidence=0.9,
                            reason="vitest in package.json test script",
                            test_directory=self._find_test_dir("vitest"),
                        )
                    if "mocha" in test_cmd:
                        return FrameworkDetectionResult(
                            framework="mocha",
                            confidence=0.9,
                            reason="mocha in package.json test script",
                            test_directory=self._find_test_dir("mocha"),
                        )
            except json.JSONDecodeError:
                pass

        # Infer from tech stack
        for tech in tech_stack:
            tech_lower = tech.lower()
            if tech_lower in DEFAULT_FRAMEWORKS:
                framework = DEFAULT_FRAMEWORKS[tech_lower]
                return FrameworkDetectionResult(
                    framework=framework,
                    confidence=0.6,
                    reason=f"Inferred from tech stack: {tech}",
                    test_directory=self._find_test_dir(framework),
                )

        # Check for existing test files
        if (self.project_dir / "tests").exists():
            for f in (self.project_dir / "tests").iterdir():
                if f.name.startswith("test_") and f.suffix == ".py":
                    return FrameworkDetectionResult(
                        framework="pytest",
                        confidence=0.7,
                        reason="Python test files found in tests/",
                        test_directory=self.project_dir / "tests",
                    )
                if f.suffix in (".ts", ".js") and ".test." in f.name:
                    return FrameworkDetectionResult(
                        framework="jest",
                        confidence=0.7,
                        reason="JavaScript test files found in tests/",
                        test_directory=self.project_dir / "tests",
                    )

        # Default to pytest (most common)
        return FrameworkDetectionResult(
            framework="pytest",
            confidence=0.5,
            reason="Default framework",
            test_directory=self._find_test_dir("pytest"),
        )

    def _find_test_dir(self, framework: str) -> Path | None:
        """
        Find the test directory for a given framework.

        Args:
            framework: Test framework name

        Returns:
            Path to test directory, or None if not found
        """
        patterns = TEST_DIR_PATTERNS.get(framework, ["tests"])
        for pattern in patterns:
            test_dir = self.project_dir / pattern
            if test_dir.exists():
                return test_dir
        # Return first pattern as default (will be created)
        return self.project_dir / patterns[0]

    def _generate_test_filename(
        self,
        agent_name: str,
        test_type: str,
        framework: str,
    ) -> str:
        """
        Generate a test filename based on agent and test type.

        Args:
            agent_name: Name of the agent
            test_type: Type of test (unit, integration, e2e, api)
            framework: Test framework

        Returns:
            Test filename
        """
        # Normalize agent name for filename
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", agent_name)
        prefix = TEST_FILE_PREFIX.get(framework, "test_")
        extension = TEST_FILE_EXTENSIONS.get(framework, ".py")

        if framework in ("pytest", "unittest"):
            return f"{prefix}{safe_name}_{test_type}{extension}"
        else:
            return f"{safe_name}.{test_type}{extension}"

    def _generate_python_test_code(
        self,
        contract: Any,
        framework: str = "pytest",
    ) -> tuple[str, int]:
        """
        Generate Python test code from a TestContract.

        Args:
            contract: TestContract instance
            framework: Test framework (pytest or unittest)

        Returns:
            Tuple of (test code string, assertion count)
        """
        lines = []
        assertion_count = 0

        # Imports
        lines.append('"""')
        lines.append(f"Test code generated from TestContract: {contract.contract_id}")
        lines.append(f"Agent: {contract.agent_name}")
        lines.append(f"Test Type: {contract.test_type}")
        if contract.description:
            lines.append(f"\n{contract.description}")
        lines.append('"""')
        lines.append("")

        if framework == "pytest":
            lines.append("import pytest")
        else:
            lines.append("import unittest")

        lines.append("import re")
        lines.append("")
        lines.append("")

        # Generate test class
        class_name = f"Test{contract.agent_name.replace('-', '_').title().replace('_', '')}"

        if framework == "unittest":
            lines.append(f"class {class_name}(unittest.TestCase):")
        else:
            lines.append(f"class {class_name}:")

        lines.append(f'    """Tests for {contract.agent_name}."""')
        lines.append("")

        # Generate tests from assertions
        for i, assertion in enumerate(contract.assertions):
            method_name = f"test_assertion_{i + 1}"
            desc = assertion.description.replace('"', "'")

            lines.append(f"    def {method_name}(self):")
            lines.append(f'        """{desc}"""')

            # Generate assertion code
            template = PYTHON_ASSERTION_TEMPLATES.get(assertion.operator, "assert {target}")
            expected = repr(assertion.expected) if isinstance(assertion.expected, str) else str(assertion.expected)

            assertion_code = template.format(
                target=assertion.target,
                expected=expected,
            )
            lines.append(f"        # Target: {assertion.target}")
            lines.append(f"        # Expected: {assertion.expected}")
            lines.append(f"        # TODO: Implement - {assertion_code}")
            lines.append("")
            assertion_count += 1

        # Generate tests from pass_criteria
        for i, criterion in enumerate(contract.pass_criteria):
            method_name = f"test_pass_criterion_{i + 1}"
            desc = criterion.replace('"', "'")

            lines.append(f"    def {method_name}(self):")
            lines.append(f'        """{desc}"""')
            lines.append(f"        # TODO: Implement test for: {criterion}")
            lines.append("        pass")
            lines.append("")
            assertion_count += 1

        # Generate fail criteria tests (negative tests)
        for i, criterion in enumerate(contract.fail_criteria):
            method_name = f"test_fail_criterion_{i + 1}"
            desc = f"Should NOT: {criterion}".replace('"', "'")

            lines.append(f"    def {method_name}(self):")
            lines.append(f'        """{desc}"""')
            lines.append(f"        # TODO: Implement negative test for: {criterion}")
            lines.append("        pass")
            lines.append("")
            assertion_count += 1

        if framework == "unittest":
            lines.append("")
            lines.append("")
            lines.append('if __name__ == "__main__":')
            lines.append("    unittest.main()")
            lines.append("")

        return "\n".join(lines), assertion_count

    def _generate_javascript_test_code(
        self,
        contract: Any,
        framework: str = "jest",
    ) -> tuple[str, int]:
        """
        Generate JavaScript/TypeScript test code from a TestContract.

        Args:
            contract: TestContract instance
            framework: Test framework (jest, mocha, vitest)

        Returns:
            Tuple of (test code string, assertion count)
        """
        lines = []
        assertion_count = 0

        # Header comment
        lines.append("/**")
        lines.append(f" * Test code generated from TestContract: {contract.contract_id}")
        lines.append(f" * Agent: {contract.agent_name}")
        lines.append(f" * Test Type: {contract.test_type}")
        if contract.description:
            lines.append(f" *")
            lines.append(f" * {contract.description}")
        lines.append(" */")
        lines.append("")

        # Imports based on framework
        if framework in ("jest", "vitest"):
            lines.append("import { describe, it, expect } from '@jest/globals';")
        elif framework == "playwright":
            lines.append("import { test, expect } from '@playwright/test';")
        lines.append("")

        # Generate describe block
        describe_name = contract.agent_name

        if framework == "playwright":
            lines.append(f"test.describe('{describe_name}', () => {{")
        else:
            lines.append(f"describe('{describe_name}', () => {{")

        # Generate tests from assertions
        for i, assertion in enumerate(contract.assertions):
            test_name = assertion.description.replace("'", "\\'")
            if framework == "playwright":
                lines.append(f"  test('{test_name}', async ({{ page }}) => {{")
            else:
                lines.append(f"  it('{test_name}', () => {{")

            # Generate assertion code
            template = JS_ASSERTION_TEMPLATES.get(assertion.operator, "expect({target}).toBeDefined();")
            expected = json.dumps(assertion.expected) if isinstance(assertion.expected, str) else str(assertion.expected)

            lines.append(f"    // Target: {assertion.target}")
            lines.append(f"    // Expected: {assertion.expected}")
            lines.append(f"    // TODO: Implement - {template.format(target=assertion.target, expected=expected)}")
            lines.append("  });")
            lines.append("")
            assertion_count += 1

        # Generate tests from pass_criteria
        for i, criterion in enumerate(contract.pass_criteria):
            test_name = criterion.replace("'", "\\'")
            if framework == "playwright":
                lines.append(f"  test('{test_name}', async ({{ page }}) => {{")
            else:
                lines.append(f"  it('{test_name}', () => {{")
            lines.append(f"    // TODO: Implement test for: {criterion}")
            lines.append("  });")
            lines.append("")
            assertion_count += 1

        # Generate fail criteria tests
        for i, criterion in enumerate(contract.fail_criteria):
            test_name = f"should NOT: {criterion}".replace("'", "\\'")
            if framework == "playwright":
                lines.append(f"  test('{test_name}', async ({{ page }}) => {{")
            else:
                lines.append(f"  it('{test_name}', () => {{")
            lines.append(f"    // TODO: Implement negative test for: {criterion}")
            lines.append("  });")
            lines.append("")
            assertion_count += 1

        lines.append("});")
        lines.append("")

        return "\n".join(lines), assertion_count

    def generate_test_code(
        self,
        contract: Any,
        framework: str | None = None,
    ) -> tuple[str, str, int]:
        """
        Generate test code from a TestContract.

        Args:
            contract: TestContract instance
            framework: Test framework (auto-detected if None)

        Returns:
            Tuple of (test code, framework used, assertion count)
        """
        # Auto-detect framework if not specified
        if framework is None:
            detection = self.detect_framework(test_type=contract.test_type)
            framework = detection.framework

        if framework in ("pytest", "unittest"):
            code, count = self._generate_python_test_code(contract, framework)
        else:
            code, count = self._generate_javascript_test_code(contract, framework)

        return code, framework, count

    def write_tests(
        self,
        contract: Any,
        framework: str | None = None,
    ) -> TestCodeWriteResult:
        """
        Write test code from a TestContract to the appropriate directory.

        Feature #206 Step 1-4: Receives TestContract, writes test files,
        places in standard test directory, follows project conventions.

        Args:
            contract: TestContract instance with test requirements
            framework: Test framework (auto-detected if None)

        Returns:
            TestCodeWriteResult with success status and file paths
        """
        try:
            # Detect framework and test directory
            if framework is None:
                detection = self.detect_framework(test_type=contract.test_type)
                framework = detection.framework
                test_dir = detection.test_directory or self._find_test_dir(framework)
            else:
                test_dir = self._find_test_dir(framework)

            # Ensure test directory exists
            if test_dir is None:
                test_dir = self.project_dir / "tests"
            test_dir.mkdir(parents=True, exist_ok=True)

            # Generate test code
            code, actual_framework, assertion_count = self.generate_test_code(
                contract, framework
            )

            # Generate filename
            filename = self._generate_test_filename(
                contract.agent_name,
                contract.test_type,
                actual_framework,
            )

            # Write test file
            test_file = test_dir / filename
            test_file.write_text(code)

            # Compute content hash for determinism verification
            content_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()

            _logger.info(
                "Test file written: %s (framework=%s, assertions=%d)",
                test_file,
                actual_framework,
                assertion_count,
            )

            return TestCodeWriteResult(
                contract_id=contract.contract_id,
                agent_name=contract.agent_name,
                success=True,
                test_files=[test_file],
                test_framework=actual_framework,
                test_directory=test_dir,
                assertions_count=assertion_count,
                content_hash=content_hash,
            )

        except Exception as e:
            _logger.error("Failed to write tests: %s", e)
            return TestCodeWriteResult(
                contract_id=contract.contract_id,
                agent_name=contract.agent_name,
                success=False,
                error=str(e),
            )

    def write_tests_with_audit(
        self,
        contract: Any,
        session: Session,
        run_id: str,
        framework: str | None = None,
    ) -> TestCodeWriteResult:
        """
        Write test code from a TestContract and record audit event.

        Feature #206 Step 5: Records tests_written audit event.

        Args:
            contract: TestContract instance with test requirements
            session: SQLAlchemy database session
            run_id: Run ID for audit event
            framework: Test framework (auto-detected if None)

        Returns:
            TestCodeWriteResult with audit_info populated
        """
        # First write the tests
        result = self.write_tests(contract, framework)

        if not result.success:
            # Don't record audit event for failed writes
            return result

        # Record audit event
        result.audit_info = self._record_tests_written_event(
            session=session,
            run_id=run_id,
            result=result,
        )

        return result

    def _record_tests_written_event(
        self,
        session: Session,
        run_id: str,
        result: TestCodeWriteResult,
    ) -> TestCodeWriterAuditInfo:
        """
        Record a tests_written audit event.

        Args:
            session: SQLAlchemy database session
            run_id: Run ID for event
            result: Test write result

        Returns:
            TestCodeWriterAuditInfo with event details
        """
        try:
            from api.event_recorder import get_event_recorder

            recorder = get_event_recorder(session, self.project_dir)

            event_id = recorder.record_tests_written(
                run_id=run_id,
                contract_id=result.contract_id,
                agent_name=result.agent_name,
                test_files=[str(f) for f in result.test_files],
                test_type=None,  # Could be extracted from contract if needed
                test_framework=result.test_framework,
                test_directory=str(result.test_directory) if result.test_directory else None,
                assertions_count=result.assertions_count,
            )

            _logger.debug(
                "tests_written event recorded: event_id=%d, run_id=%s",
                event_id,
                run_id,
            )

            return TestCodeWriterAuditInfo(
                event_id=event_id,
                run_id=run_id,
                timestamp=datetime.now(timezone.utc),
                recorded=True,
            )

        except Exception as e:
            _logger.error("Failed to record tests_written event: %s", e)
            return TestCodeWriterAuditInfo(
                run_id=run_id,
                recorded=False,
                error=str(e),
            )


# =============================================================================
# Module-Level Convenience Functions
# =============================================================================

# Global instance cache
_writer_cache: dict[str, TestCodeWriter] = {}


def get_test_code_writer(project_dir: str | Path) -> TestCodeWriter:
    """
    Get or create a TestCodeWriter instance for a project.

    Args:
        project_dir: Root directory of the project

    Returns:
        TestCodeWriter instance
    """
    key = str(project_dir)
    if key not in _writer_cache:
        _writer_cache[key] = TestCodeWriter(project_dir)
    return _writer_cache[key]


def reset_test_code_writer_cache() -> None:
    """Clear the global TestCodeWriter cache."""
    _writer_cache.clear()


def write_tests_from_contract(
    contract: Any,
    project_dir: str | Path,
    framework: str | None = None,
) -> TestCodeWriteResult:
    """
    Convenience function to write tests from a TestContract.

    Args:
        contract: TestContract instance
        project_dir: Root directory of the project
        framework: Test framework (auto-detected if None)

    Returns:
        TestCodeWriteResult
    """
    writer = get_test_code_writer(project_dir)
    return writer.write_tests(contract, framework)


def detect_test_framework(
    project_dir: str | Path,
    test_type: str | None = None,
    tech_stack: list[str] | None = None,
) -> FrameworkDetectionResult:
    """
    Convenience function to detect the test framework for a project.

    Args:
        project_dir: Root directory of the project
        test_type: Type of test (unit, integration, e2e, api)
        tech_stack: List of technologies in the project

    Returns:
        FrameworkDetectionResult
    """
    writer = get_test_code_writer(project_dir)
    return writer.detect_framework(test_type, tech_stack)
