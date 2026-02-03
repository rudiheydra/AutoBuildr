"""
Feature #200: Scaffolding generates minimal CLAUDE.md if missing

This test suite verifies that the scaffolding module can generate a minimal
CLAUDE.md file when a project doesn't have one.

Feature Steps:
1. Check if CLAUDE.md exists in project root
2. If missing, generate minimal CLAUDE.md from project metadata
3. Include: project name, tech stack summary, key directories
4. CLAUDE.md provides context for Claude CLI agents
5. Existing CLAUDE.md is never overwritten
"""
import json
import tempfile
from pathlib import Path

import pytest

from api.scaffolding import (
    # Feature #200: CLAUDE.md generation
    # Data classes
    ProjectMetadata,
    ClaudeMdResult,
    # Convenience functions
    claude_md_exists,
    generate_claude_md,
    ensure_claude_md,
    scaffold_with_claude_md,
    generate_claude_md_content,
    # Constants
    CLAUDE_MD_FILE,
    DEFAULT_FILE_PERMISSIONS,
    # Feature #199 functions for comparison
    scaffold_claude_directory,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_with_markers(temp_project_dir):
    """Create a project with common marker files for tech detection."""
    # Python project markers
    (temp_project_dir / "requirements.txt").write_text("fastapi\nsqlalchemy\npytest\n")
    (temp_project_dir / "pyproject.toml").write_text("[project]\nname = 'test-project'\n")

    # Node.js project markers
    package_json = {
        "name": "test-project",
        "dependencies": {
            "react": "^18.0.0",
            "tailwindcss": "^3.0.0",
        },
        "devDependencies": {
            "@playwright/test": "^1.40.0",
            "typescript": "^5.0.0",
        }
    }
    (temp_project_dir / "package.json").write_text(json.dumps(package_json))
    (temp_project_dir / "tsconfig.json").write_text("{}")

    # Common directories
    (temp_project_dir / "src").mkdir()
    (temp_project_dir / "api").mkdir()
    (temp_project_dir / "tests").mkdir()
    (temp_project_dir / "docs").mkdir()

    # Docker
    (temp_project_dir / "Dockerfile").write_text("FROM python:3.11\n")

    return temp_project_dir


@pytest.fixture
def sample_project_context():
    """Create a sample project_context dict like OctoRequestPayload uses."""
    return {
        "name": "MyTestApp",
        "tech_stack": ["Python", "React", "FastAPI"],
        "directory_structure": [
            {"path": "api", "description": "Backend API endpoints"},
            {"path": "ui", "description": "Frontend React app"},
            {"path": "tests", "description": "Test suites"},
        ],
        "app_spec_summary": "A full-stack web application for managing tasks.",
        "settings": {},
        "environment": "development",
    }


# =============================================================================
# Test Step 1: Check if CLAUDE.md exists in project root
# =============================================================================

class TestStep1CheckClaudeMdExists:
    """Test Step 1: Check if CLAUDE.md exists in project root."""

    def test_returns_false_when_claude_md_missing(self, temp_project_dir):
        """claude_md_exists() returns False when CLAUDE.md doesn't exist."""
        assert claude_md_exists(temp_project_dir) is False

    def test_returns_true_when_claude_md_exists(self, temp_project_dir):
        """claude_md_exists() returns True when CLAUDE.md exists."""
        (temp_project_dir / CLAUDE_MD_FILE).write_text("# My Project\n")
        assert claude_md_exists(temp_project_dir) is True

    def test_detects_existing_claude_md_case_sensitive(self, temp_project_dir):
        """Detection is case-sensitive (CLAUDE.md, not claude.md)."""
        (temp_project_dir / "claude.md").write_text("# lowercase\n")
        assert claude_md_exists(temp_project_dir) is False

        (temp_project_dir / CLAUDE_MD_FILE).write_text("# uppercase\n")
        assert claude_md_exists(temp_project_dir) is True

    def test_generate_claude_md_detects_existing(self, temp_project_dir):
        """generate_claude_md() correctly reports existing file."""
        (temp_project_dir / CLAUDE_MD_FILE).write_text("# Existing\n")

        result = generate_claude_md(temp_project_dir)

        assert result.existed is True
        assert result.skipped is True
        assert result.created is False


# =============================================================================
# Test Step 2: Generate minimal CLAUDE.md from project metadata
# =============================================================================

class TestStep2GenerateFromMetadata:
    """Test Step 2: If missing, generate minimal CLAUDE.md from project metadata."""

    def test_generates_claude_md_when_missing(self, temp_project_dir):
        """CLAUDE.md is created when it doesn't exist."""
        result = generate_claude_md(temp_project_dir)

        assert result.created is True
        assert result.error is None
        assert (temp_project_dir / CLAUDE_MD_FILE).exists()

    def test_uses_provided_metadata(self, temp_project_dir):
        """Generated content uses provided ProjectMetadata."""
        metadata = ProjectMetadata(
            name="CustomProject",
            tech_stack=["Rust", "WebAssembly"],
            key_directories=[("src", "Source code"), ("wasm", "WebAssembly output")],
            description="A high-performance computing project.",
        )

        result = generate_claude_md(temp_project_dir, metadata=metadata)

        assert result.created is True
        content = result.content
        assert "# CustomProject" in content
        assert "Rust" in content
        assert "WebAssembly" in content
        assert "`src/`" in content
        assert "`wasm/`" in content
        assert "high-performance computing" in content

    def test_uses_project_context_dict(self, temp_project_dir, sample_project_context):
        """Generated content uses project_context dict."""
        result = generate_claude_md(temp_project_dir, project_context=sample_project_context)

        assert result.created is True
        content = result.content
        assert "# MyTestApp" in content
        assert "Python" in content
        assert "React" in content
        assert "FastAPI" in content
        assert "`api/`" in content
        assert "Backend API endpoints" in content

    def test_auto_detects_metadata_from_directory(self, project_with_markers):
        """Metadata is auto-detected from project directory."""
        result = generate_claude_md(project_with_markers)

        assert result.created is True
        content = result.content

        # Should detect tech stack from marker files
        assert "Python" in content
        assert "React" in content
        assert "TypeScript" in content
        assert "Playwright" in content
        assert "FastAPI" in content
        assert "Docker" in content

        # Should detect directories
        assert "`src/`" in content
        assert "`api/`" in content
        assert "`tests/`" in content

    def test_uses_directory_name_as_fallback_project_name(self, temp_project_dir):
        """Uses directory name as project name when not provided."""
        result = generate_claude_md(temp_project_dir)

        content = result.content
        assert f"# {temp_project_dir.name}" in content


# =============================================================================
# Test Step 3: Include project name, tech stack summary, key directories
# =============================================================================

class TestStep3IncludesRequiredContent:
    """Test Step 3: Include: project name, tech stack summary, key directories."""

    def test_includes_project_name_as_heading(self, temp_project_dir):
        """Generated content includes project name as main heading."""
        metadata = ProjectMetadata(name="TestProject", tech_stack=["Python"])

        result = generate_claude_md(temp_project_dir, metadata=metadata)

        assert "# TestProject" in result.content

    def test_includes_tech_stack_section(self, temp_project_dir):
        """Generated content includes Tech Stack section."""
        metadata = ProjectMetadata(
            name="TestProject",
            tech_stack=["Python", "FastAPI", "PostgreSQL"],
        )

        result = generate_claude_md(temp_project_dir, metadata=metadata)

        assert "## Tech Stack" in result.content
        assert "- Python" in result.content
        assert "- FastAPI" in result.content
        assert "- PostgreSQL" in result.content

    def test_includes_project_structure_section(self, temp_project_dir):
        """Generated content includes Project Structure section."""
        metadata = ProjectMetadata(
            name="TestProject",
            tech_stack=["Python"],
            key_directories=[
                ("api", "Backend API"),
                ("ui", "Frontend components"),
                ("tests", "Test suites"),
            ],
        )

        result = generate_claude_md(temp_project_dir, metadata=metadata)

        assert "## Project Structure" in result.content
        assert "`api/` - Backend API" in result.content
        assert "`ui/` - Frontend components" in result.content
        assert "`tests/` - Test suites" in result.content

    def test_includes_getting_started_section(self, temp_project_dir):
        """Generated content includes Getting Started section."""
        result = generate_claude_md(temp_project_dir)

        assert "## Getting Started" in result.content
        assert "context for Claude Code agents" in result.content

    def test_includes_description_when_provided(self, temp_project_dir):
        """Generated content includes description when provided."""
        metadata = ProjectMetadata(
            name="TestProject",
            tech_stack=["Python"],
            description="A powerful task management system.",
        )

        result = generate_claude_md(temp_project_dir, metadata=metadata)

        assert "A powerful task management system." in result.content

    def test_handles_empty_tech_stack(self, temp_project_dir):
        """Generated content handles empty tech stack gracefully."""
        metadata = ProjectMetadata(name="EmptyProject", tech_stack=[])

        result = generate_claude_md(temp_project_dir, metadata=metadata)

        assert result.created is True
        assert "# EmptyProject" in result.content
        # Tech Stack section should not appear if empty
        assert "## Tech Stack" not in result.content

    def test_handles_empty_key_directories(self, temp_project_dir):
        """Generated content handles empty key directories gracefully."""
        metadata = ProjectMetadata(name="EmptyProject", tech_stack=["Python"], key_directories=[])

        result = generate_claude_md(temp_project_dir, metadata=metadata)

        assert result.created is True
        # Project Structure section should not appear if empty
        assert "## Project Structure" not in result.content


# =============================================================================
# Test Step 4: CLAUDE.md provides context for Claude CLI agents
# =============================================================================

class TestStep4ProvidesContext:
    """Test Step 4: CLAUDE.md provides context for Claude CLI agents."""

    def test_file_is_written_to_project_root(self, temp_project_dir):
        """CLAUDE.md is written to project root directory."""
        result = generate_claude_md(temp_project_dir)

        assert result.created is True
        assert result.path == temp_project_dir / CLAUDE_MD_FILE
        assert (temp_project_dir / CLAUDE_MD_FILE).exists()

    def test_file_has_correct_permissions(self, temp_project_dir):
        """Generated file has correct permissions (0644)."""
        result = generate_claude_md(temp_project_dir)

        mode = (temp_project_dir / CLAUDE_MD_FILE).stat().st_mode & 0o777
        assert mode == DEFAULT_FILE_PERMISSIONS

    def test_file_is_readable_markdown(self, temp_project_dir):
        """Generated file is valid, readable markdown."""
        metadata = ProjectMetadata(
            name="TestProject",
            tech_stack=["Python", "React"],
            key_directories=[("src", "Source code")],
        )

        result = generate_claude_md(temp_project_dir, metadata=metadata)

        # Read the file back and verify content
        file_content = (temp_project_dir / CLAUDE_MD_FILE).read_text()
        assert file_content == result.content
        assert file_content.startswith("# TestProject")

    def test_content_is_helpful_for_agents(self, temp_project_dir, sample_project_context):
        """Generated content provides helpful context for agents."""
        result = generate_claude_md(temp_project_dir, project_context=sample_project_context)

        content = result.content

        # Should provide clear project identification
        assert "# MyTestApp" in content

        # Should list technologies
        assert "Python" in content
        assert "React" in content

        # Should explain directories
        assert "api" in content
        assert "ui" in content

        # Should mention Claude Code agents
        assert "Claude Code agents" in content


# =============================================================================
# Test Step 5: Existing CLAUDE.md is never overwritten
# =============================================================================

class TestStep5NeverOverwriteExisting:
    """Test Step 5: Existing CLAUDE.md is never overwritten."""

    def test_does_not_overwrite_existing_file(self, temp_project_dir):
        """Existing CLAUDE.md is never overwritten by default."""
        original_content = "# My Custom Project\n\nThis is my custom CLAUDE.md file.\n"
        (temp_project_dir / CLAUDE_MD_FILE).write_text(original_content)

        result = generate_claude_md(temp_project_dir)

        assert result.existed is True
        assert result.skipped is True
        assert result.created is False

        # Verify original content is preserved
        current_content = (temp_project_dir / CLAUDE_MD_FILE).read_text()
        assert current_content == original_content

    def test_overwrite_flag_allows_replacement(self, temp_project_dir):
        """overwrite=True allows replacing existing CLAUDE.md."""
        original_content = "# Old Content\n"
        (temp_project_dir / CLAUDE_MD_FILE).write_text(original_content)

        metadata = ProjectMetadata(name="NewProject", tech_stack=["Rust"])
        result = generate_claude_md(temp_project_dir, metadata=metadata, overwrite=True)

        assert result.existed is True
        assert result.skipped is False
        assert result.created is True

        # Verify content was replaced
        new_content = (temp_project_dir / CLAUDE_MD_FILE).read_text()
        assert "# NewProject" in new_content
        assert "Old Content" not in new_content

    def test_ensure_claude_md_never_overwrites(self, temp_project_dir):
        """ensure_claude_md() convenience function never overwrites."""
        original_content = "# Existing\n"
        (temp_project_dir / CLAUDE_MD_FILE).write_text(original_content)

        result = ensure_claude_md(temp_project_dir)

        assert result.existed is True
        assert result.skipped is True
        assert (temp_project_dir / CLAUDE_MD_FILE).read_text() == original_content

    def test_multiple_calls_preserve_existing(self, temp_project_dir):
        """Multiple calls don't modify existing CLAUDE.md."""
        # First call creates
        result1 = generate_claude_md(temp_project_dir)
        original_content = (temp_project_dir / CLAUDE_MD_FILE).read_text()

        # Subsequent calls skip
        result2 = generate_claude_md(temp_project_dir)
        result3 = generate_claude_md(temp_project_dir)

        assert result1.created is True
        assert result2.skipped is True
        assert result3.skipped is True

        # Content unchanged
        assert (temp_project_dir / CLAUDE_MD_FILE).read_text() == original_content


# =============================================================================
# Test ProjectMetadata Data Class
# =============================================================================

class TestProjectMetadata:
    """Test ProjectMetadata data class."""

    def test_to_dict_serialization(self):
        """to_dict() produces valid serializable output."""
        metadata = ProjectMetadata(
            name="TestProject",
            tech_stack=["Python", "React"],
            key_directories=[("src", "Source code"), ("tests", "Test suites")],
            description="A test project.",
        )

        data = metadata.to_dict()

        assert data["name"] == "TestProject"
        assert data["tech_stack"] == ["Python", "React"]
        assert len(data["key_directories"]) == 2
        assert data["key_directories"][0] == {"path": "src", "description": "Source code"}
        assert data["description"] == "A test project."

    def test_from_project_context_with_full_data(self, sample_project_context):
        """from_project_context() parses complete context correctly."""
        metadata = ProjectMetadata.from_project_context(sample_project_context)

        assert metadata.name == "MyTestApp"
        assert "Python" in metadata.tech_stack
        assert "React" in metadata.tech_stack
        assert ("api", "Backend API endpoints") in metadata.key_directories
        assert metadata.description == "A full-stack web application for managing tasks."

    def test_from_project_context_with_minimal_data(self):
        """from_project_context() handles minimal context."""
        context = {"name": "MinimalProject"}
        metadata = ProjectMetadata.from_project_context(context)

        assert metadata.name == "MinimalProject"
        assert metadata.tech_stack == []
        assert metadata.key_directories == []
        assert metadata.description == ""

    def test_from_project_context_with_string_tech_stack(self):
        """from_project_context() converts comma-separated string tech_stack."""
        context = {
            "name": "StringStackProject",
            "tech_stack": "Python, React, FastAPI",
        }
        metadata = ProjectMetadata.from_project_context(context)

        assert "Python" in metadata.tech_stack
        assert "React" in metadata.tech_stack
        assert "FastAPI" in metadata.tech_stack

    def test_from_project_context_with_simple_directory_list(self):
        """from_project_context() handles simple string list for directories."""
        context = {
            "name": "SimpleProject",
            "directory_structure": ["src", "tests", "docs"],
        }
        metadata = ProjectMetadata.from_project_context(context)

        assert ("src", "") in metadata.key_directories
        assert ("tests", "") in metadata.key_directories
        assert ("docs", "") in metadata.key_directories

    def test_from_directory_detects_project_name(self, temp_project_dir):
        """from_directory() uses directory name as project name."""
        metadata = ProjectMetadata.from_directory(temp_project_dir)

        assert metadata.name == temp_project_dir.name

    def test_from_directory_detects_tech_stack(self, project_with_markers):
        """from_directory() detects technologies from marker files."""
        metadata = ProjectMetadata.from_directory(project_with_markers)

        assert "Python" in metadata.tech_stack
        assert "React" in metadata.tech_stack
        assert "TypeScript" in metadata.tech_stack

    def test_from_directory_detects_key_directories(self, project_with_markers):
        """from_directory() detects key directories."""
        metadata = ProjectMetadata.from_directory(project_with_markers)

        dir_names = [d[0] for d in metadata.key_directories]
        assert "src" in dir_names
        assert "api" in dir_names
        assert "tests" in dir_names


# =============================================================================
# Test ClaudeMdResult Data Class
# =============================================================================

class TestClaudeMdResult:
    """Test ClaudeMdResult data class."""

    def test_to_dict_serialization(self, temp_project_dir):
        """to_dict() produces valid serializable output."""
        result = generate_claude_md(temp_project_dir)

        data = result.to_dict()

        assert "path" in data
        assert "existed" in data
        assert "created" in data
        assert "skipped" in data
        assert "error" in data
        assert "content_length" in data

    def test_content_stored_in_result(self, temp_project_dir):
        """Generated content is stored in result."""
        result = generate_claude_md(temp_project_dir)

        assert result.content is not None
        assert len(result.content) > 0
        assert result.to_dict()["content_length"] == len(result.content)


# =============================================================================
# Test generate_claude_md_content Function
# =============================================================================

class TestGenerateClaudeMdContent:
    """Test generate_claude_md_content function."""

    def test_returns_string(self):
        """Function returns a string."""
        metadata = ProjectMetadata(name="Test", tech_stack=["Python"])
        content = generate_claude_md_content(metadata)

        assert isinstance(content, str)
        assert len(content) > 0

    def test_content_is_valid_markdown(self):
        """Generated content is valid markdown."""
        metadata = ProjectMetadata(
            name="Test",
            tech_stack=["Python", "React"],
            key_directories=[("src", "Source")],
            description="A project.",
        )
        content = generate_claude_md_content(metadata)

        # Check markdown structure
        assert content.startswith("# Test\n")
        assert "## Tech Stack" in content
        assert "## Project Structure" in content
        assert "## Getting Started" in content

    def test_handles_special_characters_in_name(self):
        """Handles special characters in project name."""
        metadata = ProjectMetadata(name="My Project (v2.0)", tech_stack=["Python"])
        content = generate_claude_md_content(metadata)

        assert "# My Project (v2.0)" in content


# =============================================================================
# Test scaffold_with_claude_md Function
# =============================================================================

class TestScaffoldWithClaudeMd:
    """Test scaffold_with_claude_md combined function."""

    def test_creates_both_structure_and_claude_md(self, temp_project_dir):
        """Creates both .claude directory structure and CLAUDE.md."""
        scaffold_result, claude_md_result = scaffold_with_claude_md(temp_project_dir)

        # Directory structure created
        assert scaffold_result.success
        assert (temp_project_dir / ".claude").is_dir()
        assert (temp_project_dir / ".claude" / "agents" / "generated").is_dir()

        # CLAUDE.md created
        assert claude_md_result is not None
        assert claude_md_result.created
        assert (temp_project_dir / CLAUDE_MD_FILE).exists()

    def test_uses_project_context(self, temp_project_dir, sample_project_context):
        """Uses project_context for CLAUDE.md generation."""
        scaffold_result, claude_md_result = scaffold_with_claude_md(
            temp_project_dir,
            project_context=sample_project_context,
        )

        assert claude_md_result.created
        assert "# MyTestApp" in claude_md_result.content

    def test_skips_claude_md_when_disabled(self, temp_project_dir):
        """Skips CLAUDE.md generation when include_claude_md=False."""
        scaffold_result, claude_md_result = scaffold_with_claude_md(
            temp_project_dir,
            include_claude_md=False,
        )

        assert scaffold_result.success
        assert claude_md_result is None
        assert not (temp_project_dir / CLAUDE_MD_FILE).exists()

    def test_preserves_existing_claude_md(self, temp_project_dir):
        """Does not overwrite existing CLAUDE.md."""
        original = "# Existing Project\n"
        (temp_project_dir / CLAUDE_MD_FILE).write_text(original)

        scaffold_result, claude_md_result = scaffold_with_claude_md(temp_project_dir)

        assert claude_md_result.existed
        assert claude_md_result.skipped
        assert (temp_project_dir / CLAUDE_MD_FILE).read_text() == original


# =============================================================================
# Test Tech Stack Detection
# =============================================================================

class TestTechStackDetection:
    """Test auto-detection of tech stack from marker files."""

    def test_detects_python_from_requirements(self, temp_project_dir):
        """Detects Python from requirements.txt."""
        (temp_project_dir / "requirements.txt").write_text("requests\n")

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        assert "Python" in metadata.tech_stack

    def test_detects_python_from_pyproject(self, temp_project_dir):
        """Detects Python from pyproject.toml."""
        (temp_project_dir / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        assert "Python" in metadata.tech_stack

    def test_detects_node_from_package_json(self, temp_project_dir):
        """Detects Node.js from package.json."""
        (temp_project_dir / "package.json").write_text('{"name": "test"}')

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        assert "Node.js" in metadata.tech_stack

    def test_detects_typescript_from_tsconfig(self, temp_project_dir):
        """Detects TypeScript from tsconfig.json."""
        (temp_project_dir / "tsconfig.json").write_text("{}")

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        assert "TypeScript" in metadata.tech_stack

    def test_detects_docker_from_dockerfile(self, temp_project_dir):
        """Detects Docker from Dockerfile."""
        (temp_project_dir / "Dockerfile").write_text("FROM python:3.11\n")

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        assert "Docker" in metadata.tech_stack

    def test_detects_react_from_package_dependencies(self, temp_project_dir):
        """Detects React from package.json dependencies."""
        pkg = {"dependencies": {"react": "^18.0.0"}}
        (temp_project_dir / "package.json").write_text(json.dumps(pkg))

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        assert "React" in metadata.tech_stack

    def test_detects_vue_from_package_dependencies(self, temp_project_dir):
        """Detects Vue from package.json dependencies."""
        pkg = {"dependencies": {"vue": "^3.0.0"}}
        (temp_project_dir / "package.json").write_text(json.dumps(pkg))

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        assert "Vue" in metadata.tech_stack

    def test_detects_nextjs_from_package_dependencies(self, temp_project_dir):
        """Detects Next.js from package.json dependencies."""
        pkg = {"dependencies": {"next": "^14.0.0"}}
        (temp_project_dir / "package.json").write_text(json.dumps(pkg))

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        assert "Next.js" in metadata.tech_stack

    def test_detects_fastapi_from_requirements(self, temp_project_dir):
        """Detects FastAPI from requirements.txt."""
        (temp_project_dir / "requirements.txt").write_text("fastapi\nuvicorn\n")

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        assert "FastAPI" in metadata.tech_stack

    def test_detects_flask_from_requirements(self, temp_project_dir):
        """Detects Flask from requirements.txt."""
        (temp_project_dir / "requirements.txt").write_text("flask\n")

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        assert "Flask" in metadata.tech_stack

    def test_detects_playwright_from_package(self, temp_project_dir):
        """Detects Playwright from package.json."""
        pkg = {"devDependencies": {"@playwright/test": "^1.40.0"}}
        (temp_project_dir / "package.json").write_text(json.dumps(pkg))

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        assert "Playwright" in metadata.tech_stack

    def test_no_duplicates_in_tech_stack(self, temp_project_dir):
        """Tech stack has no duplicate entries."""
        # Create multiple markers for Python
        (temp_project_dir / "requirements.txt").write_text("fastapi\n")
        (temp_project_dir / "pyproject.toml").write_text("[project]\n")
        (temp_project_dir / "setup.py").write_text("")

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        # Should only have Python once
        python_count = metadata.tech_stack.count("Python")
        assert python_count == 1


# =============================================================================
# Test Key Directory Detection
# =============================================================================

class TestKeyDirectoryDetection:
    """Test auto-detection of key directories."""

    def test_detects_src_directory(self, temp_project_dir):
        """Detects src directory."""
        (temp_project_dir / "src").mkdir()

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        dir_names = [d[0] for d in metadata.key_directories]
        assert "src" in dir_names

    def test_detects_tests_directory(self, temp_project_dir):
        """Detects tests directory."""
        (temp_project_dir / "tests").mkdir()

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        dir_names = [d[0] for d in metadata.key_directories]
        assert "tests" in dir_names

    def test_detects_api_directory(self, temp_project_dir):
        """Detects api directory."""
        (temp_project_dir / "api").mkdir()

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        dir_names = [d[0] for d in metadata.key_directories]
        assert "api" in dir_names

    def test_provides_descriptions_for_known_directories(self, temp_project_dir):
        """Provides descriptions for recognized directories."""
        (temp_project_dir / "src").mkdir()
        (temp_project_dir / "tests").mkdir()
        (temp_project_dir / "docs").mkdir()

        metadata = ProjectMetadata.from_directory(temp_project_dir)

        # Check descriptions are provided
        dir_dict = {d[0]: d[1] for d in metadata.key_directories}
        assert "Source code" in dir_dict.get("src", "")
        assert "Test" in dir_dict.get("tests", "")
        assert "Documentation" in dir_dict.get("docs", "")


# =============================================================================
# Test Error Handling
# =============================================================================

class TestErrorHandling:
    """Test error handling scenarios."""

    def test_handles_unreadable_package_json(self, temp_project_dir):
        """Handles malformed package.json gracefully."""
        (temp_project_dir / "package.json").write_text("not valid json")

        # Should not raise, just skip parsing
        metadata = ProjectMetadata.from_directory(temp_project_dir)

        assert "Node.js" in metadata.tech_stack  # Still detects file exists
        # React should not be detected (can't parse dependencies)
        assert "React" not in metadata.tech_stack


# =============================================================================
# Test Integration
# =============================================================================

class TestIntegration:
    """Integration tests for CLAUDE.md generation."""

    def test_full_workflow_with_new_project(self, temp_project_dir):
        """Test complete workflow for a new project."""
        # Create project markers
        (temp_project_dir / "requirements.txt").write_text("fastapi\n")
        (temp_project_dir / "src").mkdir()
        (temp_project_dir / "tests").mkdir()

        # Generate CLAUDE.md
        result = generate_claude_md(temp_project_dir)

        assert result.created
        assert result.error is None

        # Verify file contents
        content = (temp_project_dir / CLAUDE_MD_FILE).read_text()
        assert f"# {temp_project_dir.name}" in content
        assert "Python" in content
        assert "FastAPI" in content
        assert "`src/`" in content
        assert "`tests/`" in content

    def test_full_workflow_with_existing_project(self, temp_project_dir):
        """Test workflow with existing CLAUDE.md."""
        # Create existing CLAUDE.md
        original = "# My Custom Project\n\nCustom instructions.\n"
        (temp_project_dir / CLAUDE_MD_FILE).write_text(original)

        # Try to generate
        result = generate_claude_md(temp_project_dir)

        # Should be skipped
        assert result.skipped
        assert result.existed

        # Original content preserved
        assert (temp_project_dir / CLAUDE_MD_FILE).read_text() == original

    def test_api_package_exports(self):
        """Test that exports are available from api package."""
        from api import (
            ProjectMetadata,
            ClaudeMdResult,
            claude_md_exists,
            generate_claude_md,
            ensure_claude_md,
            scaffold_with_claude_md,
            CLAUDE_MD_FILE,
            DEFAULT_FILE_PERMISSIONS,
        )

        assert ProjectMetadata is not None
        assert ClaudeMdResult is not None
        assert claude_md_exists is not None
        assert generate_claude_md is not None
        assert ensure_claude_md is not None
        assert scaffold_with_claude_md is not None
        assert CLAUDE_MD_FILE == "CLAUDE.md"
        assert DEFAULT_FILE_PERMISSIONS == 0o644


# =============================================================================
# Test Feature #200 Verification Steps
# =============================================================================

class TestFeature200VerificationSteps:
    """
    Comprehensive tests for each Feature #200 verification step.

    These tests verify all 5 feature steps are implemented correctly.
    """

    def test_step1_check_claude_md_exists(self, temp_project_dir):
        """
        Step 1: Check if CLAUDE.md exists in project root

        Verification:
        - claude_md_exists() returns False when file is missing
        - claude_md_exists() returns True when file exists
        - generate_claude_md() detects existing file via result.existed
        """
        # Missing file
        assert claude_md_exists(temp_project_dir) is False

        # Create file
        (temp_project_dir / CLAUDE_MD_FILE).write_text("# Test\n")

        # Existing file
        assert claude_md_exists(temp_project_dir) is True

        # Result reports existed
        result = generate_claude_md(temp_project_dir)
        assert result.existed is True

    def test_step2_generate_from_metadata(self, temp_project_dir, sample_project_context):
        """
        Step 2: If missing, generate minimal CLAUDE.md from project metadata

        Verification:
        - CLAUDE.md created when missing
        - Content generated from ProjectMetadata
        - Content generated from project_context dict
        - Auto-detection from directory structure works
        """
        # From project_context
        result = generate_claude_md(temp_project_dir, project_context=sample_project_context)
        assert result.created is True
        assert "# MyTestApp" in result.content

        # Cleanup for next test
        (temp_project_dir / CLAUDE_MD_FILE).unlink()

        # From auto-detection
        (temp_project_dir / "requirements.txt").write_text("fastapi\n")
        result2 = generate_claude_md(temp_project_dir)
        assert result2.created is True
        assert "FastAPI" in result2.content

    def test_step3_includes_required_content(self, temp_project_dir):
        """
        Step 3: Include: project name, tech stack summary, key directories

        Verification:
        - Project name appears as heading
        - Tech stack listed in Tech Stack section
        - Directories listed in Project Structure section
        """
        metadata = ProjectMetadata(
            name="FeatureTest",
            tech_stack=["Python", "React", "PostgreSQL"],
            key_directories=[
                ("api", "API endpoints"),
                ("ui", "Frontend app"),
                ("migrations", "Database migrations"),
            ],
        )

        result = generate_claude_md(temp_project_dir, metadata=metadata)

        content = result.content

        # Project name
        assert "# FeatureTest" in content

        # Tech stack
        assert "## Tech Stack" in content
        assert "- Python" in content
        assert "- React" in content
        assert "- PostgreSQL" in content

        # Directories
        assert "## Project Structure" in content
        assert "`api/` - API endpoints" in content
        assert "`ui/` - Frontend app" in content
        assert "`migrations/` - Database migrations" in content

    def test_step4_provides_context_for_agents(self, temp_project_dir):
        """
        Step 4: CLAUDE.md provides context for Claude CLI agents

        Verification:
        - File is written to project root
        - File is named CLAUDE.md
        - Content mentions Claude Code agents
        - Content is valid markdown
        """
        result = generate_claude_md(temp_project_dir)

        assert result.created is True
        assert result.path == temp_project_dir / CLAUDE_MD_FILE
        assert (temp_project_dir / CLAUDE_MD_FILE).exists()

        content = (temp_project_dir / CLAUDE_MD_FILE).read_text()
        assert "Claude Code agents" in content
        assert content.startswith("# ")  # Valid markdown heading

    def test_step5_never_overwrite_existing(self, temp_project_dir):
        """
        Step 5: Existing CLAUDE.md is never overwritten

        Verification:
        - Existing CLAUDE.md is preserved by default
        - result.skipped is True when file exists
        - Multiple calls don't modify existing content
        - Only overwrite=True allows replacement
        """
        original_content = "# My Precious Project\n\nDo not touch!\n"
        (temp_project_dir / CLAUDE_MD_FILE).write_text(original_content)

        # Default behavior: skip
        result = generate_claude_md(temp_project_dir)
        assert result.existed is True
        assert result.skipped is True
        assert result.created is False
        assert (temp_project_dir / CLAUDE_MD_FILE).read_text() == original_content

        # Multiple calls still preserve
        for _ in range(3):
            r = generate_claude_md(temp_project_dir)
            assert r.skipped is True

        assert (temp_project_dir / CLAUDE_MD_FILE).read_text() == original_content

        # Only overwrite=True replaces
        new_result = generate_claude_md(temp_project_dir, overwrite=True)
        assert new_result.created is True
        assert (temp_project_dir / CLAUDE_MD_FILE).read_text() != original_content
