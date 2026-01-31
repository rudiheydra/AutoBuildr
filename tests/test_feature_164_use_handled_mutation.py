"""
Tests for Feature #164: Create useHandledMutation helper for consistent error handling.

This feature creates a useHandledMutation wrapper around React Query's useMutation
that enforces onError consistency by automatically providing toast/error notification
on failure, reducing boilerplate and preventing developers from forgetting error handlers.

These tests verify:
1. The useHandledMutation hook file exists and wraps useMutation
2. Default onError handler shows toast notification with error message
3. Callers can override or extend the default onError behavior
4. Existing mutations are refactored to use useHandledMutation
5. Error handling consistency is enforced across all mutation hooks
"""

import os
import re
import pytest

# ============================================================================
# Constants
# ============================================================================

UI_SRC = os.path.join(os.path.dirname(__file__), '..', 'ui', 'src')
HOOKS_DIR = os.path.join(UI_SRC, 'hooks')
COMPONENTS_DIR = os.path.join(UI_SRC, 'components')

HOOK_FILE = os.path.join(HOOKS_DIR, 'useHandledMutation.ts')
PROJECTS_FILE = os.path.join(HOOKS_DIR, 'useProjects.ts')
SCHEDULES_FILE = os.path.join(HOOKS_DIR, 'useSchedules.ts')
CONVERSATIONS_FILE = os.path.join(HOOKS_DIR, 'useConversations.ts')
DEVSERVER_FILE = os.path.join(COMPONENTS_DIR, 'DevServerControl.tsx')


def _read(path: str) -> str:
    with open(path, 'r') as f:
        return f.read()


# ============================================================================
# Step 1: useHandledMutation hook exists and wraps useMutation
# ============================================================================

class TestStep1HookCreation:
    """Create a useHandledMutation hook that wraps React Query's useMutation."""

    def test_hook_file_exists(self):
        """The useHandledMutation.ts file exists in hooks directory."""
        assert os.path.isfile(HOOK_FILE), f"Hook file not found at {HOOK_FILE}"

    def test_exports_use_handled_mutation_function(self):
        """The file exports a useHandledMutation function."""
        content = _read(HOOK_FILE)
        assert 'export function useHandledMutation' in content

    def test_wraps_use_mutation(self):
        """The hook internally calls useMutation from @tanstack/react-query."""
        content = _read(HOOK_FILE)
        assert "import { useMutation" in content or "import {useMutation" in content
        assert "from '@tanstack/react-query'" in content
        assert 'return useMutation' in content

    def test_returns_use_mutation_result(self):
        """The hook returns UseMutationResult for full compatibility."""
        content = _read(HOOK_FILE)
        assert 'UseMutationResult' in content

    def test_generic_type_parameters(self):
        """The hook supports generic type parameters (TData, TError, TVariables, TContext)."""
        content = _read(HOOK_FILE)
        assert 'TData' in content
        assert 'TError' in content
        assert 'TVariables' in content
        assert 'TContext' in content

    def test_accepts_standard_mutation_options(self):
        """The hook accepts standard UseMutationOptions."""
        content = _read(HOOK_FILE)
        assert 'UseMutationOptions' in content


# ============================================================================
# Step 2: Default onError handler with toast notification
# ============================================================================

class TestStep2DefaultErrorHandler:
    """Automatically inject a default onError handler that shows a toast notification."""

    def test_imports_toast(self):
        """The hook imports toast from useToast."""
        content = _read(HOOK_FILE)
        assert "import { toast }" in content
        assert "useToast" in content

    def test_default_error_title(self):
        """Default error title is 'Operation failed' when not specified."""
        content = _read(HOOK_FILE)
        assert "'Operation failed'" in content

    def test_calls_toast_error_in_default_handler(self):
        """Default onError handler calls toast.error with title and message."""
        content = _read(HOOK_FILE)
        assert 'toast.error(errorTitle, message)' in content

    def test_extracts_error_message(self):
        """Default handler extracts message from Error instances."""
        content = _read(HOOK_FILE)
        assert 'error instanceof Error' in content
        assert 'error.message' in content

    def test_handles_non_error_objects(self):
        """Default handler uses String(error) for non-Error objects."""
        content = _read(HOOK_FILE)
        assert 'String(error)' in content

    def test_error_title_option(self):
        """The hook accepts an errorTitle option for customizing the toast title."""
        content = _read(HOOK_FILE)
        assert 'errorTitle' in content
        # Verify it's in the type definition
        assert 'errorTitle?: string' in content


# ============================================================================
# Step 3: Callers can override or extend onError
# ============================================================================

class TestStep3OverrideOnError:
    """Allow callers to override or extend the default onError behavior."""

    def test_respects_caller_on_error(self):
        """When caller provides onError, the default toast handler is NOT injected."""
        content = _read(HOOK_FILE)
        # Look for the conditional logic that checks for caller-provided onError
        assert 'onError' in content
        # The hook should destructure onError from options
        assert re.search(r'const\s*\{.*onError.*\}\s*=\s*options', content, re.DOTALL)

    def test_conditional_handler_logic(self):
        """The hook uses conditional logic to pick between caller and default handler."""
        content = _read(HOOK_FILE)
        # Should have a ternary or if/else that checks if onError is provided
        assert 'onError\n    ?' in content or 'onError ?' in content or 'if (onError)' in content or 'onError\n      ?' in content or re.search(r'onError\s*\?', content)

    def test_effective_on_error_passed_to_mutation(self):
        """The effective (default or override) onError is passed to useMutation."""
        content = _read(HOOK_FILE)
        assert 'onError: effectiveOnError' in content or 'onError: onError' in content

    def test_update_settings_uses_custom_on_error(self):
        """useUpdateSettings provides a custom onError for optimistic rollback."""
        content = _read(PROJECTS_FILE)
        # useUpdateSettings should use useHandledMutation with a custom onError
        assert 'useHandledMutation' in content
        # It should have a custom onError that does rollback
        settings_section = content[content.index('useUpdateSettings'):]
        assert 'onError' in settings_section
        assert 'context?.previous' in settings_section


# ============================================================================
# Step 4: Existing mutations refactored to useHandledMutation
# ============================================================================

class TestStep4RefactorExistingMutations:
    """Refactor existing mutations to use useHandledMutation where appropriate."""

    def test_projects_file_uses_handled_mutation(self):
        """useProjects.ts imports and uses useHandledMutation."""
        content = _read(PROJECTS_FILE)
        assert "import { useHandledMutation }" in content
        assert 'useHandledMutation({' in content

    def test_projects_no_direct_use_mutation(self):
        """useProjects.ts does NOT directly import useMutation anymore."""
        content = _read(PROJECTS_FILE)
        # Should not import useMutation from react-query directly
        import_line = [l for l in content.split('\n') if '@tanstack/react-query' in l][0]
        assert 'useMutation' not in import_line

    def test_schedules_file_uses_handled_mutation(self):
        """useSchedules.ts imports and uses useHandledMutation."""
        content = _read(SCHEDULES_FILE)
        assert "import { useHandledMutation }" in content
        assert 'useHandledMutation({' in content

    def test_schedules_no_direct_use_mutation(self):
        """useSchedules.ts does NOT directly import useMutation."""
        content = _read(SCHEDULES_FILE)
        import_line = [l for l in content.split('\n') if '@tanstack/react-query' in l][0]
        assert 'useMutation' not in import_line

    def test_conversations_file_uses_handled_mutation(self):
        """useConversations.ts imports and uses useHandledMutation."""
        content = _read(CONVERSATIONS_FILE)
        assert "import { useHandledMutation }" in content
        assert 'useHandledMutation({' in content

    def test_conversations_no_direct_use_mutation(self):
        """useConversations.ts does NOT directly import useMutation."""
        content = _read(CONVERSATIONS_FILE)
        import_line = [l for l in content.split('\n') if '@tanstack/react-query' in l][0]
        assert 'useMutation' not in import_line

    def test_devserver_file_uses_handled_mutation(self):
        """DevServerControl.tsx imports and uses useHandledMutation."""
        content = _read(DEVSERVER_FILE)
        assert "import { useHandledMutation }" in content
        assert 'useHandledMutation({' in content

    def test_devserver_no_direct_use_mutation(self):
        """DevServerControl.tsx does NOT directly import useMutation."""
        content = _read(DEVSERVER_FILE)
        import_line = [l for l in content.split('\n') if '@tanstack/react-query' in l][0]
        assert 'useMutation' not in import_line

    def test_all_mutations_have_error_title(self):
        """Every useHandledMutation call across the codebase specifies errorTitle."""
        for path in [PROJECTS_FILE, SCHEDULES_FILE, CONVERSATIONS_FILE, DEVSERVER_FILE]:
            content = _read(path)
            # Count useHandledMutation calls
            mutation_calls = content.count('useHandledMutation({')
            # Count errorTitle or custom onError appearances within mutations
            error_title_count = content.count('errorTitle:')
            on_error_count = content.count('onError:')
            assert error_title_count + on_error_count >= mutation_calls, (
                f"File {os.path.basename(path)}: {mutation_calls} mutations but only "
                f"{error_title_count} errorTitle + {on_error_count} onError"
            )

    def test_no_direct_use_mutation_in_ui_src(self):
        """useMutation is ONLY imported in useHandledMutation.ts, nowhere else."""
        for root, _dirs, files in os.walk(UI_SRC):
            for fname in files:
                if not fname.endswith(('.ts', '.tsx')):
                    continue
                fpath = os.path.join(root, fname)
                if os.path.basename(fpath) == 'useHandledMutation.ts':
                    continue
                content = _read(fpath)
                for line in content.split('\n'):
                    if '@tanstack/react-query' in line and 'useMutation' in line:
                        pytest.fail(
                            f"Direct useMutation import found in {os.path.relpath(fpath, UI_SRC)}: {line.strip()}"
                        )


# ============================================================================
# Step 5: Mutations surface errors correctly on backend failures
# ============================================================================

def _extract_function_body(content: str, func_name: str) -> str:
    """Extract the full body of a function from its name to the next export/function or EOF.

    This avoids the pitfall of cutting off at the first '})' which might be
    inside an onSuccess callback rather than the end of the mutation call.
    """
    start = content.index(func_name)
    # Find the next 'export function' or 'function ' declaration after the start
    rest = content[start + len(func_name):]
    # Look for the next top-level function declaration
    next_func = re.search(r'\n(?:export )?function ', rest)
    if next_func:
        return content[start:start + len(func_name) + next_func.start()]
    # Or look for the next section separator
    next_sep = rest.find('\n// ====')
    if next_sep >= 0:
        return content[start:start + len(func_name) + next_sep]
    return content[start:]


class TestStep5ErrorSurfacing:
    """Verify that mutations using the helper surface errors correctly on backend failures."""

    def test_create_project_error_title(self):
        """useCreateProject uses errorTitle 'Failed to create project'."""
        section = _extract_function_body(_read(PROJECTS_FILE), 'useCreateProject')
        assert "errorTitle: 'Failed to create project'" in section

    def test_delete_project_error_title(self):
        """useDeleteProject uses errorTitle 'Failed to delete project'."""
        section = _extract_function_body(_read(PROJECTS_FILE), 'useDeleteProject')
        assert "errorTitle: 'Failed to delete project'" in section

    def test_create_feature_error_title(self):
        """useCreateFeature uses errorTitle 'Failed to create feature'."""
        section = _extract_function_body(_read(PROJECTS_FILE), 'useCreateFeature')
        assert "errorTitle: 'Failed to create feature'" in section

    def test_start_agent_error_title(self):
        """useStartAgent uses errorTitle 'Failed to start agent'."""
        section = _extract_function_body(_read(PROJECTS_FILE), 'useStartAgent')
        assert "errorTitle: 'Failed to start agent'" in section

    def test_create_schedule_error_title(self):
        """useCreateSchedule uses errorTitle 'Failed to create schedule'."""
        section = _extract_function_body(_read(SCHEDULES_FILE), 'useCreateSchedule')
        assert "errorTitle: 'Failed to create schedule'" in section

    def test_delete_conversation_error_title(self):
        """useDeleteConversation uses errorTitle 'Failed to delete conversation'."""
        section = _extract_function_body(_read(CONVERSATIONS_FILE), 'useDeleteConversation')
        assert "errorTitle: 'Failed to delete conversation'" in section

    def test_devserver_start_error_title(self):
        """useStartDevServer uses errorTitle 'Failed to start dev server'."""
        section = _extract_function_body(_read(DEVSERVER_FILE), 'useStartDevServer')
        assert "errorTitle: 'Failed to start dev server'" in section

    def test_devserver_stop_error_title(self):
        """useStopDevServer uses errorTitle 'Failed to stop dev server'."""
        section = _extract_function_body(_read(DEVSERVER_FILE), 'useStopDevServer')
        assert "errorTitle: 'Failed to stop dev server'" in section

    def test_hook_preserves_other_callbacks(self):
        """useHandledMutation spreads all other options (onSuccess, onSettled, etc.)."""
        content = _read(HOOK_FILE)
        # The hook should spread the rest of the options
        assert '...rest' in content
        # onSuccess and onSettled should still work in consuming files
        projects_content = _read(PROJECTS_FILE)
        assert 'onSuccess:' in projects_content
        assert 'onSettled:' in projects_content
