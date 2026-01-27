"""
ToolProvider Interface
======================

Feature #45: ToolProvider Interface Definition

Defines the ToolProvider abstract interface for external tool sources with capability negotiation.

This module provides:
- ToolProvider abstract base class defining the tool provider contract
- ToolDefinition and ToolResult dataclasses for tool operations
- ProviderCapabilities for describing what a provider can do
- LocalToolProvider implementation for MCP tools
- ToolProviderRegistry for managing multiple providers

The ToolProvider interface allows the HarnessKernel to work with different
tool sources (MCP, Cowork, Composio, etc.) without knowing their implementation
details. This is a key extensibility point for the AutoBuildr system.

Example:
    >>> registry = ToolProviderRegistry()
    >>> registry.register(LocalToolProvider())
    >>> tools = registry.list_all_tools()
    >>> result = registry.execute_tool("local", "file_read", {"path": "/tmp/test.txt"})
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Protocol, runtime_checkable

_logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


# =============================================================================
# Exceptions
# =============================================================================

class ToolProviderError(Exception):
    """Base exception for tool provider errors."""
    pass


class ToolNotFoundError(ToolProviderError):
    """Raised when a requested tool is not found in the provider."""

    def __init__(
        self,
        tool_name: str,
        provider_name: str,
        message: str | None = None,
    ):
        self.tool_name = tool_name
        self.provider_name = provider_name

        if message is None:
            message = f"Tool '{tool_name}' not found in provider '{provider_name}'"

        super().__init__(message)


class ProviderNotFoundError(ToolProviderError):
    """Raised when a requested provider is not found in the registry."""

    def __init__(
        self,
        provider_name: str,
        available_providers: list[str] | None = None,
        message: str | None = None,
    ):
        self.provider_name = provider_name
        self.available_providers = available_providers or []

        if message is None:
            if self.available_providers:
                available = ", ".join(self.available_providers)
                message = f"Provider '{provider_name}' not found. Available providers: {available}"
            else:
                message = f"Provider '{provider_name}' not found. No providers are registered."

        super().__init__(message)


class ProviderAlreadyRegisteredError(ToolProviderError):
    """Raised when attempting to register a provider with a name that already exists."""

    def __init__(
        self,
        provider_name: str,
        message: str | None = None,
    ):
        self.provider_name = provider_name

        if message is None:
            message = f"Provider '{provider_name}' is already registered"

        super().__init__(message)


class AuthenticationError(ToolProviderError):
    """Raised when authentication fails for a provider."""

    def __init__(
        self,
        provider_name: str,
        reason: str,
        message: str | None = None,
    ):
        self.provider_name = provider_name
        self.reason = reason

        if message is None:
            message = f"Authentication failed for provider '{provider_name}': {reason}"

        super().__init__(message)


class ToolExecutionError(ToolProviderError):
    """Raised when tool execution fails."""

    def __init__(
        self,
        tool_name: str,
        provider_name: str,
        error: str,
        details: dict[str, Any] | None = None,
        message: str | None = None,
    ):
        self.tool_name = tool_name
        self.provider_name = provider_name
        self.error = error
        self.details = details or {}

        if message is None:
            message = f"Tool '{tool_name}' execution failed in provider '{provider_name}': {error}"

        super().__init__(message)


# =============================================================================
# Enums
# =============================================================================

class ToolCategory(str, Enum):
    """Categories for classifying tools by their function."""

    FILE_SYSTEM = "file_system"
    DATABASE = "database"
    NETWORK = "network"
    BROWSER = "browser"
    CODE_EXECUTION = "code_execution"
    VERSION_CONTROL = "version_control"
    TESTING = "testing"
    FEATURE_MANAGEMENT = "feature_management"
    GENERAL = "general"


class AuthMethod(str, Enum):
    """Authentication methods supported by providers."""

    NONE = "none"           # No authentication required
    API_KEY = "api_key"     # Simple API key authentication
    OAUTH2 = "oauth2"       # OAuth 2.0 flow
    BASIC = "basic"         # HTTP Basic authentication
    TOKEN = "token"         # Bearer token authentication
    CUSTOM = "custom"       # Provider-specific authentication


class ProviderStatus(str, Enum):
    """Status of a tool provider."""

    AVAILABLE = "available"             # Provider is ready to use
    UNAVAILABLE = "unavailable"         # Provider is not reachable
    AUTHENTICATION_REQUIRED = "auth_required"  # Needs authentication
    RATE_LIMITED = "rate_limited"       # Temporarily rate limited
    ERROR = "error"                     # Provider is in error state


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ToolDefinition:
    """
    Represents a tool definition with full metadata.

    This extends the basic ToolDefinition from tool_policy with additional
    fields needed for the ToolProvider interface.

    Attributes:
        name: Unique tool identifier within the provider
        description: Human-readable description of what the tool does
        input_schema: JSON Schema for tool input parameters
        output_schema: Optional JSON Schema for expected output
        category: Classification of the tool's function
        required_permissions: List of permissions needed to use this tool
        timeout_seconds: Default timeout for tool execution
        metadata: Additional provider-specific metadata
    """

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    category: ToolCategory = ToolCategory.GENERAL
    required_permissions: list[str] = field(default_factory=list)
    timeout_seconds: int = 30
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "category": self.category.value if isinstance(self.category, ToolCategory) else self.category,
            "required_permissions": self.required_permissions,
            "timeout_seconds": self.timeout_seconds,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolDefinition":
        """Create a ToolDefinition from a dictionary."""
        category = data.get("category", "general")
        if isinstance(category, str):
            try:
                category = ToolCategory(category)
            except ValueError:
                category = ToolCategory.GENERAL

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema"),
            category=category,
            required_permissions=data.get("required_permissions", []),
            timeout_seconds=data.get("timeout_seconds", 30),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ToolResult:
    """
    Result from executing a tool.

    Attributes:
        success: Whether the tool execution succeeded
        output: The tool's output (any JSON-serializable value)
        error: Error message if success is False
        error_code: Optional error code for programmatic handling
        execution_time_ms: How long the tool took to execute in milliseconds
        metadata: Additional result metadata
    """

    success: bool
    output: Any = None
    error: str | None = None
    error_code: str | None = None
    execution_time_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "error_code": self.error_code,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolResult":
        """Create a ToolResult from a dictionary."""
        return cls(
            success=data.get("success", False),
            output=data.get("output"),
            error=data.get("error"),
            error_code=data.get("error_code"),
            execution_time_ms=data.get("execution_time_ms", 0),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def success_result(cls, output: Any, execution_time_ms: int = 0) -> "ToolResult":
        """Create a successful tool result."""
        return cls(
            success=True,
            output=output,
            execution_time_ms=execution_time_ms,
        )

    @classmethod
    def error_result(
        cls,
        error: str,
        error_code: str | None = None,
        execution_time_ms: int = 0,
    ) -> "ToolResult":
        """Create an error tool result."""
        return cls(
            success=False,
            error=error,
            error_code=error_code,
            execution_time_ms=execution_time_ms,
        )


@dataclass
class ProviderCapabilities:
    """
    Describes what a ToolProvider can do.

    Used for capability negotiation between the kernel and providers.

    Attributes:
        supports_async: Whether the provider supports async tool execution
        supports_streaming: Whether the provider supports streaming output
        supports_batching: Whether multiple tools can be executed in a batch
        supports_cancellation: Whether running tools can be cancelled
        max_concurrent_calls: Maximum concurrent tool executions (0 = unlimited)
        supported_auth_methods: Authentication methods supported
        rate_limit_per_minute: Rate limit for tool calls (0 = unlimited)
        tool_categories: Categories of tools this provider offers
        version: Provider version string
        metadata: Additional capability metadata
    """

    supports_async: bool = False
    supports_streaming: bool = False
    supports_batching: bool = False
    supports_cancellation: bool = False
    max_concurrent_calls: int = 0
    supported_auth_methods: list[AuthMethod] = field(default_factory=lambda: [AuthMethod.NONE])
    rate_limit_per_minute: int = 0
    tool_categories: list[ToolCategory] = field(default_factory=list)
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "supports_async": self.supports_async,
            "supports_streaming": self.supports_streaming,
            "supports_batching": self.supports_batching,
            "supports_cancellation": self.supports_cancellation,
            "max_concurrent_calls": self.max_concurrent_calls,
            "supported_auth_methods": [
                m.value if isinstance(m, AuthMethod) else m
                for m in self.supported_auth_methods
            ],
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "tool_categories": [
                c.value if isinstance(c, ToolCategory) else c
                for c in self.tool_categories
            ],
            "version": self.version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProviderCapabilities":
        """Create ProviderCapabilities from a dictionary."""
        auth_methods = []
        for method in data.get("supported_auth_methods", ["none"]):
            if isinstance(method, str):
                try:
                    auth_methods.append(AuthMethod(method))
                except ValueError:
                    auth_methods.append(AuthMethod.CUSTOM)
            else:
                auth_methods.append(method)

        categories = []
        for cat in data.get("tool_categories", []):
            if isinstance(cat, str):
                try:
                    categories.append(ToolCategory(cat))
                except ValueError:
                    categories.append(ToolCategory.GENERAL)
            else:
                categories.append(cat)

        return cls(
            supports_async=data.get("supports_async", False),
            supports_streaming=data.get("supports_streaming", False),
            supports_batching=data.get("supports_batching", False),
            supports_cancellation=data.get("supports_cancellation", False),
            max_concurrent_calls=data.get("max_concurrent_calls", 0),
            supported_auth_methods=auth_methods,
            rate_limit_per_minute=data.get("rate_limit_per_minute", 0),
            tool_categories=categories,
            version=data.get("version", "1.0.0"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AuthCredentials:
    """
    Credentials for authenticating with a tool provider.

    This is a generic container for authentication information.
    Specific providers may require specific credential types.

    Attributes:
        method: The authentication method being used
        api_key: API key for API_KEY authentication
        access_token: Token for TOKEN/OAUTH2 authentication
        refresh_token: Refresh token for OAUTH2 authentication
        username: Username for BASIC authentication
        password: Password for BASIC authentication
        custom_data: Provider-specific authentication data
        expires_at: When the credentials expire (if applicable)
    """

    method: AuthMethod = AuthMethod.NONE
    api_key: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    username: str | None = None
    password: str | None = None
    custom_data: dict[str, Any] = field(default_factory=dict)
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        """Check if the credentials have expired."""
        if self.expires_at is None:
            return False
        return _utc_now() >= self.expires_at

    def to_dict(self, include_secrets: bool = False) -> dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Args:
            include_secrets: If True, include sensitive fields. Default False.
        """
        result = {
            "method": self.method.value if isinstance(self.method, AuthMethod) else self.method,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

        if include_secrets:
            result.update({
                "api_key": self.api_key,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "username": self.username,
                "password": self.password,
                "custom_data": self.custom_data,
            })
        else:
            # Indicate presence of credentials without exposing them
            result.update({
                "has_api_key": self.api_key is not None,
                "has_access_token": self.access_token is not None,
                "has_refresh_token": self.refresh_token is not None,
                "has_username": self.username is not None,
            })

        return result


@dataclass
class AuthResult:
    """
    Result from an authentication attempt.

    Attributes:
        success: Whether authentication succeeded
        credentials: Updated credentials if successful
        error: Error message if authentication failed
        requires_refresh: Whether credentials need to be refreshed
    """

    success: bool
    credentials: AuthCredentials | None = None
    error: str | None = None
    requires_refresh: bool = False

    def to_dict(self, include_secrets: bool = False) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "credentials": self.credentials.to_dict(include_secrets) if self.credentials else None,
            "error": self.error,
            "requires_refresh": self.requires_refresh,
        }


# =============================================================================
# ToolProvider Abstract Base Class
# =============================================================================

class ToolProvider(ABC):
    """
    Abstract base class for tool providers.

    A ToolProvider represents a source of tools that can be used by agents.
    This could be an MCP server, an external service like Cowork or Composio,
    or any other tool source.

    Implementations must provide:
    - name: A unique identifier for the provider
    - list_tools(): Get available tools
    - execute_tool(): Run a specific tool
    - get_capabilities(): Describe provider capabilities
    - authenticate(): Handle authentication (stub for future OAuth)

    Example Implementation:
        class MyToolProvider(ToolProvider):
            @property
            def name(self) -> str:
                return "my_provider"

            def list_tools(self) -> list[ToolDefinition]:
                return [
                    ToolDefinition(name="my_tool", description="Does something")
                ]

            def execute_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
                if name == "my_tool":
                    return ToolResult.success_result({"result": "done"})
                raise ToolNotFoundError(name, self.name)
    """

    # Class variable for provider type identification
    provider_type: ClassVar[str] = "base"

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Get the unique name of this provider.

        This name is used to identify the provider in the registry
        and for tool execution routing.

        Returns:
            str: The provider name (e.g., "local", "cowork", "composio")
        """
        ...

    @abstractmethod
    def list_tools(self) -> list[ToolDefinition]:
        """
        Get list of tools available from this provider.

        Returns:
            list[ToolDefinition]: List of tool definitions with full metadata

        Raises:
            ToolProviderError: If unable to retrieve tool list
        """
        ...

    @abstractmethod
    def execute_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
        """
        Execute a tool with the given arguments.

        Args:
            name: The name of the tool to execute
            args: Dictionary of arguments to pass to the tool

        Returns:
            ToolResult: The result of the tool execution

        Raises:
            ToolNotFoundError: If the tool is not found
            ToolExecutionError: If the tool execution fails
            ToolProviderError: For other provider errors
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """
        Get the capabilities of this provider.

        Used for capability negotiation with the kernel.

        Returns:
            ProviderCapabilities: Description of what this provider can do
        """
        ...

    def authenticate(self, credentials: AuthCredentials) -> AuthResult:
        """
        Authenticate with the provider using the given credentials.

        This is a stub for future OAuth integration. The default implementation
        returns success with the same credentials for providers that don't
        require authentication.

        Args:
            credentials: The credentials to use for authentication

        Returns:
            AuthResult: The result of the authentication attempt
        """
        # Default implementation for providers that don't require auth
        _logger.debug("authenticate() called on %s (default no-op)", self.name)
        return AuthResult(
            success=True,
            credentials=credentials,
        )

    def get_tool(self, name: str) -> ToolDefinition | None:
        """
        Get a specific tool by name.

        Convenience method that searches list_tools() for the given name.

        Args:
            name: The name of the tool to find

        Returns:
            ToolDefinition if found, None otherwise
        """
        for tool in self.list_tools():
            if tool.name == name:
                return tool
        return None

    def has_tool(self, name: str) -> bool:
        """
        Check if this provider has a tool with the given name.

        Args:
            name: The name of the tool to check

        Returns:
            bool: True if the tool exists, False otherwise
        """
        return self.get_tool(name) is not None

    def get_status(self) -> ProviderStatus:
        """
        Get the current status of this provider.

        Default implementation returns AVAILABLE. Subclasses can override
        to check actual connectivity or other conditions.

        Returns:
            ProviderStatus: The current provider status
        """
        return ProviderStatus.AVAILABLE

    def validate_args(self, tool_name: str, args: dict[str, Any]) -> list[str]:
        """
        Validate arguments for a tool against its input schema.

        Default implementation performs basic JSON Schema validation.
        Subclasses can override for custom validation.

        Args:
            tool_name: The name of the tool
            args: The arguments to validate

        Returns:
            list[str]: List of validation errors (empty if valid)
        """
        tool = self.get_tool(tool_name)
        if tool is None:
            return [f"Tool '{tool_name}' not found"]

        errors: list[str] = []
        schema = tool.input_schema

        if not schema:
            return errors  # No schema = no validation

        # Basic validation: check required properties
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for prop in required:
            if prop not in args:
                errors.append(f"Missing required argument: {prop}")

        # Check for unexpected arguments
        if properties:
            for arg in args:
                if arg not in properties:
                    errors.append(f"Unexpected argument: {arg}")

        return errors


# =============================================================================
# LocalToolProvider Implementation
# =============================================================================

class LocalToolProvider(ToolProvider):
    """
    ToolProvider implementation for local/MCP tools.

    This provider wraps the existing MCP tool infrastructure and exposes
    it through the ToolProvider interface. It serves as the default
    provider for tools available in the local environment.

    Tools can be registered explicitly or discovered from MCP servers.
    For now, this provides a static list of commonly available tools.

    Example:
        >>> provider = LocalToolProvider()
        >>> tools = provider.list_tools()
        >>> result = provider.execute_tool("file_read", {"path": "/tmp/test.txt"})
    """

    provider_type: ClassVar[str] = "local"

    def __init__(
        self,
        tools: list[ToolDefinition] | None = None,
        tool_executor: Any | None = None,
    ):
        """
        Initialize the LocalToolProvider.

        Args:
            tools: Optional list of tools to make available. If not provided,
                   a default set of MCP-compatible tools will be used.
            tool_executor: Optional callable for executing tools. If not provided,
                          execute_tool will return a placeholder result.
        """
        self._tools: dict[str, ToolDefinition] = {}
        self._tool_executor = tool_executor

        if tools:
            for tool in tools:
                self._tools[tool.name] = tool
        else:
            # Initialize with default MCP tools
            self._init_default_tools()

    def _init_default_tools(self) -> None:
        """Initialize with default MCP-compatible tools."""
        default_tools = [
            # Feature management tools
            ToolDefinition(
                name="feature_get_by_id",
                description="Get a feature by its ID",
                input_schema={
                    "type": "object",
                    "properties": {
                        "feature_id": {"type": "integer", "description": "The feature ID"}
                    },
                    "required": ["feature_id"]
                },
                category=ToolCategory.FEATURE_MANAGEMENT,
            ),
            ToolDefinition(
                name="feature_mark_passing",
                description="Mark a feature as passing",
                input_schema={
                    "type": "object",
                    "properties": {
                        "feature_id": {"type": "integer", "description": "The feature ID"}
                    },
                    "required": ["feature_id"]
                },
                category=ToolCategory.FEATURE_MANAGEMENT,
            ),
            ToolDefinition(
                name="feature_mark_in_progress",
                description="Mark a feature as in-progress",
                input_schema={
                    "type": "object",
                    "properties": {
                        "feature_id": {"type": "integer", "description": "The feature ID"}
                    },
                    "required": ["feature_id"]
                },
                category=ToolCategory.FEATURE_MANAGEMENT,
            ),
            ToolDefinition(
                name="feature_skip",
                description="Skip a feature (move to end of queue)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "feature_id": {"type": "integer", "description": "The feature ID"}
                    },
                    "required": ["feature_id"]
                },
                category=ToolCategory.FEATURE_MANAGEMENT,
            ),
            ToolDefinition(
                name="feature_get_stats",
                description="Get feature completion statistics",
                input_schema={"type": "object", "properties": {}},
                category=ToolCategory.FEATURE_MANAGEMENT,
            ),

            # File system tools
            ToolDefinition(
                name="Read",
                description="Read a file from the filesystem",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "The file path to read"}
                    },
                    "required": ["file_path"]
                },
                category=ToolCategory.FILE_SYSTEM,
            ),
            ToolDefinition(
                name="Write",
                description="Write content to a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "The file path to write to"},
                        "content": {"type": "string", "description": "The content to write"}
                    },
                    "required": ["file_path", "content"]
                },
                category=ToolCategory.FILE_SYSTEM,
            ),
            ToolDefinition(
                name="Edit",
                description="Edit a file with search and replace",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "The file path to edit"},
                        "old_string": {"type": "string", "description": "Text to search for"},
                        "new_string": {"type": "string", "description": "Text to replace with"}
                    },
                    "required": ["file_path", "old_string", "new_string"]
                },
                category=ToolCategory.FILE_SYSTEM,
            ),
            ToolDefinition(
                name="Glob",
                description="Find files matching a pattern",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob pattern to match"}
                    },
                    "required": ["pattern"]
                },
                category=ToolCategory.FILE_SYSTEM,
            ),
            ToolDefinition(
                name="Grep",
                description="Search file contents with regex",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Regex pattern to search for"}
                    },
                    "required": ["pattern"]
                },
                category=ToolCategory.FILE_SYSTEM,
            ),

            # Code execution tools
            ToolDefinition(
                name="Bash",
                description="Execute a bash command",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The command to execute"}
                    },
                    "required": ["command"]
                },
                category=ToolCategory.CODE_EXECUTION,
            ),

            # Browser automation tools
            ToolDefinition(
                name="browser_navigate",
                description="Navigate to a URL in the browser",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to navigate to"}
                    },
                    "required": ["url"]
                },
                category=ToolCategory.BROWSER,
            ),
            ToolDefinition(
                name="browser_click",
                description="Click an element in the browser",
                input_schema={
                    "type": "object",
                    "properties": {
                        "ref": {"type": "string", "description": "Element reference to click"}
                    },
                    "required": ["ref"]
                },
                category=ToolCategory.BROWSER,
            ),
            ToolDefinition(
                name="browser_snapshot",
                description="Capture accessibility snapshot of the page",
                input_schema={"type": "object", "properties": {}},
                category=ToolCategory.BROWSER,
            ),
            ToolDefinition(
                name="browser_take_screenshot",
                description="Take a screenshot of the page",
                input_schema={
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["png", "jpeg"]}
                    }
                },
                category=ToolCategory.BROWSER,
            ),
        ]

        for tool in default_tools:
            self._tools[tool.name] = tool

    @property
    def name(self) -> str:
        """Get the provider name."""
        return "local"

    def list_tools(self) -> list[ToolDefinition]:
        """Get list of available tools."""
        return list(self._tools.values())

    def execute_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
        """
        Execute a tool with the given arguments.

        If a tool_executor was provided, it will be used to execute the tool.
        Otherwise, returns a placeholder result indicating the tool would be executed.
        """
        if name not in self._tools:
            raise ToolNotFoundError(name, self.name)

        if self._tool_executor is not None:
            try:
                import time
                start_time = time.time()
                result = self._tool_executor(name, args)
                execution_time_ms = int((time.time() - start_time) * 1000)

                if isinstance(result, ToolResult):
                    return result

                return ToolResult.success_result(result, execution_time_ms)

            except Exception as e:
                _logger.error("Tool execution failed: %s - %s", name, e)
                raise ToolExecutionError(name, self.name, str(e))

        # Placeholder result when no executor is configured
        _logger.debug(
            "Tool '%s' called with args %s (no executor configured)",
            name, args
        )
        return ToolResult(
            success=True,
            output={
                "message": f"Tool '{name}' would be executed",
                "args": args,
            },
            metadata={"placeholder": True},
        )

    def get_capabilities(self) -> ProviderCapabilities:
        """Get provider capabilities."""
        categories = list(set(tool.category for tool in self._tools.values()))

        return ProviderCapabilities(
            supports_async=False,  # MCP tools are synchronous
            supports_streaming=False,
            supports_batching=False,
            supports_cancellation=False,
            max_concurrent_calls=1,
            supported_auth_methods=[AuthMethod.NONE],
            rate_limit_per_minute=0,  # No rate limit
            tool_categories=categories,
            version="1.0.0",
            metadata={"provider_type": "local"},
        )

    def add_tool(self, tool: ToolDefinition) -> None:
        """
        Add a tool to the provider.

        Args:
            tool: The tool definition to add
        """
        self._tools[tool.name] = tool
        _logger.debug("Added tool '%s' to local provider", tool.name)

    def remove_tool(self, name: str) -> bool:
        """
        Remove a tool from the provider.

        Args:
            name: The name of the tool to remove

        Returns:
            bool: True if the tool was removed, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            _logger.debug("Removed tool '%s' from local provider", name)
            return True
        return False


# =============================================================================
# ToolProviderRegistry
# =============================================================================

class ToolProviderRegistry:
    """
    Registry for managing multiple tool providers.

    The registry allows:
    - Registering and unregistering providers
    - Looking up providers by name
    - Listing all available tools across providers
    - Executing tools by routing to the correct provider

    Example:
        >>> registry = ToolProviderRegistry()
        >>> registry.register(LocalToolProvider())
        >>> registry.register(MyExternalProvider())
        >>>
        >>> # List all tools
        >>> all_tools = registry.list_all_tools()
        >>>
        >>> # Execute a tool
        >>> result = registry.execute_tool("local", "file_read", {"path": "/tmp/test"})
        >>>
        >>> # Get capabilities
        >>> caps = registry.get_all_capabilities()
    """

    def __init__(self):
        """Initialize an empty registry."""
        self._providers: dict[str, ToolProvider] = {}
        _logger.debug("ToolProviderRegistry initialized")

    def register(
        self,
        provider: ToolProvider,
        *,
        replace: bool = False,
    ) -> None:
        """
        Register a tool provider.

        Args:
            provider: The provider to register
            replace: If True, replace existing provider with same name

        Raises:
            ProviderAlreadyRegisteredError: If provider name already exists and replace=False
        """
        name = provider.name

        if name in self._providers and not replace:
            raise ProviderAlreadyRegisteredError(name)

        self._providers[name] = provider
        _logger.info("Registered tool provider: %s", name)

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool provider.

        Args:
            name: The name of the provider to unregister

        Returns:
            bool: True if the provider was removed, False if not found
        """
        if name in self._providers:
            del self._providers[name]
            _logger.info("Unregistered tool provider: %s", name)
            return True
        return False

    def get_provider(self, name: str) -> ToolProvider:
        """
        Get a provider by name.

        Args:
            name: The provider name

        Returns:
            ToolProvider: The requested provider

        Raises:
            ProviderNotFoundError: If the provider is not found
        """
        if name not in self._providers:
            raise ProviderNotFoundError(name, list(self._providers.keys()))
        return self._providers[name]

    def has_provider(self, name: str) -> bool:
        """
        Check if a provider is registered.

        Args:
            name: The provider name

        Returns:
            bool: True if the provider exists
        """
        return name in self._providers

    def list_providers(self) -> list[str]:
        """
        List all registered provider names.

        Returns:
            list[str]: Names of all registered providers
        """
        return list(self._providers.keys())

    def list_all_tools(self) -> dict[str, list[ToolDefinition]]:
        """
        List all tools from all providers.

        Returns:
            dict[str, list[ToolDefinition]]: Map of provider name to tool list
        """
        result: dict[str, list[ToolDefinition]] = {}
        for name, provider in self._providers.items():
            try:
                result[name] = provider.list_tools()
            except Exception as e:
                _logger.error("Failed to list tools from provider %s: %s", name, e)
                result[name] = []
        return result

    def get_all_capabilities(self) -> dict[str, ProviderCapabilities]:
        """
        Get capabilities from all providers.

        Returns:
            dict[str, ProviderCapabilities]: Map of provider name to capabilities
        """
        result: dict[str, ProviderCapabilities] = {}
        for name, provider in self._providers.items():
            try:
                result[name] = provider.get_capabilities()
            except Exception as e:
                _logger.error("Failed to get capabilities from provider %s: %s", name, e)
        return result

    def execute_tool(
        self,
        provider_name: str,
        tool_name: str,
        args: dict[str, Any],
    ) -> ToolResult:
        """
        Execute a tool from a specific provider.

        Args:
            provider_name: The name of the provider
            tool_name: The name of the tool to execute
            args: Arguments to pass to the tool

        Returns:
            ToolResult: The result of the tool execution

        Raises:
            ProviderNotFoundError: If the provider is not found
            ToolNotFoundError: If the tool is not found
            ToolExecutionError: If the tool execution fails
        """
        provider = self.get_provider(provider_name)
        return provider.execute_tool(tool_name, args)

    def find_tool(self, tool_name: str) -> tuple[str, ToolDefinition] | None:
        """
        Find a tool across all providers.

        Args:
            tool_name: The name of the tool to find

        Returns:
            Tuple of (provider_name, tool_definition) if found, None otherwise
        """
        for name, provider in self._providers.items():
            tool = provider.get_tool(tool_name)
            if tool is not None:
                return (name, tool)
        return None

    def execute_tool_any(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        """
        Execute a tool, finding it in any registered provider.

        This is a convenience method that searches all providers for the tool.
        For deterministic behavior, use execute_tool with an explicit provider name.

        Args:
            tool_name: The name of the tool to execute
            args: Arguments to pass to the tool

        Returns:
            ToolResult: The result of the tool execution

        Raises:
            ToolNotFoundError: If the tool is not found in any provider
        """
        result = self.find_tool(tool_name)
        if result is None:
            raise ToolNotFoundError(
                tool_name,
                "registry",
                f"Tool '{tool_name}' not found in any registered provider. "
                f"Available providers: {', '.join(self._providers.keys())}"
            )

        provider_name, _ = result
        return self.execute_tool(provider_name, tool_name, args)

    def get_provider_status(self) -> dict[str, ProviderStatus]:
        """
        Get status of all registered providers.

        Returns:
            dict[str, ProviderStatus]: Map of provider name to status
        """
        result: dict[str, ProviderStatus] = {}
        for name, provider in self._providers.items():
            try:
                result[name] = provider.get_status()
            except Exception as e:
                _logger.error("Failed to get status from provider %s: %s", name, e)
                result[name] = ProviderStatus.ERROR
        return result

    def clear(self) -> None:
        """Remove all registered providers."""
        self._providers.clear()
        _logger.info("Cleared all tool providers from registry")


# =============================================================================
# Module-level convenience functions
# =============================================================================

# Global registry instance
_global_registry: ToolProviderRegistry | None = None


def get_tool_registry() -> ToolProviderRegistry:
    """
    Get the global ToolProviderRegistry instance.

    Creates a new registry with a LocalToolProvider if one doesn't exist.

    Returns:
        ToolProviderRegistry: The global registry
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolProviderRegistry()
        _global_registry.register(LocalToolProvider())
    return _global_registry


def reset_tool_registry() -> None:
    """
    Reset the global ToolProviderRegistry.

    This is useful for testing or when you need to reconfigure providers.
    """
    global _global_registry
    _global_registry = None


def register_provider(provider: ToolProvider, *, replace: bool = False) -> None:
    """
    Register a provider in the global registry.

    Convenience function for get_tool_registry().register().

    Args:
        provider: The provider to register
        replace: If True, replace existing provider with same name
    """
    get_tool_registry().register(provider, replace=replace)


def execute_tool(
    tool_name: str,
    args: dict[str, Any],
    *,
    provider_name: str | None = None,
) -> ToolResult:
    """
    Execute a tool using the global registry.

    Args:
        tool_name: The name of the tool to execute
        args: Arguments to pass to the tool
        provider_name: Optional specific provider to use

    Returns:
        ToolResult: The result of the tool execution
    """
    registry = get_tool_registry()
    if provider_name:
        return registry.execute_tool(provider_name, tool_name, args)
    return registry.execute_tool_any(tool_name, args)
