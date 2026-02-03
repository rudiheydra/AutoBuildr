"""
API Package
============

Database models and utilities for feature management.
"""

from api.database import Feature, create_database, get_database_path
from api.dependency_resolver import (
    DependencyIssue,
    DependencyResult,
    ValidationResult,
    validate_dependency_graph,
    validate_dependencies,
    resolve_dependencies,
    would_create_circular_dependency,
    are_dependencies_satisfied,
    get_blocking_dependencies,
    get_ready_features,
    get_blocked_features,
    build_graph_data,
    compute_scheduling_scores,
)
from api.prompt_builder import (
    build_system_prompt,
    extract_tool_hints,
    format_tool_hints_as_markdown,
    inject_tool_hints_into_prompt,
)
from api.harness_kernel import (
    BudgetExceeded,
    BudgetTracker,
    ExecutionResult,
    HarnessKernel,
    MaxTurnsExceeded,
    TimeoutSecondsExceeded,
    # Feature #77: Database Transaction Safety
    TransactionError,
    ConcurrentModificationError,
    DatabaseLockError,
    commit_with_retry,
    rollback_and_record_error,
    get_run_with_lock,
    safe_add_and_commit_event,
)
from api.static_spec_adapter import (
    StaticSpecAdapter,
    get_static_spec_adapter,
    reset_static_spec_adapter,
    INITIALIZER_TOOLS,
    CODING_TOOLS,
    TESTING_TOOLS,
    DEFAULT_BUDGETS,
)
from api.tool_policy import (
    CompiledPattern,
    PatternCompilationError,
    ToolCallBlocked,
    ToolPolicyEnforcer,
    ToolPolicyError,
    check_arguments_against_patterns,
    compile_forbidden_patterns,
    create_enforcer_for_run,
    extract_forbidden_patterns,
    record_blocked_tool_call_event,
    serialize_tool_arguments,
    # Feature #57: Tool Policy Derivation from Task Type
    derive_tool_policy,
    get_tool_set,
    get_standard_forbidden_patterns,
    get_task_forbidden_patterns,
    get_combined_forbidden_patterns,
    get_tool_hints,
    get_supported_task_types,
    TOOL_SETS,
    STANDARD_FORBIDDEN_PATTERNS,
    TASK_SPECIFIC_FORBIDDEN_PATTERNS,
    TASK_TOOL_HINTS,
    # Feature #58: Budget Derivation from Task Complexity
    BASE_BUDGETS,
    MIN_BUDGET,
    MAX_BUDGET,
    DESCRIPTION_LENGTH_THRESHOLDS,
    STEPS_COUNT_THRESHOLDS,
    BudgetResult,
    derive_budget,
    derive_budget_detailed,
    get_base_budget,
    get_budget_bounds,
    get_all_base_budgets,
    # Feature #40: ToolPolicy Allowed Tools Filtering
    ToolDefinition,
    ToolFilterResult,
    extract_allowed_tools,
    filter_tools,
    filter_tools_for_spec,
    get_filtered_tool_names,
    validate_tool_names,
    # Feature #44: Policy Violation Event Logging
    PolicyViolation,
    ViolationAggregation,
    VIOLATION_TYPES,
    create_allowed_tools_violation,
    create_directory_sandbox_violation,
    create_forbidden_patterns_violation,
    get_violation_aggregation,
    record_allowed_tools_violation,
    record_and_aggregate_violation,
    record_directory_sandbox_violation,
    record_forbidden_patterns_violation,
    record_policy_violation_event,
    update_run_violation_metadata,
    # Feature #47: Forbidden Tools Explicit Blocking
    ForbiddenToolBlocked,
    extract_forbidden_tools,
    create_forbidden_tools_violation,
    record_forbidden_tools_violation,
    # Feature #46: Symlink Target Validation
    BrokenSymlinkError,
    DirectoryAccessBlocked,
    is_broken_symlink,
    get_symlink_target,
    resolve_target_path,
    validate_directory_access,
    # Feature #48: Path Traversal Attack Detection
    PathTraversalResult,
    contains_null_byte,
    contains_path_traversal,
    detect_path_traversal_attack,
    normalize_path_for_comparison,
    path_differs_after_normalization,
)
from api.display_derivation import (
    derive_display_name,
    derive_display_properties,
    derive_icon,
    derive_mascot_name,
    extract_first_sentence,
    get_mascot_pool,
    get_task_type_icons,
    truncate_with_ellipsis,
    DISPLAY_NAME_MAX_LENGTH,
    MASCOT_POOL,
    TASK_TYPE_ICONS,
    DEFAULT_ICON,
)
# Feature #186: Octo selects appropriate tools for each agent
from api.tool_selection import (
    AVAILABLE_TOOLS,
    ROLE_TOOL_CATEGORIES,
    ROLE_TOOL_OVERRIDES,
    ToolSelectionResult,
    get_all_tool_categories,
    get_browser_tools,
    get_test_runner_tools,
    get_tool_info,
    get_tools_by_category,
    get_tools_by_privilege,
    get_ui_agent_tools,
    is_browser_tool,
    select_tools_for_capability,
    select_tools_for_role,
)
from api.validators import (
    AcceptanceGate,
    FileExistsValidator,
    GateResult,
    LintCleanValidator,
    TestEnforcementValidator,  # Feature #211
    Validator,
    ValidatorResult,
    VALIDATOR_REGISTRY,
    evaluate_acceptance_spec,
    evaluate_validator,
    get_validator,
    normalize_acceptance_results_to_record,
)
from api.feature_compiler import (
    CATEGORY_TO_TASK_TYPE,
    FeatureCompiler,
    compile_feature,
    extract_task_type_from_category,
    get_budget_for_task_type,
    get_feature_compiler,
    get_tools_for_task_type,
    reset_feature_compiler,
    slugify,
)
from api.websocket_events import (
    AcceptanceUpdatePayload,
    RunStartedPayload,
    ValidatorResultPayload,
    broadcast_acceptance_update,
    broadcast_acceptance_update_sync,
    broadcast_run_started,
    broadcast_run_started_sync,
    build_acceptance_update_from_results,
    create_validator_result_payload,
)
from api.event_recorder import (
    EventRecorder,
    get_event_recorder,
    clear_recorder_cache,
)
from api.event_replay import (
    # Feature #227: Audit events support replay and debugging
    ReplayableEvent,
    DebugContext,
    EventTimeline,
    EventReplayContext,
    get_replay_context,
    reconstruct_run_events,
    get_run_debug_context,
    verify_event_sequence_integrity,
)
from api.dspy_signatures import (
    SpecGenerationSignature,
    get_spec_generator,
    validate_spec_output,
    VALID_TASK_TYPES,
    DEFAULT_BUDGETS as DSPY_DEFAULT_BUDGETS,
    # Feature #182: Octo DSPy signature for AgentSpec generation
    OctoSpecGenerationSignature,
    get_octo_spec_generator,
    validate_octo_spec_output,
    convert_octo_output_to_agent_spec_dict,
    VALID_AGENT_MODELS,
    VALID_GATE_MODES,
    VALID_OCTO_VALIDATOR_TYPES,
)
from api.spec_name_generator import (
    # Feature #59: Unique Spec Name Generation
    SPEC_NAME_MAX_LENGTH,
    SPEC_NAME_PATTERN,
    STOP_WORDS,
    check_name_exists,
    extract_keywords,
    generate_sequence_suffix,
    generate_slug,
    generate_spec_name,
    generate_spec_name_for_feature,
    generate_timestamp_suffix,
    generate_unique_spec_name,
    get_existing_names_with_prefix,
    normalize_slug,
    validate_spec_name,
)
from api.orphaned_run_cleanup import (
    # Feature #79: Orphaned Run Cleanup on Startup
    ORPHANED_ERROR_MESSAGE,
    DEFAULT_ORPHAN_TIMEOUT_SECONDS,
    OrphanedRunInfo,
    CleanupResult,
    get_orphaned_runs,
    is_run_stale,
    cleanup_single_run,
    cleanup_orphaned_runs,
    get_orphan_statistics,
)
from api.spec_validator import (
    # Feature #78: Invalid AgentSpec Graceful Handling
    REQUIRED_FIELDS as SPEC_REQUIRED_FIELDS,
    VALID_TASK_TYPES as SPEC_VALID_TASK_TYPES,
    MIN_MAX_TURNS,
    MAX_MAX_TURNS,
    MIN_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    NAME_PATTERN as SPEC_NAME_PATTERN_RE,
    TOOL_POLICY_REQUIRED_FIELDS,
    ValidationError as SpecValidationError,
    SpecValidationResult,
    SpecValidationError as SpecValidationException,
    validate_spec,
    validate_spec_or_raise,
    validate_spec_dict,
)
from api.migration_flag import (
    # Feature #39: AUTOBUILDR_USE_KERNEL Migration Flag
    ENV_VAR_NAME as MIGRATION_ENV_VAR_NAME,
    DEFAULT_USE_KERNEL,
    TRUTHY_VALUES as MIGRATION_TRUTHY_VALUES,
    FALSY_VALUES as MIGRATION_FALSY_VALUES,
    ExecutionPath,
    FeatureExecutionResult,
    get_use_kernel_env_value,
    parse_use_kernel_value,
    is_kernel_enabled,
    set_kernel_enabled,
    clear_kernel_flag,
    execute_feature_legacy,
    execute_feature_kernel,
    execute_feature,
    get_execution_path_string,
    get_migration_status,
)
from api.tool_provider import (
    # Feature #45: ToolProvider Interface Definition
    # Exceptions
    ToolProviderError,
    ToolNotFoundError,
    ProviderNotFoundError,
    ProviderAlreadyRegisteredError,
    AuthenticationError,
    ToolExecutionError,
    # Enums
    ToolCategory,
    AuthMethod,
    ProviderStatus,
    # Data classes
    ToolDefinition as ProviderToolDefinition,  # Alias to avoid conflict with tool_policy.ToolDefinition
    ToolResult,
    ProviderCapabilities,
    AuthCredentials,
    AuthResult,
    # Abstract base class
    ToolProvider,
    # Implementations
    LocalToolProvider,
    ToolProviderRegistry,
    # Module-level functions
    get_tool_registry,
    reset_tool_registry,
    register_provider,
    execute_tool as execute_provider_tool,  # Alias to avoid conflict with execute_tool from migration_flag
)
from api.spec_builder import (
    # Feature #54: DSPy Module Execution for Spec Generation
    # Exceptions
    SpecBuilderError,
    DSPyInitializationError,
    DSPyExecutionError,
    OutputValidationError,
    ToolPolicyValidationError,
    ValidatorsValidationError,
    # Data classes
    BuildResult,
    ParsedOutput,
    # Validation functions
    validate_tool_policy,
    validate_validators,
    parse_json_field,
    coerce_integer,
    # Main class
    SpecBuilder,
    # Module-level functions
    get_spec_builder,
    reset_spec_builder,
    # Constants
    DEFAULT_MODEL,
    AVAILABLE_MODELS,
    MIN_MAX_TURNS,
    MAX_MAX_TURNS,
    MIN_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    TOOL_POLICY_REQUIRED_FIELDS as SPEC_BUILDER_TOOL_POLICY_REQUIRED_FIELDS,
)
from api.task_type_detector import (
    # Feature #56: Task Type Detection from Description
    # Constants
    CODING_KEYWORDS,
    TESTING_KEYWORDS,
    REFACTORING_KEYWORDS,
    DOCUMENTATION_KEYWORDS,
    AUDIT_KEYWORDS,
    TASK_TYPE_KEYWORDS,
    VALID_TASK_TYPES as DETECTOR_VALID_TASK_TYPES,
    MIN_SCORE_THRESHOLD,
    TIE_BREAKER_PRIORITY,
    # Data classes
    TaskTypeDetectionResult,
    # Core functions
    detect_task_type,
    detect_task_type_detailed,
    normalize_description,
    score_task_type,
    calculate_confidence,
    # Utility functions
    get_keywords_for_type,
    get_all_keyword_sets,
    get_valid_task_types as detector_get_valid_task_types,
    is_valid_task_type,
    explain_detection,
)
from api.maestro import (
    # Feature #174: Maestro detects when new agents are needed
    # Constants
    DEFAULT_AGENTS,
    SPECIALIZED_CAPABILITY_KEYWORDS,
    # Data classes
    ProjectContext,
    CapabilityRequirement,
    AgentPlanningDecision,
    # Feature #176: Octo Delegation Result
    OctoDelegationResult,
    # Feature #179: Decision Persistence
    PersistDecisionResult,
    # Feature #180: Octo Delegation With Fallback
    OctoDelegationWithFallbackResult,
    # Main class
    Maestro,
    # Module-level functions
    get_maestro,
    reset_maestro,
    evaluate_project,
    detect_agent_planning_required,
)
from api.agentspec_models import (
    # Feature #179: Agent Planning Decision Record (persisted to DB)
    AgentPlanningDecisionRecord,
)
from api.octo import (
    # Feature #187: Octo Model Selection
    VALID_MODELS as OCTO_VALID_MODELS,
    DEFAULT_MODEL as OCTO_DEFAULT_MODEL,
    HAIKU_CAPABILITIES,
    OPUS_CAPABILITIES,
    TASK_TYPE_MODEL_DEFAULTS,
    COMPLEXITY_INDICATORS,
    select_model_for_capability,
    validate_model,
    get_model_characteristics,
    # Feature #189: Octo persists AgentSpecs to database
    SOURCE_TYPE_OCTO_GENERATED,
    SOURCE_TYPE_MANUAL,
    SOURCE_TYPE_DSPy,
    SOURCE_TYPE_TEMPLATE,
    SOURCE_TYPE_IMPORTED,
    VALID_SOURCE_TYPES,
    SpecPersistenceResult,
    # Feature #190: Octo handles malformed project context gracefully
    PayloadValidationError,
    PayloadValidationResult,
)
from api.constraints import (
    # Feature #185: Constraint Satisfaction for AgentSpec Generation
    ConstraintDefinition,
    ConstraintValidator,
    ConstraintValidationResult,
    ConstraintViolation,
    ToolAvailabilityConstraint,
    ModelLimitConstraint,
    SandboxConstraint,
    ForbiddenPatternConstraint,
    create_constraints_from_payload,
    create_default_constraints,
    # Constants
    DEFAULT_MAX_TURNS_LIMIT,
    DEFAULT_TIMEOUT_LIMIT,
    MODEL_LIMITS as CONSTRAINT_MODEL_LIMITS,
    STANDARD_TOOLS as CONSTRAINT_STANDARD_TOOLS,
)
from api.octo_schemas import (
    # Feature #188: Octo outputs are strictly typed and schema-validated
    # Exceptions
    OctoSchemaValidationError,
    SchemaValidationError as OctoSchemaValidationErrorDetail,
    SchemaValidationResult as OctoSchemaValidationResult,
    # Validation functions
    validate_agent_spec_schema,
    validate_test_contract_schema,
    validate_octo_outputs,
    validate_agent_spec_schema_or_raise,
    validate_test_contract_schema_or_raise,
    get_schema,
    # Schemas
    AGENT_SPEC_SCHEMA,
    TEST_CONTRACT_SCHEMA,
    TEST_CONTRACT_ASSERTION_SCHEMA,
    TEST_DEPENDENCY_SCHEMA,  # Feature #209
    # Constants
    VALID_TASK_TYPES as OCTO_SCHEMA_VALID_TASK_TYPES,
    VALID_TEST_TYPES as OCTO_SCHEMA_VALID_TEST_TYPES,
    VALID_GATE_MODES as OCTO_SCHEMA_VALID_GATE_MODES,
    VALID_ASSERTION_OPERATORS,
    VALID_DEPENDENCY_TYPES,  # Feature #209
)
from api.archetypes import (
    # Feature #191: Octo uses agent archetypes for common patterns
    # Data classes
    AgentArchetype,
    ArchetypeMatchResult,
    CustomizedArchetype,
    # Constants
    AGENT_ARCHETYPES,
    HIGH_CONFIDENCE_THRESHOLD,
    MEDIUM_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
    # Core functions
    get_archetype,
    get_all_archetypes,
    get_archetype_names,
    archetype_exists,
    map_capability_to_archetype,
    is_custom_agent_needed,
    customize_archetype,
    create_agent_from_archetype,
    # Utility functions
    get_archetype_for_task_type,
    get_archetype_summary,
)
from api.agent_materializer import (
    # Feature #192: Agent Materializer converts AgentSpec to Claude Code markdown
    # Feature #195: Agent Materializer records agent_materialized audit event
    # Feature #196: Agent Materializer validates template output
    # Feature #197: Agent Materializer handles multiple agents in batch
    # Feature #218: Icon generation triggered during agent materialization
    # Data classes
    MaterializationResult as AgentMaterializationResult,
    BatchMaterializationResult,
    MaterializationAuditInfo,
    IconGenerationInfo,
    ValidationError as MaterializerValidationError,
    TemplateValidationResult,
    # Type aliases
    ProgressCallback as MaterializerProgressCallback,
    # Exception
    TemplateValidationError,
    # Main class
    AgentMaterializer,
    # Convenience functions
    render_agentspec_to_markdown,
    verify_determinism as verify_materializer_determinism,
    # Constants
    DEFAULT_OUTPUT_DIR as MATERIALIZER_DEFAULT_OUTPUT_DIR,
    DEFAULT_MODEL as MATERIALIZER_DEFAULT_MODEL,
    DEFAULT_COLOR as MATERIALIZER_DEFAULT_COLOR,
    TASK_TYPE_COLORS,
    VALID_MODELS as MATERIALIZER_VALID_MODELS,
    DESCRIPTION_MAX_LENGTH,
    REQUIRED_MARKDOWN_SECTIONS,
    REQUIRED_FRONTMATTER_FIELDS,
)
from api.scaffolding import (
    # Feature #199: .claude directory scaffolding creates standard structure
    # Data classes
    DirectoryStatus,
    ScaffoldResult,
    ScaffoldPreview,
    # Main class
    ClaudeDirectoryScaffold,
    # Convenience functions
    scaffold_claude_directory,
    preview_claude_directory,
    ensure_claude_root,
    ensure_agents_generated,
    verify_claude_structure,
    is_claude_scaffolded,
    get_standard_subdirs,
    # Constants
    CLAUDE_ROOT_DIR,
    STANDARD_SUBDIRS,
    DEFAULT_DIR_PERMISSIONS,
    PHASE_1_DIRS,
    PHASE_2_DIRS,
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
    # Feature #202: Project Initialization with Scaffolding
    # Data classes
    ScaffoldingStatus,
    ProjectInitializationResult,
    # Functions
    get_scaffolding_status,
    needs_scaffolding,
    initialize_project_scaffolding,
    ensure_project_scaffolded,
    is_project_initialized,
    # Constants
    SCAFFOLDING_METADATA_KEY,
    SCAFFOLDING_TIMESTAMP_KEY,
    SCAFFOLDING_COMPLETED_KEY,
    PROJECT_METADATA_FILE,
    # Feature #204: Scaffolding respects .gitignore patterns
    # Data classes
    GitignoreUpdateResult,
    # Functions
    gitignore_exists,
    update_gitignore,
    ensure_gitignore_patterns,
    verify_gitignore_patterns,
    scaffold_with_gitignore,
    # Constants
    GITIGNORE_FILE,
    GITIGNORE_GENERATED_PATTERNS,
    GITIGNORE_TRACKED_PATTERNS,
)
from api.settings_manager import (
    # Feature #198: Agent Materializer generates settings.local.json when needed
    # Data classes
    SettingsUpdateResult,
    SettingsRequirements,
    # Main class
    SettingsManager,
    # Convenience functions
    check_settings_exist,
    ensure_settings_for_agents,
    detect_required_mcp_servers,
    get_settings_manager,
    # Constants
    SETTINGS_LOCAL_FILE,
    CLAUDE_DIR as SETTINGS_CLAUDE_DIR,
    DEFAULT_SETTINGS_PERMISSIONS,
    DEFAULT_SETTINGS,
    MCP_SERVER_CONFIGS,
    MCP_TOOL_PATTERNS,
)
from api.test_code_writer import (
    # Feature #206: Test-runner agent writes test code from TestContract
    # Data classes
    TestCodeWriteResult,
    TestCodeWriterAuditInfo,
    FrameworkDetectionResult,
    # Main class
    TestCodeWriter,
    # Convenience functions
    get_test_code_writer,
    reset_test_code_writer_cache,
    write_tests_from_contract,
    detect_test_framework,
    # Constants
    TEST_FRAMEWORKS,
    DEFAULT_FRAMEWORKS,
    TEST_DIR_PATTERNS,
    TEST_FILE_EXTENSIONS,
)
from api.test_runner import (
    # Feature #207: Test-runner agent executes tests and reports results
    # Data classes
    TestFailure,
    TestExecutionResult,
    # Parsers
    PytestResultParser,
    UnittestResultParser,
    JestResultParser,
    # Main class
    TestRunner,
    # Convenience functions
    record_tests_executed,
    run_tests,
)
from api.test_contract_gate import (
    # Feature #210: Feature cannot pass without tests passing
    # Enums
    TestGateStatus,
    # Data classes
    TestGateConfiguration,
    AssertionCoverage,
    TestContractCoverage,
    TestGateResult,
    # Main class
    TestContractGate,
    # Convenience functions
    get_test_contract_gate,
    reset_test_contract_gate,
    evaluate_test_gate,
    check_tests_required,
    get_blocking_test_issues,
    # Constants
    DEFAULT_ENFORCE_TEST_GATE,
    DEFAULT_REQUIRE_ALL_ASSERTIONS,
    DEFAULT_MIN_TEST_COVERAGE,
    DEFAULT_ALLOW_SKIP_FOR_NO_CONTRACT,
)
from api.test_framework import (
    # Feature #208: Test-runner agent supports multiple test frameworks
    # Enum
    TestFramework,
    # Data classes
    TestFrameworkDetectionResult,
    TestCommand,
    TestResult,
    FrameworkPreference,
    # Detection functions
    detect_framework,
    # Command generation functions
    generate_test_command,
    get_available_options,
    # Result parsing functions
    parse_test_output,
    # Settings functions
    get_framework_preference,
    set_framework_preference,
    get_supported_frameworks,
    get_framework_info,
    # Constants
    FRAMEWORK_MARKERS,
    FRAMEWORK_LANGUAGES,
    DEFAULT_TEST_COMMANDS,
    TEST_COMMAND_OPTIONS,
    SETTINGS_FRAMEWORK_KEY,
    SETTINGS_TEST_SECTION,
)
from api.sandbox_test_runner import (
    # Feature #214: Test-runner agent can run in sandbox environment
    # Data classes
    SandboxConfiguration,
    DependencyInstallResult,
    SandboxExecutionResult,
    # Main class
    SandboxTestRunner,
    # Convenience functions
    run_tests_in_sandbox,
    is_sandbox_available,
    get_default_sandbox_config,
    record_sandbox_tests_executed,
    # Constants
    DEFAULT_SANDBOX_IMAGE,
    DEFAULT_PROJECT_MOUNT,
    DEFAULT_SANDBOX_TIMEOUT,
    DEFAULT_INSTALL_TIMEOUT,
    DEPENDENCY_FILES,
)
from api.test_result_artifact import (
    # Feature #212: Test results persisted as artifacts
    # Constants
    ARTIFACT_TYPE_TEST_RESULT,
    MAX_FAILURES_IN_METADATA,
    # Data classes
    TestResultArtifactMetadata,
    StoreTestResultResult,
    RetrievedTestResult,
    # Functions
    build_test_result_metadata,
    serialize_test_result,
    deserialize_test_result,
    store_test_result_artifact,
    get_store_result as get_test_result_store_result,
    retrieve_test_result_from_artifact,
    get_test_result_artifacts_for_run,
    get_latest_test_result_artifact,
    get_test_summary_from_artifact,
    record_test_result_artifact_created,
)
from api.playwright_mcp_config import (
    # Feature #213: Playwright MCP available for E2E test agents
    # Enums
    PlaywrightMode,
    PlaywrightToolSet,
    # Data classes
    PlaywrightMcpConfig,
    PlaywrightAgentConfigResult,
    McpConnectionResult,
    # Configuration functions
    get_playwright_config,
    is_playwright_enabled,
    enable_playwright,
    disable_playwright,
    # Tool selection functions
    get_playwright_tools,
    configure_playwright_for_agent,
    add_playwright_tools_to_spec,
    is_e2e_agent,
    # MCP connection functions
    get_mcp_server_config,
    verify_mcp_connection,
    ensure_playwright_in_settings,
    # Agent integration functions
    get_e2e_agent_tools,
    should_include_playwright_tools,
    # Cache functions
    get_cached_playwright_config,
    reset_playwright_config_cache,
    # Constants
    PLAYWRIGHT_TOOLS,
    CORE_PLAYWRIGHT_TOOLS,
    EXTENDED_PLAYWRIGHT_TOOLS,
    PLAYWRIGHT_TOOL_SETS,
    SUPPORTED_BROWSERS,
    DEFAULT_BROWSER,
    DEFAULT_TIMEOUT_MS,
    DEFAULT_VIEWPORT,
    DEFAULT_PLAYWRIGHT_MCP_CONFIG,
    HEADFUL_PLAYWRIGHT_MCP_CONFIG,
    SETTINGS_PLAYWRIGHT_SECTION,
)
from api.icon_provider import (
    # Feature #215: Icon provider interface defined
    # Exceptions
    IconProviderError,
    IconGenerationError,
    ProviderNotFoundError as IconProviderNotFoundError,
    ProviderAlreadyRegisteredError as IconProviderAlreadyRegisteredError,
    InvalidIconFormatError,
    # Enums
    IconFormat,
    IconTone,
    ProviderStatus as IconProviderStatus,
    # Data classes
    IconResult,
    IconProviderCapabilities,
    IconGenerationRequest,
    # Abstract base class
    IconProvider,
    # Default implementation
    DefaultIconProvider,
    # Registry
    IconProviderRegistry,
    # Convenience functions
    get_icon_registry,
    reset_icon_registry,
    register_icon_provider,
    generate_icon,
    get_default_icon_provider,
    configure_icon_provider_from_settings,
    # Configuration functions
    get_active_provider_from_config,
    set_active_provider_in_config,
    # Constants
    ICON_PROVIDER_CONFIG_KEY,
    DEFAULT_PROVIDER_NAME as DEFAULT_ICON_PROVIDER_NAME,
)
from api.local_placeholder_icon_provider import (
    # Feature #216: LocalPlaceholderIconProvider implements stub
    # Main class
    LocalPlaceholderIconProvider,
    # Data classes/Enums
    PlaceholderConfig,
    PlaceholderShape,
    # Convenience functions
    get_local_placeholder_provider,
    generate_placeholder_icon,
    get_placeholder_color,
    get_placeholder_initials,
    # Core functions
    compute_name_hash,
    compute_color_from_name,
    extract_initials,
    generate_placeholder_svg,
    generate_shape_svg,
    # Constants
    LOCAL_PLACEHOLDER_PROVIDER_NAME,
    DEFAULT_SVG_WIDTH,
    DEFAULT_SVG_HEIGHT,
    PLACEHOLDER_COLOR_PALETTE,
)
from api.icon_provider_config import (
    # Feature #217: Icon provider is configurable via settings
    # Constants
    ENV_VAR_ICON_PROVIDER,
    SETTINGS_ICON_PROVIDER_KEY,
    DEFAULT_ICON_PROVIDER,
    KNOWN_PROVIDERS,
    PROVIDER_ALIASES,
    # Enums
    ConfigSource as IconConfigSource,
    # Data classes
    IconProviderConfigResult,
    IconProviderSettings,
    # Core configuration functions
    normalize_provider_name,
    is_valid_provider_name,
    get_env_icon_provider,
    get_settings_icon_provider,
    resolve_icon_provider,
    get_icon_provider,
    set_icon_provider,
    clear_icon_provider_override,
    get_icon_provider_override,
    # Settings file functions
    load_icon_provider_settings,
    save_icon_provider_settings,
    # Configuration validation
    validate_icon_provider_config,
    get_available_providers,
    get_provider_info,
    # Module-level configuration
    configure_icon_provider,
    get_icon_provider_config_documentation,
)
from api.icon_storage import (
    # Feature #219: Generated icons stored and retrievable
    # Constants
    ICON_INLINE_MAX_SIZE,
    ICON_FORMAT_MIME_TYPES,
    DEFAULT_PLACEHOLDER_PROVIDER,
    # Data classes
    StoredIconResult,
    RetrievedIcon,
    # Database model
    AgentIcon,
    # Main class
    IconStorage,
    # Helper functions
    get_mime_type_for_format,
    store_icon_from_result,
    get_icon_storage,
)

__all__ = [
    "Feature",
    "create_database",
    "get_database_path",
    # Dependency resolver exports
    "DependencyIssue",
    "DependencyResult",
    "ValidationResult",
    "validate_dependency_graph",
    "validate_dependencies",
    "resolve_dependencies",
    "would_create_circular_dependency",
    "are_dependencies_satisfied",
    "get_blocking_dependencies",
    "get_ready_features",
    "get_blocked_features",
    "build_graph_data",
    "compute_scheduling_scores",
    # Prompt builder exports
    "build_system_prompt",
    "extract_tool_hints",
    "format_tool_hints_as_markdown",
    "inject_tool_hints_into_prompt",
    # Harness kernel exports
    "BudgetExceeded",
    "BudgetTracker",
    "ExecutionResult",
    "HarnessKernel",
    "MaxTurnsExceeded",
    "TimeoutSecondsExceeded",
    # Feature #77: Database Transaction Safety exports
    "TransactionError",
    "ConcurrentModificationError",
    "DatabaseLockError",
    "commit_with_retry",
    "rollback_and_record_error",
    "get_run_with_lock",
    "safe_add_and_commit_event",
    # Static spec adapter exports
    "StaticSpecAdapter",
    "get_static_spec_adapter",
    "reset_static_spec_adapter",
    "INITIALIZER_TOOLS",
    "CODING_TOOLS",
    "TESTING_TOOLS",
    "DEFAULT_BUDGETS",
    # Tool policy exports
    "CompiledPattern",
    "PatternCompilationError",
    "ToolCallBlocked",
    "ToolPolicyEnforcer",
    "ToolPolicyError",
    "check_arguments_against_patterns",
    "compile_forbidden_patterns",
    "create_enforcer_for_run",
    "extract_forbidden_patterns",
    "record_blocked_tool_call_event",
    "serialize_tool_arguments",
    # Feature #57: Tool Policy Derivation exports
    "derive_tool_policy",
    "get_tool_set",
    "get_standard_forbidden_patterns",
    "get_task_forbidden_patterns",
    "get_combined_forbidden_patterns",
    "get_tool_hints",
    "get_supported_task_types",
    "TOOL_SETS",
    "STANDARD_FORBIDDEN_PATTERNS",
    "TASK_SPECIFIC_FORBIDDEN_PATTERNS",
    "TASK_TOOL_HINTS",
    # Feature #58: Budget Derivation from Task Complexity exports
    "BASE_BUDGETS",
    "MIN_BUDGET",
    "MAX_BUDGET",
    "DESCRIPTION_LENGTH_THRESHOLDS",
    "STEPS_COUNT_THRESHOLDS",
    "BudgetResult",
    "derive_budget",
    "derive_budget_detailed",
    "get_base_budget",
    "get_budget_bounds",
    "get_all_base_budgets",
    # Feature #40: ToolPolicy Allowed Tools Filtering exports
    "ToolDefinition",
    "ToolFilterResult",
    "extract_allowed_tools",
    "filter_tools",
    "filter_tools_for_spec",
    "get_filtered_tool_names",
    "validate_tool_names",
    # Feature #44: Policy Violation Event Logging exports
    "PolicyViolation",
    "ViolationAggregation",
    "VIOLATION_TYPES",
    "create_allowed_tools_violation",
    "create_directory_sandbox_violation",
    "create_forbidden_patterns_violation",
    "get_violation_aggregation",
    "record_allowed_tools_violation",
    "record_and_aggregate_violation",
    "record_directory_sandbox_violation",
    "record_forbidden_patterns_violation",
    "record_policy_violation_event",
    "update_run_violation_metadata",
    # Feature #47: Forbidden Tools Explicit Blocking exports
    "ForbiddenToolBlocked",
    "extract_forbidden_tools",
    "create_forbidden_tools_violation",
    "record_forbidden_tools_violation",
    # Display derivation exports
    "derive_display_name",
    "derive_display_properties",
    "derive_icon",
    "derive_mascot_name",
    "extract_first_sentence",
    "get_mascot_pool",
    "get_task_type_icons",
    "truncate_with_ellipsis",
    "DISPLAY_NAME_MAX_LENGTH",
    "MASCOT_POOL",
    "TASK_TYPE_ICONS",
    "DEFAULT_ICON",
    # Feature #186: Tool Selection exports
    "AVAILABLE_TOOLS",
    "ROLE_TOOL_CATEGORIES",
    "ROLE_TOOL_OVERRIDES",
    "ToolSelectionResult",
    "get_all_tool_categories",
    "get_browser_tools",
    "get_test_runner_tools",
    "get_tool_info",
    "get_tools_by_category",
    "get_tools_by_privilege",
    "get_ui_agent_tools",
    "is_browser_tool",
    "select_tools_for_capability",
    "select_tools_for_role",
    # Validators exports (Feature #35: AcceptanceGate, Feature #140: LintCleanValidator)
    "AcceptanceGate",
    "FileExistsValidator",
    "GateResult",
    "LintCleanValidator",
    "TestEnforcementValidator",  # Feature #211
    "Validator",
    "ValidatorResult",
    "VALIDATOR_REGISTRY",
    "evaluate_acceptance_spec",
    "evaluate_validator",
    "get_validator",
    "normalize_acceptance_results_to_record",
    # Feature compiler exports
    "CATEGORY_TO_TASK_TYPE",
    "FeatureCompiler",
    "compile_feature",
    "extract_task_type_from_category",
    "get_budget_for_task_type",
    "get_feature_compiler",
    "get_tools_for_task_type",
    "reset_feature_compiler",
    "slugify",
    # WebSocket event broadcasting exports (Feature #61, #63)
    "AcceptanceUpdatePayload",
    "RunStartedPayload",
    "ValidatorResultPayload",
    "broadcast_acceptance_update",
    "broadcast_acceptance_update_sync",
    "broadcast_run_started",
    "broadcast_run_started_sync",
    "build_acceptance_update_from_results",
    "create_validator_result_payload",
    # Event recorder exports (Feature #30)
    "EventRecorder",
    "get_event_recorder",
    "clear_recorder_cache",
    # DSPy signature exports (Feature #50)
    "SpecGenerationSignature",
    "get_spec_generator",
    "validate_spec_output",
    "VALID_TASK_TYPES",
    "DSPY_DEFAULT_BUDGETS",
    # Feature #182: Octo DSPy signature exports
    "OctoSpecGenerationSignature",
    "get_octo_spec_generator",
    "validate_octo_spec_output",
    "convert_octo_output_to_agent_spec_dict",
    "VALID_AGENT_MODELS",
    "VALID_GATE_MODES",
    "VALID_OCTO_VALIDATOR_TYPES",
    # Feature #59: Unique Spec Name Generation exports
    "SPEC_NAME_MAX_LENGTH",
    "SPEC_NAME_PATTERN",
    "STOP_WORDS",
    "check_name_exists",
    "extract_keywords",
    "generate_sequence_suffix",
    "generate_slug",
    "generate_spec_name",
    "generate_spec_name_for_feature",
    "generate_timestamp_suffix",
    "generate_unique_spec_name",
    "get_existing_names_with_prefix",
    "normalize_slug",
    "validate_spec_name",
    # Feature #79: Orphaned Run Cleanup on Startup exports
    "ORPHANED_ERROR_MESSAGE",
    "DEFAULT_ORPHAN_TIMEOUT_SECONDS",
    "OrphanedRunInfo",
    "CleanupResult",
    "get_orphaned_runs",
    "is_run_stale",
    "cleanup_single_run",
    "cleanup_orphaned_runs",
    "get_orphan_statistics",
    # Feature #78: Invalid AgentSpec Graceful Handling exports
    "SPEC_REQUIRED_FIELDS",
    "SPEC_VALID_TASK_TYPES",
    "MIN_MAX_TURNS",
    "MAX_MAX_TURNS",
    "MIN_TIMEOUT_SECONDS",
    "MAX_TIMEOUT_SECONDS",
    "SPEC_NAME_PATTERN_RE",
    "TOOL_POLICY_REQUIRED_FIELDS",
    "SpecValidationError",
    "SpecValidationResult",
    "SpecValidationException",
    "validate_spec",
    "validate_spec_or_raise",
    "validate_spec_dict",
    # Feature #39: AUTOBUILDR_USE_KERNEL Migration Flag exports
    "MIGRATION_ENV_VAR_NAME",
    "DEFAULT_USE_KERNEL",
    "MIGRATION_TRUTHY_VALUES",
    "MIGRATION_FALSY_VALUES",
    "ExecutionPath",
    "FeatureExecutionResult",
    "get_use_kernel_env_value",
    "parse_use_kernel_value",
    "is_kernel_enabled",
    "set_kernel_enabled",
    "clear_kernel_flag",
    "execute_feature_legacy",
    "execute_feature_kernel",
    "execute_feature",
    "get_execution_path_string",
    "get_migration_status",
    # Feature #48: Path Traversal Attack Detection exports
    "PathTraversalResult",
    "contains_null_byte",
    "contains_path_traversal",
    "detect_path_traversal_attack",
    "normalize_path_for_comparison",
    "path_differs_after_normalization",
    # Feature #45: ToolProvider Interface Definition exports
    "ToolProviderError",
    "ToolNotFoundError",
    "ProviderNotFoundError",
    "ProviderAlreadyRegisteredError",
    "AuthenticationError",
    "ToolExecutionError",
    "ToolCategory",
    "AuthMethod",
    "ProviderStatus",
    "ProviderToolDefinition",
    "ToolResult",
    "ProviderCapabilities",
    "AuthCredentials",
    "AuthResult",
    "ToolProvider",
    "LocalToolProvider",
    "ToolProviderRegistry",
    "get_tool_registry",
    "reset_tool_registry",
    "register_provider",
    "execute_provider_tool",
    # Feature #54: DSPy Module Execution for Spec Generation exports
    "SpecBuilderError",
    "DSPyInitializationError",
    "DSPyExecutionError",
    "OutputValidationError",
    "ToolPolicyValidationError",
    "ValidatorsValidationError",
    "BuildResult",
    "ParsedOutput",
    "validate_tool_policy",
    "validate_validators",
    "parse_json_field",
    "coerce_integer",
    "SpecBuilder",
    "get_spec_builder",
    "reset_spec_builder",
    "DEFAULT_MODEL",
    "AVAILABLE_MODELS",
    "SPEC_BUILDER_TOOL_POLICY_REQUIRED_FIELDS",
    # Feature #56: Task Type Detection from Description exports
    "CODING_KEYWORDS",
    "TESTING_KEYWORDS",
    "REFACTORING_KEYWORDS",
    "DOCUMENTATION_KEYWORDS",
    "AUDIT_KEYWORDS",
    "TASK_TYPE_KEYWORDS",
    "DETECTOR_VALID_TASK_TYPES",
    "MIN_SCORE_THRESHOLD",
    "TIE_BREAKER_PRIORITY",
    "TaskTypeDetectionResult",
    "detect_task_type",
    "detect_task_type_detailed",
    "normalize_description",
    "score_task_type",
    "calculate_confidence",
    "get_keywords_for_type",
    "get_all_keyword_sets",
    "detector_get_valid_task_types",
    "is_valid_task_type",
    "explain_detection",
    # Feature #174: Maestro Agent Planning Detection exports
    "DEFAULT_AGENTS",
    "SPECIALIZED_CAPABILITY_KEYWORDS",
    "ProjectContext",
    "CapabilityRequirement",
    "AgentPlanningDecision",
    "Maestro",
    "get_maestro",
    "reset_maestro",
    "evaluate_project",
    "detect_agent_planning_required",
    # Feature #176: Octo Delegation Result
    "OctoDelegationResult",
    # Feature #179: Decision Persistence exports
    "PersistDecisionResult",
    "AgentPlanningDecisionRecord",
    # Feature #180: Octo Delegation With Fallback
    "OctoDelegationWithFallbackResult",
    # Feature #187: Octo Model Selection exports
    "OCTO_VALID_MODELS",
    "OCTO_DEFAULT_MODEL",
    "HAIKU_CAPABILITIES",
    "OPUS_CAPABILITIES",
    "TASK_TYPE_MODEL_DEFAULTS",
    "COMPLEXITY_INDICATORS",
    "select_model_for_capability",
    "validate_model",
    "get_model_characteristics",
    # Feature #190: Octo handles malformed project context gracefully
    "PayloadValidationError",
    "PayloadValidationResult",
    # Feature #188: Octo Schema Validation exports
    "OctoSchemaValidationError",
    "OctoSchemaValidationErrorDetail",
    "OctoSchemaValidationResult",
    "validate_agent_spec_schema",
    "validate_test_contract_schema",
    "validate_octo_outputs",
    "validate_agent_spec_schema_or_raise",
    "validate_test_contract_schema_or_raise",
    "get_schema",
    "AGENT_SPEC_SCHEMA",
    "TEST_CONTRACT_SCHEMA",
    "TEST_CONTRACT_ASSERTION_SCHEMA",
    "TEST_DEPENDENCY_SCHEMA",  # Feature #209
    "OCTO_SCHEMA_VALID_TASK_TYPES",
    "OCTO_SCHEMA_VALID_TEST_TYPES",
    "OCTO_SCHEMA_VALID_GATE_MODES",
    "VALID_ASSERTION_OPERATORS",
    "VALID_DEPENDENCY_TYPES",  # Feature #209
    # Feature #191: Octo uses agent archetypes for common patterns
    "AgentArchetype",
    "ArchetypeMatchResult",
    "CustomizedArchetype",
    "AGENT_ARCHETYPES",
    "HIGH_CONFIDENCE_THRESHOLD",
    "MEDIUM_CONFIDENCE_THRESHOLD",
    "LOW_CONFIDENCE_THRESHOLD",
    "get_archetype",
    "get_all_archetypes",
    "get_archetype_names",
    "archetype_exists",
    "map_capability_to_archetype",
    "is_custom_agent_needed",
    "customize_archetype",
    "create_agent_from_archetype",
    "get_archetype_for_task_type",
    "get_archetype_summary",
    # Feature #192: Agent Materializer exports
    # Feature #195: Agent Materializer audit event exports
    # Feature #196: Agent Materializer validates template output
    # Feature #218: Icon generation during materialization
    "AgentMaterializer",
    "AgentMaterializationResult",
    "BatchMaterializationResult",
    "MaterializationAuditInfo",
    "IconGenerationInfo",
    "MaterializerValidationError",
    "TemplateValidationResult",
    "TemplateValidationError",
    "MaterializerProgressCallback",  # Feature #197
    "render_agentspec_to_markdown",
    "verify_materializer_determinism",
    "MATERIALIZER_DEFAULT_OUTPUT_DIR",
    "MATERIALIZER_DEFAULT_MODEL",
    "MATERIALIZER_DEFAULT_COLOR",
    "TASK_TYPE_COLORS",
    "MATERIALIZER_VALID_MODELS",
    "DESCRIPTION_MAX_LENGTH",
    "REQUIRED_MARKDOWN_SECTIONS",
    "REQUIRED_FRONTMATTER_FIELDS",
    # Feature #199: .claude directory scaffolding exports
    "DirectoryStatus",
    "ScaffoldResult",
    "ScaffoldPreview",
    "ClaudeDirectoryScaffold",
    "scaffold_claude_directory",
    "preview_claude_directory",
    "ensure_claude_root",
    "ensure_agents_generated",
    "verify_claude_structure",
    "is_claude_scaffolded",
    "get_standard_subdirs",
    "CLAUDE_ROOT_DIR",
    "STANDARD_SUBDIRS",
    "DEFAULT_DIR_PERMISSIONS",
    "PHASE_1_DIRS",
    "PHASE_2_DIRS",
    # Feature #202: Project Initialization with Scaffolding exports
    "ScaffoldingStatus",
    "ProjectInitializationResult",
    "get_scaffolding_status",
    "needs_scaffolding",
    "initialize_project_scaffolding",
    "ensure_project_scaffolded",
    "is_project_initialized",
    "SCAFFOLDING_METADATA_KEY",
    "SCAFFOLDING_TIMESTAMP_KEY",
    "SCAFFOLDING_COMPLETED_KEY",
    "PROJECT_METADATA_FILE",
    # Feature #204: Scaffolding respects .gitignore patterns exports
    "GitignoreUpdateResult",
    "gitignore_exists",
    "update_gitignore",
    "ensure_gitignore_patterns",
    "verify_gitignore_patterns",
    "scaffold_with_gitignore",
    "GITIGNORE_FILE",
    "GITIGNORE_GENERATED_PATTERNS",
    "GITIGNORE_TRACKED_PATTERNS",
    # Feature #198: Settings Manager exports
    "SettingsUpdateResult",
    "SettingsRequirements",
    "SettingsManager",
    "check_settings_exist",
    "ensure_settings_for_agents",
    "detect_required_mcp_servers",
    "get_settings_manager",
    "SETTINGS_LOCAL_FILE",
    "SETTINGS_CLAUDE_DIR",
    "DEFAULT_SETTINGS_PERMISSIONS",
    "DEFAULT_SETTINGS",
    "MCP_SERVER_CONFIGS",
    "MCP_TOOL_PATTERNS",
    # Feature #206: Test Code Writer exports
    "TestCodeWriteResult",
    "TestCodeWriterAuditInfo",
    "FrameworkDetectionResult",
    "TestCodeWriter",
    "get_test_code_writer",
    "reset_test_code_writer_cache",
    "write_tests_from_contract",
    "detect_test_framework",
    "TEST_FRAMEWORKS",
    "DEFAULT_FRAMEWORKS",
    "TEST_DIR_PATTERNS",
    "TEST_FILE_EXTENSIONS",
    # Feature #207: Test Runner exports
    "TestFailure",
    "TestExecutionResult",
    "PytestResultParser",
    "UnittestResultParser",
    "JestResultParser",
    "TestRunner",
    "record_tests_executed",
    "run_tests",
    # Feature #208: Test Framework Support exports
    "TestFramework",
    "TestFrameworkDetectionResult",
    "TestCommand",
    "TestResult",
    "FrameworkPreference",
    "detect_framework",
    "generate_test_command",
    "get_available_options",
    "parse_test_output",
    "get_framework_preference",
    "set_framework_preference",
    "get_supported_frameworks",
    "get_framework_info",
    "FRAMEWORK_MARKERS",
    "FRAMEWORK_LANGUAGES",
    "DEFAULT_TEST_COMMANDS",
    "TEST_COMMAND_OPTIONS",
    "SETTINGS_FRAMEWORK_KEY",
    "SETTINGS_TEST_SECTION",
    # Feature #214: Sandbox Test Runner exports
    "SandboxConfiguration",
    "DependencyInstallResult",
    "SandboxExecutionResult",
    "SandboxTestRunner",
    "run_tests_in_sandbox",
    "is_sandbox_available",
    "get_default_sandbox_config",
    "record_sandbox_tests_executed",
    "DEFAULT_SANDBOX_IMAGE",
    "DEFAULT_PROJECT_MOUNT",
    "DEFAULT_SANDBOX_TIMEOUT",
    "DEFAULT_INSTALL_TIMEOUT",
    "DEPENDENCY_FILES",
    # Feature #210: Test Contract Gate exports
    "TestGateStatus",
    "TestGateConfiguration",
    "AssertionCoverage",
    "TestContractCoverage",
    "TestGateResult",
    "TestContractGate",
    "get_test_contract_gate",
    "reset_test_contract_gate",
    "evaluate_test_gate",
    "check_tests_required",
    "get_blocking_test_issues",
    "DEFAULT_ENFORCE_TEST_GATE",
    "DEFAULT_REQUIRE_ALL_ASSERTIONS",
    "DEFAULT_MIN_TEST_COVERAGE",
    "DEFAULT_ALLOW_SKIP_FOR_NO_CONTRACT",
    # Feature #212: Test Result Artifact exports
    "ARTIFACT_TYPE_TEST_RESULT",
    "MAX_FAILURES_IN_METADATA",
    "TestResultArtifactMetadata",
    "StoreTestResultResult",
    "RetrievedTestResult",
    "build_test_result_metadata",
    "serialize_test_result",
    "deserialize_test_result",
    "store_test_result_artifact",
    "get_test_result_store_result",
    "retrieve_test_result_from_artifact",
    "get_test_result_artifacts_for_run",
    "get_latest_test_result_artifact",
    "get_test_summary_from_artifact",
    "record_test_result_artifact_created",
    # Feature #213: Playwright MCP Configuration exports
    "PlaywrightMode",
    "PlaywrightToolSet",
    "PlaywrightMcpConfig",
    "PlaywrightAgentConfigResult",
    "McpConnectionResult",
    "get_playwright_config",
    "is_playwright_enabled",
    "enable_playwright",
    "disable_playwright",
    "get_playwright_tools",
    "configure_playwright_for_agent",
    "add_playwright_tools_to_spec",
    "is_e2e_agent",
    "get_mcp_server_config",
    "verify_mcp_connection",
    "ensure_playwright_in_settings",
    "get_e2e_agent_tools",
    "should_include_playwright_tools",
    "get_cached_playwright_config",
    "reset_playwright_config_cache",
    "PLAYWRIGHT_TOOLS",
    "CORE_PLAYWRIGHT_TOOLS",
    "EXTENDED_PLAYWRIGHT_TOOLS",
    "PLAYWRIGHT_TOOL_SETS",
    "SUPPORTED_BROWSERS",
    "DEFAULT_BROWSER",
    "DEFAULT_TIMEOUT_MS",
    "DEFAULT_VIEWPORT",
    "DEFAULT_PLAYWRIGHT_MCP_CONFIG",
    "HEADFUL_PLAYWRIGHT_MCP_CONFIG",
    "SETTINGS_PLAYWRIGHT_SECTION",
    # Feature #215: Icon Provider Interface exports
    "IconProviderError",
    "IconGenerationError",
    "IconProviderNotFoundError",
    "IconProviderAlreadyRegisteredError",
    "InvalidIconFormatError",
    "IconFormat",
    "IconTone",
    "IconProviderStatus",
    "IconResult",
    "IconProviderCapabilities",
    "IconGenerationRequest",
    "IconProvider",
    "DefaultIconProvider",
    "IconProviderRegistry",
    "get_icon_registry",
    "reset_icon_registry",
    "register_icon_provider",
    "generate_icon",
    "get_default_icon_provider",
    "configure_icon_provider_from_settings",
    "get_active_provider_from_config",
    "set_active_provider_in_config",
    "ICON_PROVIDER_CONFIG_KEY",
    "DEFAULT_ICON_PROVIDER_NAME",
    # Feature #216: LocalPlaceholderIconProvider exports
    "LocalPlaceholderIconProvider",
    "PlaceholderConfig",
    "PlaceholderShape",
    "get_local_placeholder_provider",
    "generate_placeholder_icon",
    "get_placeholder_color",
    "get_placeholder_initials",
    "compute_name_hash",
    "compute_color_from_name",
    "extract_initials",
    "generate_placeholder_svg",
    "generate_shape_svg",
    "LOCAL_PLACEHOLDER_PROVIDER_NAME",
    "DEFAULT_SVG_WIDTH",
    "DEFAULT_SVG_HEIGHT",
    "PLACEHOLDER_COLOR_PALETTE",
    # Feature #217: Icon Provider Configuration exports
    "ENV_VAR_ICON_PROVIDER",
    "SETTINGS_ICON_PROVIDER_KEY",
    "DEFAULT_ICON_PROVIDER",
    "KNOWN_PROVIDERS",
    "PROVIDER_ALIASES",
    "IconConfigSource",
    "IconProviderConfigResult",
    "IconProviderSettings",
    "normalize_provider_name",
    "is_valid_provider_name",
    "get_env_icon_provider",
    "get_settings_icon_provider",
    "resolve_icon_provider",
    "get_icon_provider",
    "set_icon_provider",
    "clear_icon_provider_override",
    "get_icon_provider_override",
    "load_icon_provider_settings",
    "save_icon_provider_settings",
    "validate_icon_provider_config",
    "get_available_providers",
    "get_provider_info",
    "configure_icon_provider",
    "get_icon_provider_config_documentation",
    # Feature #219: Icon Storage exports
    "ICON_INLINE_MAX_SIZE",
    "ICON_FORMAT_MIME_TYPES",
    "DEFAULT_PLACEHOLDER_PROVIDER",
    "StoredIconResult",
    "RetrievedIcon",
    "AgentIcon",
    "IconStorage",
    "get_mime_type_for_format",
    "store_icon_from_result",
    "get_icon_storage",
]
