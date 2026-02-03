"""
Tests for Feature #214: Test-runner agent can run in sandbox environment
========================================================================

This module tests the SandboxTestRunner which executes tests within isolated
Docker sandbox environments.

Feature Steps:
1. Test-runner execution routed through sandbox
2. Sandbox has access to project files
3. Test dependencies installed in sandbox
4. Sandbox provides consistent test environment
5. Results captured from sandbox execution

Run with: pytest tests/test_feature_214_sandbox_test_runner.py -v
"""

import pytest
import subprocess
import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock

from api.sandbox_test_runner import (
    SandboxConfiguration,
    DependencyInstallResult,
    SandboxExecutionResult,
    SandboxTestRunner,
    run_tests_in_sandbox,
    is_sandbox_available,
    get_default_sandbox_config,
    record_sandbox_tests_executed,
    DEFAULT_SANDBOX_IMAGE,
    DEFAULT_PROJECT_MOUNT,
    DEFAULT_SANDBOX_TIMEOUT,
    DEFAULT_INSTALL_TIMEOUT,
    DEPENDENCY_FILES,
)
from api.test_runner import TestExecutionResult


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory with test files."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()

    # Create a simple Python file
    (project_dir / "app.py").write_text("def hello(): return 'Hello, World!'")

    # Create tests directory with a simple test
    tests_dir = project_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_app.py").write_text("""
def test_hello():
    from app import hello
    assert hello() == 'Hello, World!'
""")

    # Create requirements.txt
    (project_dir / "requirements.txt").write_text("pytest>=7.0.0")

    return project_dir


@pytest.fixture
def js_project_dir(tmp_path):
    """Create a temporary JavaScript project directory."""
    project_dir = tmp_path / "js-project"
    project_dir.mkdir()

    # Create package.json
    (project_dir / "package.json").write_text("""{
  "name": "test-project",
  "version": "1.0.0",
  "scripts": {
    "test": "jest"
  },
  "devDependencies": {
    "jest": "^29.0.0"
  }
}""")

    return project_dir


@pytest.fixture
def sandbox_config():
    """Create a default sandbox configuration."""
    return SandboxConfiguration()


@pytest.fixture
def mock_subprocess_run():
    """Mock subprocess.run for testing without Docker."""
    with patch("subprocess.run") as mock_run:
        yield mock_run


@pytest.fixture
def mock_docker_available():
    """Mock Docker being available."""
    with patch("shutil.which") as mock_which, \
         patch("subprocess.run") as mock_run:
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        yield mock_run


# =============================================================================
# Test SandboxConfiguration
# =============================================================================

class TestSandboxConfiguration:
    """Tests for SandboxConfiguration dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SandboxConfiguration()

        assert config.image == DEFAULT_SANDBOX_IMAGE
        assert config.project_mount == DEFAULT_PROJECT_MOUNT
        assert config.network_mode == "none"
        assert config.timeout_seconds == DEFAULT_SANDBOX_TIMEOUT
        assert config.install_timeout == DEFAULT_INSTALL_TIMEOUT
        assert config.remove_container is True
        assert config.pull_policy == "if-not-present"

    def test_custom_values(self):
        """Test custom configuration values."""
        config = SandboxConfiguration(
            image="python:3.11-slim",
            project_mount="/app",
            working_directory="/app/tests",
            network_mode="bridge",
            memory_limit="2g",
            cpu_limit="2.0",
            timeout_seconds=1200,
            environment={"DEBUG": "1"},
        )

        assert config.image == "python:3.11-slim"
        assert config.project_mount == "/app"
        assert config.working_directory == "/app/tests"
        assert config.network_mode == "bridge"
        assert config.memory_limit == "2g"
        assert config.cpu_limit == "2.0"
        assert config.timeout_seconds == 1200
        assert config.environment == {"DEBUG": "1"}

    def test_to_dict(self):
        """Test serialization to dictionary."""
        config = SandboxConfiguration(
            image="python:3.11",
            environment={"KEY": "value"},
            volumes=["/host:/container"],
        )
        result = config.to_dict()

        assert result["image"] == "python:3.11"
        assert result["environment_keys"] == ["KEY"]
        assert result["volumes_count"] == 1
        assert "docker_socket" not in result  # Security: don't expose socket path


class TestDependencyInstallResult:
    """Tests for DependencyInstallResult dataclass."""

    def test_successful_install(self):
        """Test successful dependency installation result."""
        result = DependencyInstallResult(
            success=True,
            exit_code=0,
            stdout="Successfully installed pytest-7.0.0",
            command="pip install -q -r requirements.txt",
            duration_seconds=5.5,
            dependencies_file="requirements.txt",
            dependency_count=5,
        )

        assert result.success is True
        assert result.exit_code == 0
        assert "pytest" in result.stdout
        assert result.dependency_count == 5

    def test_failed_install(self):
        """Test failed dependency installation result."""
        result = DependencyInstallResult(
            success=False,
            exit_code=1,
            stderr="Package not found",
            command="pip install -q -r requirements.txt",
            duration_seconds=2.0,
        )

        assert result.success is False
        assert result.exit_code == 1
        assert "not found" in result.stderr

    def test_to_dict_truncates_output(self):
        """Test that to_dict truncates long output."""
        long_stdout = "x" * 5000
        result = DependencyInstallResult(
            success=True,
            exit_code=0,
            stdout=long_stdout,
            command="pip install",
            duration_seconds=1.0,
        )
        serialized = result.to_dict()

        assert len(serialized["stdout"]) <= 2000


class TestSandboxExecutionResult:
    """Tests for SandboxExecutionResult dataclass."""

    def test_inherits_test_execution_result(self):
        """Test that SandboxExecutionResult inherits from TestExecutionResult."""
        assert issubclass(SandboxExecutionResult, TestExecutionResult)

    def test_sandbox_specific_fields(self):
        """Test sandbox-specific fields are present."""
        result = SandboxExecutionResult(
            passed=True,
            exit_code=0,
            container_id="abc123",
            sandbox_image="python:3.11",
            project_mounted=True,
            sandbox_working_dir="/workspace",
        )

        assert result.container_id == "abc123"
        assert result.sandbox_image == "python:3.11"
        assert result.project_mounted is True
        assert result.sandbox_working_dir == "/workspace"

    def test_to_dict_includes_sandbox_fields(self):
        """Test that to_dict includes sandbox-specific fields."""
        result = SandboxExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=5,
            passed_tests=5,
            sandbox_image="python:3.11",
            sandbox_environment={"CI": "true"},
            project_mounted=True,
        )
        serialized = result.to_dict()

        assert serialized["sandbox_image"] == "python:3.11"
        assert serialized["sandbox_environment_keys"] == ["CI"]
        assert serialized["project_mounted"] is True


# =============================================================================
# Test SandboxTestRunner - Step 1: Execution Routed Through Sandbox
# =============================================================================

class TestStep1ExecutionRoutedThroughSandbox:
    """
    Feature #214, Step 1: Test-runner execution routed through sandbox

    Verify that test commands are executed inside Docker containers.
    """

    def test_builds_docker_run_command(self, temp_project_dir):
        """Test that Docker run command is properly built."""
        config = SandboxConfiguration(image="python:3.11-slim")
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest tests/ -v",
            project_path=temp_project_dir,
        )

        assert docker_cmd[0] == "docker"
        assert docker_cmd[1] == "run"
        assert "--rm" in docker_cmd
        assert "python:3.11-slim" in docker_cmd
        assert "pytest tests/ -v" in " ".join(docker_cmd)

    def test_network_isolation_by_default(self, temp_project_dir):
        """Test that network is isolated by default."""
        config = SandboxConfiguration()
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
        )

        assert "--network" in docker_cmd
        network_idx = docker_cmd.index("--network")
        assert docker_cmd[network_idx + 1] == "none"

    def test_custom_network_mode(self, temp_project_dir):
        """Test custom network mode configuration."""
        config = SandboxConfiguration(network_mode="bridge")
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
        )

        network_idx = docker_cmd.index("--network")
        assert docker_cmd[network_idx + 1] == "bridge"

    def test_memory_limit_applied(self, temp_project_dir):
        """Test memory limit is applied to container."""
        config = SandboxConfiguration(memory_limit="512m")
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
        )

        assert "--memory" in docker_cmd
        memory_idx = docker_cmd.index("--memory")
        assert docker_cmd[memory_idx + 1] == "512m"

    def test_cpu_limit_applied(self, temp_project_dir):
        """Test CPU limit is applied to container."""
        config = SandboxConfiguration(cpu_limit="1.5")
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
        )

        assert "--cpus" in docker_cmd
        cpu_idx = docker_cmd.index("--cpus")
        assert docker_cmd[cpu_idx + 1] == "1.5"


# =============================================================================
# Test SandboxTestRunner - Step 2: Sandbox Has Access to Project Files
# =============================================================================

class TestStep2SandboxHasAccessToProjectFiles:
    """
    Feature #214, Step 2: Sandbox has access to project files

    Verify that project directory is mounted correctly in the container.
    """

    def test_project_mounted_as_volume(self, temp_project_dir):
        """Test that project directory is mounted as volume."""
        config = SandboxConfiguration(project_mount="/workspace")
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
        )

        volume_args = [arg for arg in docker_cmd if str(temp_project_dir) in arg]
        assert len(volume_args) == 1
        assert "/workspace" in volume_args[0]

    def test_working_directory_set_correctly(self, temp_project_dir):
        """Test that working directory is set inside container."""
        config = SandboxConfiguration(
            project_mount="/workspace",
            working_directory="/workspace/tests",
        )
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
        )

        assert "-w" in docker_cmd
        w_idx = docker_cmd.index("-w")
        assert docker_cmd[w_idx + 1] == "/workspace/tests"

    def test_relative_working_directory(self, temp_project_dir):
        """Test relative working directory is handled correctly by run_in_sandbox."""
        config = SandboxConfiguration(project_mount="/workspace")
        runner = SandboxTestRunner(config=config)

        # Note: _build_docker_command takes working_directory as the final sandbox path
        # The run_in_sandbox method combines project_mount + working_directory
        # Here we test _build_docker_command directly with the expected combined path
        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
            working_directory="/workspace/src/tests",  # Already combined path
        )

        w_idx = docker_cmd.index("-w")
        assert docker_cmd[w_idx + 1] == "/workspace/src/tests"

    def test_additional_volumes_mounted(self, temp_project_dir):
        """Test additional volume mounts work."""
        config = SandboxConfiguration(
            volumes=["/cache:/root/.cache", "/data:/data:ro"],
        )
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
        )

        assert "/cache:/root/.cache" in docker_cmd
        assert "/data:/data:ro" in docker_cmd

    def test_project_not_found_returns_error(self, tmp_path):
        """Test that missing project directory returns error result."""
        runner = SandboxTestRunner()
        non_existent = tmp_path / "does-not-exist"

        result = runner.run_in_sandbox(
            command="pytest",
            project_dir=non_existent,
        )

        assert result.passed is False
        assert "does not exist" in result.error_message
        assert result.project_mounted is False


# =============================================================================
# Test SandboxTestRunner - Step 3: Test Dependencies Installed in Sandbox
# =============================================================================

class TestStep3TestDependenciesInstalledInSandbox:
    """
    Feature #214, Step 3: Test dependencies installed in sandbox

    Verify that test dependencies are installed before test execution.
    """

    def test_detects_python_requirements(self, temp_project_dir):
        """Test detection of Python requirements.txt."""
        runner = SandboxTestRunner()
        cmd, file = runner._detect_install_command(temp_project_dir)

        assert cmd is not None
        assert "pip install" in cmd
        assert file == "requirements.txt"

    def test_detects_python_requirements_test(self, temp_project_dir):
        """Test detection of requirements-test.txt."""
        # Remove regular requirements.txt
        (temp_project_dir / "requirements.txt").unlink()
        # Create requirements-test.txt
        (temp_project_dir / "requirements-test.txt").write_text("pytest\nmock")

        runner = SandboxTestRunner()
        cmd, file = runner._detect_install_command(temp_project_dir)

        assert "requirements-test.txt" in cmd
        assert file == "requirements-test.txt"

    def test_detects_pyproject_toml(self, temp_project_dir):
        """Test detection of pyproject.toml."""
        (temp_project_dir / "requirements.txt").unlink()
        (temp_project_dir / "pyproject.toml").write_text('[project]\nname = "test"')

        runner = SandboxTestRunner()
        cmd, file = runner._detect_install_command(temp_project_dir)

        assert "pip install" in cmd
        assert "-e ." in cmd
        assert file == "pyproject.toml"

    def test_detects_javascript_package_json(self, js_project_dir):
        """Test detection of JavaScript package.json."""
        runner = SandboxTestRunner()
        cmd, file = runner._detect_install_command(js_project_dir)

        assert "npm ci" in cmd
        assert file == "package.json"

    def test_no_dependencies_found(self, tmp_path):
        """Test when no dependency files exist."""
        empty_project = tmp_path / "empty-project"
        empty_project.mkdir()

        runner = SandboxTestRunner()
        cmd, file = runner._detect_install_command(empty_project)

        assert cmd is None
        assert file is None

    def test_custom_install_command_used(self, temp_project_dir):
        """Test custom install command takes precedence."""
        runner = SandboxTestRunner()
        cmd, file = runner._detect_install_command(
            temp_project_dir,
            custom_command="poetry install",
        )

        assert cmd == "poetry install"
        assert file is None

    def test_dependency_install_result_structure(self):
        """Test DependencyInstallResult has correct fields."""
        result = DependencyInstallResult(
            success=True,
            exit_code=0,
            stdout="Installing collected packages...",
            command="pip install -r requirements.txt",
            duration_seconds=10.5,
            dependencies_file="requirements.txt",
            dependency_count=15,
        )

        assert result.success is True
        assert result.exit_code == 0
        assert result.dependencies_file == "requirements.txt"
        assert result.dependency_count == 15


# =============================================================================
# Test SandboxTestRunner - Step 4: Consistent Test Environment
# =============================================================================

class TestStep4ConsistentTestEnvironment:
    """
    Feature #214, Step 4: Sandbox provides consistent test environment

    Verify that the sandbox provides a reproducible, consistent environment.
    """

    def test_uses_configured_image(self, temp_project_dir):
        """Test that configured Docker image is used."""
        config = SandboxConfiguration(image="python:3.11-slim")
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
        )

        assert "python:3.11-slim" in docker_cmd

    def test_environment_variables_passed(self, temp_project_dir):
        """Test that environment variables are passed to container."""
        config = SandboxConfiguration(
            environment={"CI": "true", "DEBUG": "1"},
        )
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
            environment=config.environment,
        )

        assert "-e" in docker_cmd
        env_args = [docker_cmd[i+1] for i, arg in enumerate(docker_cmd) if arg == "-e"]
        assert "CI=true" in env_args
        assert "DEBUG=1" in env_args

    def test_container_removed_after_execution(self, temp_project_dir):
        """Test that container is removed after execution by default."""
        config = SandboxConfiguration(remove_container=True)
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
        )

        assert "--rm" in docker_cmd

    def test_container_preserved_when_configured(self, temp_project_dir):
        """Test that container can be preserved if configured."""
        config = SandboxConfiguration(remove_container=False)
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
        )

        assert "--rm" not in docker_cmd

    def test_default_config_provides_isolation(self):
        """Test that default config provides secure isolation."""
        config = get_default_sandbox_config()

        assert config.network_mode == "none"  # No network by default
        assert config.remove_container is True  # Clean up after
        # Don't expose docker socket by default
        assert "/var/run/docker.sock" not in config.volumes


# =============================================================================
# Test SandboxTestRunner - Step 5: Results Captured from Sandbox
# =============================================================================

class TestStep5ResultsCapturedFromSandbox:
    """
    Feature #214, Step 5: Results captured from sandbox execution

    Verify that test results are properly captured from the sandbox.
    """

    def test_sandbox_result_includes_image(self, temp_project_dir, mock_docker_available):
        """Test that result includes sandbox image information."""
        config = SandboxConfiguration(image="python:3.11")
        runner = SandboxTestRunner(config=config)

        # Mock subprocess to return test output
        mock_docker_available.return_value = Mock(
            returncode=0,
            stdout="1 passed in 0.5s",
            stderr="",
        )

        result = runner.run_in_sandbox(
            command="pytest tests/ -v",
            project_dir=temp_project_dir,
            install_dependencies=False,
        )

        assert result.sandbox_image == "python:3.11"

    def test_sandbox_result_includes_project_mounted(self, temp_project_dir, mock_docker_available):
        """Test that result indicates project was mounted."""
        runner = SandboxTestRunner()

        mock_docker_available.return_value = Mock(
            returncode=0,
            stdout="1 passed",
            stderr="",
        )

        result = runner.run_in_sandbox(
            command="pytest",
            project_dir=temp_project_dir,
            install_dependencies=False,
        )

        assert result.project_mounted is True

    def test_sandbox_result_includes_working_dir(self, temp_project_dir, mock_docker_available):
        """Test that result includes working directory."""
        config = SandboxConfiguration(working_directory="/workspace/tests")
        runner = SandboxTestRunner(config=config)

        mock_docker_available.return_value = Mock(
            returncode=0,
            stdout="1 passed",
            stderr="",
        )

        result = runner.run_in_sandbox(
            command="pytest",
            project_dir=temp_project_dir,
            install_dependencies=False,
        )

        assert result.sandbox_working_dir == "/workspace/tests"

    def test_sandbox_result_includes_environment(self, temp_project_dir, mock_docker_available):
        """Test that result includes environment variables."""
        runner = SandboxTestRunner()

        mock_docker_available.return_value = Mock(
            returncode=0,
            stdout="1 passed",
            stderr="",
        )

        result = runner.run_in_sandbox(
            command="pytest",
            project_dir=temp_project_dir,
            environment={"CI": "true"},
            install_dependencies=False,
        )

        assert "CI" in result.sandbox_environment

    def test_parses_pytest_results_in_sandbox(self, temp_project_dir, mock_docker_available):
        """Test that pytest output is correctly parsed from sandbox."""
        runner = SandboxTestRunner()

        # Mock pytest output
        mock_docker_available.return_value = Mock(
            returncode=0,
            stdout="==================== 5 passed, 1 failed, 2 skipped in 1.23s ====================",
            stderr="",
        )

        result = runner.run_in_sandbox(
            command="pytest tests/ -v",
            project_dir=temp_project_dir,
            install_dependencies=False,
        )

        assert result.total_tests == 8
        assert result.passed_tests == 5
        assert result.failed_tests == 1
        assert result.skipped_tests == 2

    def test_captures_failed_test_details(self, temp_project_dir):
        """Test that failure details are captured from sandbox."""
        with patch("shutil.which") as mock_which, \
             patch("subprocess.run") as mock_run:
            # First call to docker info for availability check
            mock_which.return_value = "/usr/bin/docker"

            # Setup mock to handle both docker info check and actual test run
            def run_side_effect(*args, **kwargs):
                cmd = args[0] if args else kwargs.get("args", [])
                if isinstance(cmd, list) and "info" in cmd:
                    return Mock(returncode=0, stdout="", stderr="")
                # Test execution
                return Mock(
                    returncode=1,
                    stdout="FAILED tests/test_app.py::test_hello - AssertionError: assert 'Hi' == 'Hello'\n1 failed",
                    stderr="",
                )

            mock_run.side_effect = run_side_effect

            runner = SandboxTestRunner()
            runner._docker_available = None  # Force re-check

            result = runner.run_in_sandbox(
                command="pytest tests/ -v",
                project_dir=temp_project_dir,
                install_dependencies=False,
            )

            assert result.passed is False
            assert result.failed_tests >= 1


# =============================================================================
# Test Docker Availability Check
# =============================================================================

class TestDockerAvailabilityCheck:
    """Tests for Docker availability detection."""

    def test_docker_available_when_installed_and_running(self):
        """Test detection when Docker is installed and running."""
        with patch("shutil.which") as mock_which, \
             patch("subprocess.run") as mock_run:
            mock_which.return_value = "/usr/bin/docker"
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            runner = SandboxTestRunner()
            assert runner.is_docker_available is True

    def test_docker_unavailable_when_not_installed(self):
        """Test detection when Docker is not installed."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None

            runner = SandboxTestRunner()
            # Force re-check
            runner._docker_available = None
            assert runner.is_docker_available is False

    def test_docker_unavailable_when_daemon_not_running(self):
        """Test detection when Docker daemon is not running."""
        with patch("shutil.which") as mock_which, \
             patch("subprocess.run") as mock_run:
            mock_which.return_value = "/usr/bin/docker"
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="Cannot connect to the Docker daemon",
            )

            runner = SandboxTestRunner()
            runner._docker_available = None
            assert runner.is_docker_available is False

    def test_fallback_to_local_when_docker_unavailable(self, temp_project_dir):
        """Test fallback to local execution when Docker is unavailable."""
        with patch("shutil.which") as mock_which, \
             patch.object(SandboxTestRunner, "_check_docker_available", return_value=False), \
             patch("subprocess.run") as mock_run:
            mock_which.return_value = None

            # Mock local pytest execution
            mock_run.return_value = Mock(
                returncode=0,
                stdout="1 passed in 0.5s",
                stderr="",
            )

            runner = SandboxTestRunner()
            runner._docker_available = False

            result = runner.run(
                command="pytest tests/ -v",
                working_directory=temp_project_dir,
            )

            # Should fall back to local execution via parent class
            assert result.passed is True


# =============================================================================
# Test Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_is_sandbox_available_function(self):
        """Test is_sandbox_available convenience function."""
        with patch.object(SandboxTestRunner, "is_docker_available", new_callable=lambda: property(lambda self: True)):
            # Note: This test may fail in environments without Docker
            # The function should return a boolean
            result = is_sandbox_available()
            assert isinstance(result, bool)

    def test_get_default_sandbox_config(self):
        """Test get_default_sandbox_config convenience function."""
        config = get_default_sandbox_config()

        assert isinstance(config, SandboxConfiguration)
        assert config.image == DEFAULT_SANDBOX_IMAGE
        assert config.project_mount == DEFAULT_PROJECT_MOUNT

    def test_run_tests_in_sandbox_creates_runner(self, temp_project_dir, mock_docker_available):
        """Test run_tests_in_sandbox creates runner with config."""
        mock_docker_available.return_value = Mock(
            returncode=0,
            stdout="1 passed",
            stderr="",
        )

        result = run_tests_in_sandbox(
            command="pytest",
            project_dir=temp_project_dir,
            image="python:3.11",
            install_dependencies=False,
        )

        assert isinstance(result, SandboxExecutionResult)
        assert result.sandbox_image == "python:3.11"


# =============================================================================
# Test Audit Event Recording
# =============================================================================

class TestAuditEventRecording:
    """Tests for sandbox test execution audit event recording."""

    def test_record_sandbox_tests_executed_basic(self):
        """Test basic audit event recording."""
        mock_recorder = Mock()
        mock_recorder.record.return_value = 123

        result = SandboxExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=5,
            passed_tests=5,
            command="pytest tests/",
            sandbox_image="python:3.11",
            project_mounted=True,
        )

        event_id = record_sandbox_tests_executed(
            recorder=mock_recorder,
            run_id="test-run-123",
            result=result,
        )

        assert event_id == 123
        mock_recorder.record.assert_called_once()

        # Check event type
        call_args = mock_recorder.record.call_args
        assert call_args[0][0] == "test-run-123"
        assert call_args[0][1] == "sandbox_tests_executed"

    def test_record_sandbox_tests_executed_includes_sandbox_fields(self):
        """Test that sandbox-specific fields are included in event."""
        mock_recorder = Mock()
        mock_recorder.record.return_value = 1

        result = SandboxExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=1,
            passed_tests=1,
            command="pytest",
            sandbox_image="python:3.11",
            project_mounted=True,
            sandbox_working_dir="/workspace",
        )

        record_sandbox_tests_executed(
            recorder=mock_recorder,
            run_id="run-1",
            result=result,
        )

        payload = mock_recorder.record.call_args[1]["payload"]
        assert payload["sandbox_execution"] is True
        assert payload["sandbox_image"] == "python:3.11"
        assert payload["project_mounted"] is True
        assert payload["sandbox_working_dir"] == "/workspace"

    def test_record_sandbox_tests_executed_includes_dependency_info(self):
        """Test that dependency installation info is included."""
        mock_recorder = Mock()
        mock_recorder.record.return_value = 1

        dep_result = DependencyInstallResult(
            success=True,
            exit_code=0,
            command="pip install -r requirements.txt",
            dependencies_file="requirements.txt",
            duration_seconds=5.0,
        )

        result = SandboxExecutionResult(
            passed=True,
            exit_code=0,
            command="pytest",
            sandbox_image="python:3.11",
            dependency_install=dep_result,
        )

        record_sandbox_tests_executed(
            recorder=mock_recorder,
            run_id="run-1",
            result=result,
        )

        payload = mock_recorder.record.call_args[1]["payload"]
        assert "dependency_install" in payload
        assert payload["dependency_install"]["success"] is True
        assert payload["dependency_install"]["dependencies_file"] == "requirements.txt"


# =============================================================================
# Test API Package Exports
# =============================================================================

class TestApiPackageExports:
    """Test that all Feature #214 exports are available from api package."""

    def test_sandbox_configuration_exported(self):
        """Test SandboxConfiguration is exported from api."""
        from api import SandboxConfiguration
        assert SandboxConfiguration is not None

    def test_dependency_install_result_exported(self):
        """Test DependencyInstallResult is exported from api."""
        from api import DependencyInstallResult
        assert DependencyInstallResult is not None

    def test_sandbox_execution_result_exported(self):
        """Test SandboxExecutionResult is exported from api."""
        from api import SandboxExecutionResult
        assert SandboxExecutionResult is not None

    def test_sandbox_test_runner_exported(self):
        """Test SandboxTestRunner is exported from api."""
        from api import SandboxTestRunner
        assert SandboxTestRunner is not None

    def test_convenience_functions_exported(self):
        """Test convenience functions are exported from api."""
        from api import (
            run_tests_in_sandbox,
            is_sandbox_available,
            get_default_sandbox_config,
            record_sandbox_tests_executed,
        )
        assert run_tests_in_sandbox is not None
        assert is_sandbox_available is not None
        assert get_default_sandbox_config is not None
        assert record_sandbox_tests_executed is not None

    def test_constants_exported(self):
        """Test constants are exported from api."""
        from api import (
            DEFAULT_SANDBOX_IMAGE,
            DEFAULT_PROJECT_MOUNT,
            DEFAULT_SANDBOX_TIMEOUT,
            DEFAULT_INSTALL_TIMEOUT,
            DEPENDENCY_FILES,
        )
        assert DEFAULT_SANDBOX_IMAGE is not None
        assert DEFAULT_PROJECT_MOUNT == "/workspace"
        assert DEFAULT_SANDBOX_TIMEOUT == 600
        assert DEFAULT_INSTALL_TIMEOUT == 180
        assert "python" in DEPENDENCY_FILES


# =============================================================================
# Test Feature #214 Verification Steps Summary
# =============================================================================

class TestFeature214VerificationSteps:
    """
    Summary tests that verify all 5 feature steps are implemented.
    """

    def test_step1_execution_routed_through_sandbox(self, temp_project_dir):
        """Step 1: Test-runner execution routed through sandbox."""
        runner = SandboxTestRunner()
        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
        )

        # Verify Docker run command is built
        assert docker_cmd[0] == "docker"
        assert docker_cmd[1] == "run"
        assert "pytest" in " ".join(docker_cmd)

    def test_step2_sandbox_has_project_access(self, temp_project_dir):
        """Step 2: Sandbox has access to project files."""
        config = SandboxConfiguration(project_mount="/workspace")
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
        )

        # Verify volume mount includes project path
        volume_arg = [a for a in docker_cmd if str(temp_project_dir) in a][0]
        assert "/workspace" in volume_arg

    def test_step3_dependencies_installed_in_sandbox(self, temp_project_dir):
        """Step 3: Test dependencies installed in sandbox."""
        runner = SandboxTestRunner()

        # Verify dependency detection works
        cmd, file = runner._detect_install_command(temp_project_dir)
        assert cmd is not None
        assert "pip install" in cmd or "npm" in cmd

    def test_step4_consistent_environment(self):
        """Step 4: Sandbox provides consistent test environment."""
        config = SandboxConfiguration(
            image="python:3.11-slim",
            network_mode="none",
        )

        # Verify config provides consistent settings
        assert config.image == "python:3.11-slim"
        assert config.network_mode == "none"  # Isolated network
        assert config.remove_container is True  # Clean up

    def test_step5_results_captured_from_sandbox(self):
        """Step 5: Results captured from sandbox execution."""
        result = SandboxExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=5,
            passed_tests=5,
            command="pytest",
            sandbox_image="python:3.11",
            project_mounted=True,
            sandbox_working_dir="/workspace",
        )

        # Verify all sandbox-specific fields are captured
        assert result.sandbox_image is not None
        assert result.project_mounted is True
        assert result.sandbox_working_dir is not None
        assert isinstance(result.to_dict(), dict)


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_timeout_during_sandbox_execution(self, temp_project_dir):
        """Test handling of timeout during sandbox execution."""
        with patch("shutil.which") as mock_which, \
             patch("subprocess.run") as mock_run:
            mock_which.return_value = "/usr/bin/docker"

            # First call succeeds (docker info), second call times out (test execution)
            call_count = [0]
            def run_side_effect(*args, **kwargs):
                call_count[0] += 1
                cmd = args[0] if args else kwargs.get("args", [])
                if isinstance(cmd, list) and "info" in cmd:
                    return Mock(returncode=0, stdout="", stderr="")
                # Test execution times out
                raise subprocess.TimeoutExpired(
                    cmd="docker run ...",
                    timeout=60,
                    output=b"",
                    stderr=b"",
                )

            mock_run.side_effect = run_side_effect

            runner = SandboxTestRunner()
            runner._docker_available = None  # Force re-check

            result = runner.run_in_sandbox(
                command="pytest",
                project_dir=temp_project_dir,
                timeout_seconds=60,
                install_dependencies=False,
            )

            assert result.passed is False
            assert "timed out" in result.error_message.lower()

    def test_empty_project_directory(self, tmp_path):
        """Test handling of empty project directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        runner = SandboxTestRunner()

        # Should still work, just no dependencies to install
        cmd, file = runner._detect_install_command(empty_dir)
        assert cmd is None
        assert file is None

    def test_invalid_docker_command_error(self, temp_project_dir, mock_docker_available):
        """Test handling of Docker command errors."""
        mock_docker_available.side_effect = FileNotFoundError("docker not found")

        runner = SandboxTestRunner()
        runner._docker_available = True  # Force thinking Docker is available

        result = runner.run_in_sandbox(
            command="pytest",
            project_dir=temp_project_dir,
            install_dependencies=False,
        )

        assert result.passed is False
        assert result.error_message is not None

    def test_very_long_command(self, temp_project_dir):
        """Test handling of very long test commands."""
        long_command = "pytest " + " ".join([f"test_{i}.py" for i in range(100)])

        runner = SandboxTestRunner()
        docker_cmd = runner._build_docker_command(
            command=long_command,
            project_path=temp_project_dir,
        )

        # Should handle long commands via shell
        assert "sh" in docker_cmd
        assert "-c" in docker_cmd

    def test_special_characters_in_environment(self, temp_project_dir):
        """Test handling of special characters in environment variables."""
        config = SandboxConfiguration(
            environment={
                "PATH": "/usr/bin:/bin",
                "QUOTE": 'value with "quotes"',
            }
        )
        runner = SandboxTestRunner(config=config)

        docker_cmd = runner._build_docker_command(
            command="pytest",
            project_path=temp_project_dir,
            environment=config.environment,
        )

        # Should include environment variables
        assert "-e" in docker_cmd
