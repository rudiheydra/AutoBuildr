"""
Sandbox Test Runner Module
==========================

Test execution within isolated Docker sandbox environments.

Feature #214: Test-runner agent can run in sandbox environment

This module provides:
- SandboxTestRunner: Executes tests in Docker sandbox for isolation
- SandboxConfiguration: Configuration for sandbox execution
- SandboxExecutionResult: Result dataclass with sandbox-specific metadata
- Dependency installation within sandbox containers
- Results capture from sandbox execution

The SandboxTestRunner extends TestRunner to route all test execution
through a Docker sandbox environment, providing:
1. Isolation: Tests run in a fresh container environment
2. Consistency: Same Docker image ensures reproducible results
3. Safety: Tests can't affect the host system
4. Dependency management: Install test deps in isolated sandbox

Usage:
    from api.sandbox_test_runner import SandboxTestRunner, SandboxConfiguration

    # Create sandbox configuration
    config = SandboxConfiguration(
        image="autobuildr-sandbox:latest",
        project_mount="/workspace",
        working_directory="/workspace/tests",
    )

    # Create sandbox test runner
    runner = SandboxTestRunner(config=config)

    # Execute tests in sandbox
    result = runner.run_in_sandbox(
        command="pytest tests/ -v",
        project_dir="/path/to/project",
    )

    if result.passed:
        print(f"All {result.total_tests} tests passed in sandbox!")
    else:
        print(f"Failed: {result.failures_count} / {result.total_tests}")
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from api.test_runner import TestRunner, TestExecutionResult, TestFailure

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from api.event_recorder import EventRecorder

# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Default Docker image for sandbox execution
DEFAULT_SANDBOX_IMAGE = "autobuildr-sandbox:latest"

# Default mount point for project files in sandbox
DEFAULT_PROJECT_MOUNT = "/workspace"

# Default timeout for sandbox execution (seconds)
DEFAULT_SANDBOX_TIMEOUT = 600

# Default timeout for dependency installation (seconds)
DEFAULT_INSTALL_TIMEOUT = 180

# Common test dependency files
DEPENDENCY_FILES = {
    "python": ["requirements.txt", "requirements-test.txt", "requirements-dev.txt", "pyproject.toml"],
    "javascript": ["package.json", "package-lock.json", "yarn.lock"],
}

# Default pip install command
DEFAULT_PIP_INSTALL = "pip install -q"

# Default npm install command
DEFAULT_NPM_INSTALL = "npm ci --silent"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SandboxConfiguration:
    """
    Configuration for sandbox test execution.

    Feature #214, Step 1: Test-runner execution routed through sandbox

    Attributes:
        image: Docker image for sandbox execution
        project_mount: Mount point for project files in container
        working_directory: Working directory inside container
        network_mode: Docker network mode (default: none for isolation)
        memory_limit: Memory limit for container (e.g., "1g")
        cpu_limit: CPU limit for container (e.g., "1.0")
        timeout_seconds: Default timeout for test execution
        install_timeout: Timeout for dependency installation
        environment: Additional environment variables
        volumes: Additional volume mounts (host:container)
        docker_socket: Path to Docker socket (for docker-in-docker)
        remove_container: Remove container after execution
        pull_policy: Image pull policy (never, always, if-not-present)
    """
    image: str = DEFAULT_SANDBOX_IMAGE
    project_mount: str = DEFAULT_PROJECT_MOUNT
    working_directory: str | None = None
    network_mode: str = "none"
    memory_limit: str | None = None
    cpu_limit: str | None = None
    timeout_seconds: int = DEFAULT_SANDBOX_TIMEOUT
    install_timeout: int = DEFAULT_INSTALL_TIMEOUT
    environment: dict[str, str] = field(default_factory=dict)
    volumes: list[str] = field(default_factory=list)
    docker_socket: str = "/var/run/docker.sock"
    remove_container: bool = True
    pull_policy: str = "if-not-present"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "image": self.image,
            "project_mount": self.project_mount,
            "working_directory": self.working_directory,
            "network_mode": self.network_mode,
            "memory_limit": self.memory_limit,
            "cpu_limit": self.cpu_limit,
            "timeout_seconds": self.timeout_seconds,
            "install_timeout": self.install_timeout,
            "environment_keys": list(self.environment.keys()),
            "volumes_count": len(self.volumes),
            "remove_container": self.remove_container,
            "pull_policy": self.pull_policy,
        }


@dataclass
class DependencyInstallResult:
    """
    Result of installing test dependencies in sandbox.

    Feature #214, Step 3: Test dependencies installed in sandbox

    Attributes:
        success: Whether installation succeeded
        exit_code: Exit code from install command
        stdout: Standard output from installation
        stderr: Standard error from installation
        command: Command that was executed
        duration_seconds: How long installation took
        dependencies_file: File used for dependency resolution
        dependency_count: Number of dependencies installed (if known)
    """
    success: bool
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    command: str = ""
    duration_seconds: float = 0.0
    dependencies_file: str | None = None
    dependency_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:2000],
            "stderr": self.stderr[:1000],
            "command": self.command,
            "duration_seconds": self.duration_seconds,
            "dependencies_file": self.dependencies_file,
            "dependency_count": self.dependency_count,
        }


@dataclass
class SandboxExecutionResult(TestExecutionResult):
    """
    Extended test execution result with sandbox-specific metadata.

    Feature #214, Step 5: Results captured from sandbox execution

    Additional attributes beyond TestExecutionResult:
        container_id: Docker container ID used for execution
        sandbox_image: Docker image that was used
        dependency_install: Result of dependency installation
        sandbox_environment: Environment variables in sandbox
        project_mounted: Whether project was successfully mounted
        sandbox_working_dir: Working directory used in sandbox
    """
    container_id: str | None = None
    sandbox_image: str | None = None
    dependency_install: DependencyInstallResult | None = None
    sandbox_environment: dict[str, str] = field(default_factory=dict)
    project_mounted: bool = False
    sandbox_working_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base_dict = super().to_dict()
        base_dict.update({
            "container_id": self.container_id,
            "sandbox_image": self.sandbox_image,
            "dependency_install": self.dependency_install.to_dict() if self.dependency_install else None,
            "sandbox_environment_keys": list(self.sandbox_environment.keys()),
            "project_mounted": self.project_mounted,
            "sandbox_working_dir": self.sandbox_working_dir,
        })
        return base_dict


# =============================================================================
# Sandbox Test Runner
# =============================================================================

class SandboxTestRunner(TestRunner):
    """
    Test execution engine with Docker sandbox isolation.

    Feature #214: Test-runner agent can run in sandbox environment

    This class implements:
    - Step 1: Test-runner execution routed through sandbox (Docker)
    - Step 2: Sandbox has access to project files (volume mount)
    - Step 3: Test dependencies installed in sandbox
    - Step 4: Sandbox provides consistent test environment
    - Step 5: Results captured from sandbox execution

    The SandboxTestRunner extends TestRunner to route all test execution
    through a Docker container. This provides:
    - **Isolation**: Tests run in a fresh container environment
    - **Consistency**: Same Docker image ensures reproducible results
    - **Safety**: Tests can't affect the host system
    - **Dependency management**: Install test deps in isolated sandbox

    Usage:
        config = SandboxConfiguration(image="python:3.11-slim")
        runner = SandboxTestRunner(config=config)

        result = runner.run_in_sandbox(
            command="pytest tests/ -v",
            project_dir="/path/to/project",
        )

        if result.passed:
            print("All tests passed!")
    """

    def __init__(
        self,
        config: SandboxConfiguration | None = None,
        *,
        default_timeout: int = DEFAULT_SANDBOX_TIMEOUT,
        max_output_size: int = 65536,
        auto_install_deps: bool = True,
    ):
        """
        Initialize the SandboxTestRunner.

        Args:
            config: Sandbox configuration (uses defaults if not provided)
            default_timeout: Default timeout for test execution in seconds
            max_output_size: Maximum output size to capture (bytes)
            auto_install_deps: Automatically install dependencies before tests
        """
        super().__init__(default_timeout=default_timeout, max_output_size=max_output_size)
        self._config = config or SandboxConfiguration()
        self._auto_install_deps = auto_install_deps
        self._docker_available: bool | None = None
        self._logger = logging.getLogger(__name__)

    @property
    def config(self) -> SandboxConfiguration:
        """Get the sandbox configuration."""
        return self._config

    @property
    def is_docker_available(self) -> bool:
        """
        Check if Docker is available for sandbox execution.

        Returns True if Docker CLI is installed and daemon is running.
        """
        if self._docker_available is None:
            self._docker_available = self._check_docker_available()
        return self._docker_available

    def _check_docker_available(self) -> bool:
        """Check if Docker is installed and running."""
        docker_path = shutil.which("docker")
        if not docker_path:
            self._logger.warning("Docker CLI not found in PATH")
            return False

        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                self._logger.debug("Docker is available and running")
                return True
            else:
                self._logger.warning("Docker daemon not running: %s", result.stderr[:200])
                return False
        except subprocess.TimeoutExpired:
            self._logger.warning("Docker info command timed out")
            return False
        except Exception as e:
            self._logger.warning("Docker availability check failed: %s", e)
            return False

    def run_in_sandbox(
        self,
        command: str,
        project_dir: str | Path,
        *,
        timeout_seconds: int | None = None,
        expected_exit_code: int = 0,
        working_directory: str | None = None,
        environment: dict[str, str] | None = None,
        install_dependencies: bool | None = None,
        dependency_command: str | None = None,
    ) -> SandboxExecutionResult:
        """
        Execute tests in a Docker sandbox container.

        Feature #214 Steps 1-5: Full sandbox test execution

        Args:
            command: Test command to execute (e.g., "pytest tests/ -v")
            project_dir: Path to project directory (mounted in sandbox)
            timeout_seconds: Timeout for test execution (uses config default if not specified)
            expected_exit_code: Expected exit code for "passed" status (default 0)
            working_directory: Working directory inside sandbox (relative to project mount)
            environment: Additional environment variables for sandbox
            install_dependencies: Override auto_install_deps setting
            dependency_command: Custom command for installing dependencies

        Returns:
            SandboxExecutionResult with test results and sandbox metadata
        """
        project_path = Path(project_dir).resolve()
        timeout = timeout_seconds or self._config.timeout_seconds
        start_time = datetime.now(timezone.utc)

        self._logger.info(
            "SandboxTestRunner.run_in_sandbox: command='%s', project='%s', timeout=%ds",
            command, project_path, timeout
        )

        # Check Docker availability
        if not self.is_docker_available:
            self._logger.error("Docker is not available for sandbox execution")
            return SandboxExecutionResult(
                passed=False,
                exit_code=None,
                expected_exit_code=expected_exit_code,
                command=command,
                working_directory=str(project_path),
                timeout_seconds=timeout,
                duration_seconds=0.0,
                timestamp=start_time,
                error_message="Docker is not available for sandbox execution",
                sandbox_image=self._config.image,
                project_mounted=False,
            )

        # Check project directory exists
        if not project_path.exists():
            self._logger.error("Project directory does not exist: %s", project_path)
            return SandboxExecutionResult(
                passed=False,
                exit_code=None,
                expected_exit_code=expected_exit_code,
                command=command,
                working_directory=str(project_path),
                timeout_seconds=timeout,
                duration_seconds=0.0,
                timestamp=start_time,
                error_message=f"Project directory does not exist: {project_path}",
                sandbox_image=self._config.image,
                project_mounted=False,
            )

        # Step 3: Install dependencies if requested
        should_install = install_dependencies if install_dependencies is not None else self._auto_install_deps
        dep_result = None

        if should_install:
            dep_result = self._install_dependencies(
                project_path,
                custom_command=dependency_command,
                environment=environment,
            )
            if not dep_result.success:
                self._logger.warning(
                    "Dependency installation failed, continuing with test execution"
                )

        # Step 1 & 2: Execute tests in sandbox with project mounted
        return self._execute_in_sandbox(
            command=command,
            project_path=project_path,
            timeout_seconds=timeout,
            expected_exit_code=expected_exit_code,
            working_directory=working_directory,
            environment=environment,
            start_time=start_time,
            dependency_install=dep_result,
        )

    def _install_dependencies(
        self,
        project_path: Path,
        custom_command: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> DependencyInstallResult:
        """
        Install test dependencies in the sandbox.

        Feature #214, Step 3: Test dependencies installed in sandbox

        Args:
            project_path: Path to project directory
            custom_command: Custom install command (auto-detects if not provided)
            environment: Additional environment variables

        Returns:
            DependencyInstallResult with installation outcome
        """
        start_time = datetime.now(timezone.utc)

        # Auto-detect install command if not provided
        install_cmd, deps_file = self._detect_install_command(project_path, custom_command)

        if not install_cmd:
            self._logger.debug("No dependencies to install for project: %s", project_path)
            return DependencyInstallResult(
                success=True,
                exit_code=0,
                command="",
                duration_seconds=0.0,
                dependencies_file=None,
            )

        self._logger.info(
            "Installing dependencies: command='%s', file='%s'",
            install_cmd, deps_file
        )

        # Build Docker command for dependency installation
        docker_cmd = self._build_docker_command(
            command=install_cmd,
            project_path=project_path,
            environment=environment,
        )

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=self._config.install_timeout,
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            success = result.returncode == 0

            self._logger.info(
                "Dependency installation %s: exit_code=%d, duration=%.2fs",
                "succeeded" if success else "failed",
                result.returncode,
                duration
            )

            return DependencyInstallResult(
                success=success,
                exit_code=result.returncode,
                stdout=self._truncate_output(result.stdout),
                stderr=self._truncate_output(result.stderr),
                command=install_cmd,
                duration_seconds=duration,
                dependencies_file=deps_file,
                dependency_count=self._count_dependencies(result.stdout),
            )

        except subprocess.TimeoutExpired as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            stdout = e.stdout.decode("utf-8", errors="replace") if e.stdout else ""
            stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""

            self._logger.warning(
                "Dependency installation timed out after %ds",
                self._config.install_timeout
            )

            return DependencyInstallResult(
                success=False,
                exit_code=None,
                stdout=self._truncate_output(stdout),
                stderr=self._truncate_output(stderr) + f"\nTimed out after {self._config.install_timeout}s",
                command=install_cmd,
                duration_seconds=duration,
                dependencies_file=deps_file,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            self._logger.exception("Dependency installation failed")

            return DependencyInstallResult(
                success=False,
                exit_code=None,
                stderr=str(e),
                command=install_cmd,
                duration_seconds=duration,
                dependencies_file=deps_file,
            )

    def _detect_install_command(
        self,
        project_path: Path,
        custom_command: str | None = None,
    ) -> tuple[str | None, str | None]:
        """
        Detect the appropriate dependency installation command.

        Returns:
            Tuple of (install_command, dependency_file) or (None, None) if no deps
        """
        if custom_command:
            return custom_command, None

        # Check for Python dependencies
        for dep_file in DEPENDENCY_FILES["python"]:
            if (project_path / dep_file).exists():
                if dep_file == "pyproject.toml":
                    return f"{DEFAULT_PIP_INSTALL} -e .", dep_file
                else:
                    return f"{DEFAULT_PIP_INSTALL} -r {dep_file}", dep_file

        # Check for JavaScript dependencies
        for dep_file in DEPENDENCY_FILES["javascript"]:
            if (project_path / dep_file).exists():
                return DEFAULT_NPM_INSTALL, dep_file

        return None, None

    def _count_dependencies(self, stdout: str) -> int:
        """Try to count installed dependencies from output."""
        # Look for common patterns
        import re

        # pip: "Successfully installed package1 package2 ..."
        pip_match = re.search(r"Successfully installed (\d+)", stdout)
        if pip_match:
            return int(pip_match.group(1))

        # Count "Installing" lines
        installing_count = stdout.lower().count("installing")
        if installing_count > 0:
            return installing_count

        return 0

    def _execute_in_sandbox(
        self,
        command: str,
        project_path: Path,
        timeout_seconds: int,
        expected_exit_code: int,
        working_directory: str | None,
        environment: dict[str, str] | None,
        start_time: datetime,
        dependency_install: DependencyInstallResult | None,
    ) -> SandboxExecutionResult:
        """
        Execute the test command in a Docker sandbox.

        Feature #214, Steps 1, 2, 4, 5:
        - Step 1: Test-runner execution routed through sandbox
        - Step 2: Sandbox has access to project files
        - Step 4: Sandbox provides consistent test environment
        - Step 5: Results captured from sandbox execution

        Args:
            command: Test command to execute
            project_path: Path to project directory
            timeout_seconds: Execution timeout
            expected_exit_code: Expected exit code for pass
            working_directory: Working directory in sandbox
            environment: Environment variables
            start_time: When execution started
            dependency_install: Result of dependency installation

        Returns:
            SandboxExecutionResult with full test results
        """
        # Determine working directory inside sandbox
        sandbox_workdir = self._config.working_directory or self._config.project_mount
        if working_directory:
            sandbox_workdir = f"{self._config.project_mount}/{working_directory.lstrip('/')}"

        # Merge environment variables
        env_vars = {**self._config.environment}
        if environment:
            env_vars.update(environment)

        # Build Docker command
        docker_cmd = self._build_docker_command(
            command=command,
            project_path=project_path,
            working_directory=sandbox_workdir,
            environment=env_vars,
        )

        self._logger.debug(
            "Executing in sandbox: docker_cmd=%s",
            " ".join(docker_cmd)
        )

        try:
            # Execute in sandbox
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            stdout = self._truncate_output(result.stdout)
            stderr = self._truncate_output(result.stderr)
            exit_code = result.returncode

            self._logger.info(
                "Sandbox execution complete: exit_code=%d, duration=%.2fs",
                exit_code, duration
            )

            # Parse results using parent class logic
            parsed = self._parse_results(command, stdout, stderr, exit_code)

            return SandboxExecutionResult(
                passed=exit_code == expected_exit_code,
                exit_code=exit_code,
                expected_exit_code=expected_exit_code,
                total_tests=parsed.get("total_tests", 0),
                passed_tests=parsed.get("passed_tests", 0),
                failed_tests=parsed.get("failed_tests", 0),
                skipped_tests=parsed.get("skipped_tests", 0),
                error_tests=parsed.get("error_tests", 0),
                failures=parsed.get("failures", []),
                stdout=stdout,
                stderr=stderr,
                command=command,
                working_directory=str(project_path),
                timeout_seconds=timeout_seconds,
                duration_seconds=duration,
                framework=parsed.get("framework"),
                framework_version=parsed.get("framework_version"),
                timestamp=start_time,
                # Sandbox-specific fields
                sandbox_image=self._config.image,
                dependency_install=dependency_install,
                sandbox_environment=env_vars,
                project_mounted=True,
                sandbox_working_dir=sandbox_workdir,
            )

        except subprocess.TimeoutExpired as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            stdout = e.stdout.decode("utf-8", errors="replace") if e.stdout else ""
            stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""

            self._logger.warning(
                "Sandbox execution timed out after %ds", timeout_seconds
            )

            return SandboxExecutionResult(
                passed=False,
                exit_code=None,
                expected_exit_code=expected_exit_code,
                stdout=self._truncate_output(stdout),
                stderr=self._truncate_output(stderr),
                command=command,
                working_directory=str(project_path),
                timeout_seconds=timeout_seconds,
                duration_seconds=duration,
                timestamp=start_time,
                error_message=f"Sandbox execution timed out after {timeout_seconds} seconds",
                sandbox_image=self._config.image,
                dependency_install=dependency_install,
                sandbox_environment=env_vars,
                project_mounted=True,
                sandbox_working_dir=sandbox_workdir,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            self._logger.exception("Sandbox execution failed")

            return SandboxExecutionResult(
                passed=False,
                exit_code=None,
                expected_exit_code=expected_exit_code,
                stdout="",
                stderr=str(e),
                command=command,
                working_directory=str(project_path),
                timeout_seconds=timeout_seconds,
                duration_seconds=duration,
                timestamp=start_time,
                error_message=f"Sandbox execution error: {e}",
                sandbox_image=self._config.image,
                dependency_install=dependency_install,
                sandbox_environment=env_vars,
                project_mounted=False,
                sandbox_working_dir=sandbox_workdir,
            )

    def _build_docker_command(
        self,
        command: str,
        project_path: Path,
        working_directory: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> list[str]:
        """
        Build the Docker run command for sandbox execution.

        Feature #214, Steps 1 & 2:
        - Step 1: Route execution through Docker sandbox
        - Step 2: Mount project files for sandbox access

        Args:
            command: Command to execute inside container
            project_path: Path to project (mounted as volume)
            working_directory: Working directory inside container
            environment: Environment variables

        Returns:
            List of command arguments for subprocess
        """
        docker_cmd = ["docker", "run"]

        # Remove container after execution
        if self._config.remove_container:
            docker_cmd.append("--rm")

        # Network mode (default: none for isolation)
        docker_cmd.extend(["--network", self._config.network_mode])

        # Memory limit
        if self._config.memory_limit:
            docker_cmd.extend(["--memory", self._config.memory_limit])

        # CPU limit
        if self._config.cpu_limit:
            docker_cmd.extend(["--cpus", self._config.cpu_limit])

        # Working directory inside container
        workdir = working_directory or self._config.working_directory or self._config.project_mount
        docker_cmd.extend(["-w", workdir])

        # Step 2: Mount project directory
        docker_cmd.extend([
            "-v", f"{project_path}:{self._config.project_mount}"
        ])

        # Additional volume mounts
        for volume in self._config.volumes:
            docker_cmd.extend(["-v", volume])

        # Environment variables
        if environment:
            for key, value in environment.items():
                docker_cmd.extend(["-e", f"{key}={value}"])

        # Image
        docker_cmd.append(self._config.image)

        # Command (via shell for flexibility)
        docker_cmd.extend(["sh", "-c", command])

        return docker_cmd

    def run(
        self,
        command: str,
        working_directory: str | Path | None = None,
        timeout_seconds: int | None = None,
        expected_exit_code: int = 0,
        env: dict[str, str] | None = None,
    ) -> TestExecutionResult:
        """
        Override parent run() to route through sandbox if Docker is available.

        If Docker is available, runs tests in sandbox. Otherwise, falls back
        to local execution using parent class implementation.

        Args:
            command: Test command to execute
            working_directory: Working directory (used as project_dir for sandbox)
            timeout_seconds: Timeout in seconds
            expected_exit_code: Expected exit code for success
            env: Additional environment variables

        Returns:
            TestExecutionResult (or SandboxExecutionResult if sandbox used)
        """
        # Try sandbox execution if Docker is available
        if self.is_docker_available and working_directory:
            return self.run_in_sandbox(
                command=command,
                project_dir=working_directory,
                timeout_seconds=timeout_seconds,
                expected_exit_code=expected_exit_code,
                environment=env,
            )

        # Fall back to local execution
        self._logger.debug(
            "Falling back to local execution (Docker available: %s, working_dir: %s)",
            self.is_docker_available,
            working_directory,
        )
        return super().run(
            command=command,
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
            expected_exit_code=expected_exit_code,
            env=env,
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def run_tests_in_sandbox(
    command: str,
    project_dir: str | Path,
    *,
    timeout_seconds: int = DEFAULT_SANDBOX_TIMEOUT,
    expected_exit_code: int = 0,
    image: str = DEFAULT_SANDBOX_IMAGE,
    install_dependencies: bool = True,
    environment: dict[str, str] | None = None,
) -> SandboxExecutionResult:
    """
    Convenience function to run tests in a Docker sandbox.

    Creates a SandboxTestRunner with the specified configuration and
    executes tests in a sandboxed environment.

    Args:
        command: Test command to execute
        project_dir: Path to project directory
        timeout_seconds: Timeout in seconds
        expected_exit_code: Expected exit code for success
        image: Docker image to use
        install_dependencies: Whether to install dependencies first
        environment: Additional environment variables

    Returns:
        SandboxExecutionResult with execution details

    Example:
        result = run_tests_in_sandbox(
            "pytest tests/ -v",
            "/path/to/project",
            image="python:3.11-slim",
        )
    """
    config = SandboxConfiguration(
        image=image,
        timeout_seconds=timeout_seconds,
    )

    runner = SandboxTestRunner(config=config, auto_install_deps=install_dependencies)

    return runner.run_in_sandbox(
        command=command,
        project_dir=project_dir,
        timeout_seconds=timeout_seconds,
        expected_exit_code=expected_exit_code,
        environment=environment,
    )


def is_sandbox_available() -> bool:
    """
    Check if sandbox execution is available (Docker is installed and running).

    Returns:
        True if Docker is available for sandbox execution
    """
    runner = SandboxTestRunner()
    return runner.is_docker_available


def get_default_sandbox_config() -> SandboxConfiguration:
    """
    Get the default sandbox configuration.

    Returns:
        Default SandboxConfiguration instance
    """
    return SandboxConfiguration()


def record_sandbox_tests_executed(
    recorder: "EventRecorder",
    run_id: str,
    result: SandboxExecutionResult,
    *,
    agent_name: str | None = None,
    spec_id: str | None = None,
    test_target: str | None = None,
) -> int:
    """
    Record a sandbox_tests_executed audit event.

    Feature #214, Step 5: Results captured from sandbox execution

    This function records sandbox test execution details to the audit trail,
    including sandbox-specific metadata.

    Args:
        recorder: EventRecorder instance
        run_id: Run ID for the event
        result: SandboxExecutionResult from test execution
        agent_name: Name of the test-runner agent
        spec_id: ID of the AgentSpec being tested
        test_target: What was being tested (e.g., "feature-123")

    Returns:
        Event ID
    """
    payload = {
        "passed": result.passed,
        "exit_code": result.exit_code,
        "total_tests": result.total_tests,
        "passed_tests": result.passed_tests,
        "failed_tests": result.failed_tests,
        "skipped_tests": result.skipped_tests,
        "error_tests": result.error_tests,
        "command": result.command,
        "duration_seconds": result.duration_seconds,
        "framework": result.framework,
        # Sandbox-specific fields
        "sandbox_execution": True,
        "sandbox_image": result.sandbox_image,
        "project_mounted": result.project_mounted,
        "sandbox_working_dir": result.sandbox_working_dir,
    }

    if agent_name:
        payload["agent_name"] = agent_name
    if spec_id:
        payload["spec_id"] = spec_id
    if test_target:
        payload["test_target"] = test_target
    if result.error_message:
        payload["error_message"] = result.error_message

    # Include dependency installation info
    if result.dependency_install:
        payload["dependency_install"] = {
            "success": result.dependency_install.success,
            "command": result.dependency_install.command,
            "dependencies_file": result.dependency_install.dependencies_file,
            "duration_seconds": result.dependency_install.duration_seconds,
        }

    # Include truncated failure details
    if result.failures:
        failure_summaries = [
            {"test_name": f.test_name, "message": f.message[:200]}
            for f in result.failures[:10]
        ]
        payload["failures"] = failure_summaries

    return recorder.record(run_id, "sandbox_tests_executed", payload=payload)
