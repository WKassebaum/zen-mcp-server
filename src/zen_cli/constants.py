"""Constants and enums used throughout the Zen CLI.

This module centralizes all magic strings and constants to improve
maintainability and reduce errors from typos.
"""

from enum import Enum, auto
from typing import Final


# Model selection constants
MODEL_AUTO: Final[str] = "auto"
DEFAULT_MODEL: Final[str] = "gemini-2.5-flash"
DEFAULT_TEMPERATURE: Final[float] = 0.7


class ModelCategory(str, Enum):
    """Categories of models for automatic selection."""
    DEFAULT = "default"
    FAST_RESPONSE = "fast"
    REASONING = "reasoning"
    CREATIVE = "creative"
    ANALYTICAL = "analytical"


class ConfidenceLevel(str, Enum):
    """Confidence levels for debugging and analysis."""
    EXPLORING = "exploring"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"
    ALMOST_CERTAIN = "almost_certain"
    CERTAIN = "certain"


class ReviewType(str, Enum):
    """Types of code reviews."""
    ALL = "all"
    SECURITY = "security"
    PERFORMANCE = "performance"
    QUALITY = "quality"


class AnalysisType(str, Enum):
    """Types of code analysis."""
    GENERAL = "general"
    ARCHITECTURE = "architecture"
    COMPLEXITY = "complexity"


class TraceMode(str, Enum):
    """Modes for code tracing."""
    ASK = "ask"
    PRECISION = "precision"
    DEPENDENCIES = "dependencies"


class ThreatLevel(str, Enum):
    """Security threat levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityScope(str, Enum):
    """Security audit scopes."""
    WEB = "web"
    MOBILE = "mobile"
    API = "api"
    ENTERPRISE = "enterprise"
    CLOUD = "cloud"


class OutputFormat(str, Enum):
    """Output format options."""
    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"
    TABLE = "table"


class ThinkingMode(str, Enum):
    """Thinking depth modes for models."""
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


# Session and continuation constants
SESSION_PREFIX: Final[str] = "cli_session_"
DEFAULT_CONTINUATION_ID: Final[str] = "default"

# File size and token limits
MAX_FILE_SIZE: Final[int] = 1_000_000  # 1MB
MAX_TOKEN_LIMIT: Final[int] = 128_000  # Conservative token limit
DEFAULT_MAX_OUTPUT_TOKENS: Final[int] = 8192

# Retry configuration defaults
DEFAULT_RETRY_ATTEMPTS: Final[int] = 3
DEFAULT_RETRY_INITIAL_DELAY: Final[float] = 1.0
DEFAULT_RETRY_MAX_DELAY: Final[float] = 60.0
DEFAULT_RETRY_EXPONENTIAL_BASE: Final[float] = 2.0

# Progress and timeout settings
DEFAULT_COMMAND_TIMEOUT: Final[int] = 120  # 2 minutes
PROGRESS_SPINNER_DELAY: Final[float] = 0.1

# Tool categories (for model selection)
UTILITY_TOOLS: Final[set] = {"listmodels", "version"}
WORKFLOW_TOOLS: Final[set] = {
    "debug", "codereview", "analyze", "refactor", 
    "secaudit", "tracer", "docgen", "precommit", 
    "thinkdeep", "planner", "testgen"
}
SIMPLE_TOOLS: Final[set] = {"chat", "consensus", "challenge"}

# Error messages
ERROR_UNKNOWN_TOOL: Final[str] = "Unknown tool: {tool_name}"
ERROR_MODEL_NOT_AVAILABLE: Final[str] = "Model '{model_name}' is not available"
ERROR_FILE_NOT_FOUND: Final[str] = "File not found: {file_path}"
ERROR_INVALID_INPUT: Final[str] = "Invalid input: {details}"
ERROR_API_KEY_MISSING: Final[str] = "API key not configured for {provider}"
ERROR_RETRY_EXHAUSTED: Final[str] = "Failed after {attempts} attempts: {error}"

# Success messages
SUCCESS_COMMAND_COMPLETE: Final[str] = "Command completed successfully"
SUCCESS_FILE_WRITTEN: Final[str] = "File written: {file_path}"
SUCCESS_CONFIG_SAVED: Final[str] = "Configuration saved"

# CLI help text snippets
HELP_MODEL_OPTION: Final[str] = "Model to use (auto for automatic selection)"
HELP_FILES_OPTION: Final[str] = "Files to include for context"
HELP_CONFIDENCE_OPTION: Final[str] = "Confidence level in understanding the problem"
HELP_OUTPUT_FORMAT: Final[str] = "Output format (text, json, markdown)"
HELP_SESSION_OPTION: Final[str] = "Session ID for conversation continuity"

# Environment variable names
ENV_ZEN_CLI_MODE: Final[str] = "ZEN_CLI_MODE"
ENV_GEMINI_API_KEY: Final[str] = "GEMINI_API_KEY"
ENV_OPENAI_API_KEY: Final[str] = "OPENAI_API_KEY"
ENV_REDIS_HOST: Final[str] = "REDIS_HOST"
ENV_REDIS_PORT: Final[str] = "REDIS_PORT"
ENV_STORAGE_TYPE: Final[str] = "ZEN_STORAGE_TYPE"

# Storage types
class StorageType(str, Enum):
    """Types of storage backends."""
    MEMORY = "memory"
    FILE = "file"
    REDIS = "redis"


# Workflow step status
class WorkflowStatus(str, Enum):
    """Status of workflow execution."""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    FILES_REQUIRED = "files_required_to_continue"
    ANALYSIS_COMPLETE = "analysis_complete"