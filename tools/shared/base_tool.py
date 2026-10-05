"""
Core Tool Infrastructure for ZEN MCP Tools

This module provides the fundamental base class for all tools:
- BaseTool: Abstract base class defining the tool interface

The BaseTool class defines the core contract that tools must implement and provides
common functionality for request validation, error handling, model management,
conversation handling, file processing, and response formatting.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

from mcp.types import TextContent

if TYPE_CHECKING:
    from providers.shared import ModelCapabilities
    from tools.models import ToolModelCategory

from config import MCP_PROMPT_SIZE_LIMIT
from providers import ModelProvider, ModelProviderRegistry
from utils import estimate_tokens
from utils.conversation_memory import (
    ConversationTurn,
    get_conversation_file_list,
    get_conversation_media_first_seen,
    get_conversation_media_kinds,
    get_conversation_media_list,
    get_thread,
)
from utils.env import get_env
from utils.file_utils import NOT_TEXT_FILE_HEADERS, read_file_content, read_files

# Import models from tools.models for compatibility
try:
    from tools.models import SPECIAL_STATUS_MODELS, ContinuationOffer, ToolOutput
except ImportError:
    # Fallback in case models haven't been set up yet
    SPECIAL_STATUS_MODELS = {}
    ContinuationOffer = None
    ToolOutput = None

logger = logging.getLogger(__name__)

# The model field's note on intent words (providers.registry.INTENT_MODELS), in auto and non-auto mode alike
INTENT_MODELS_NOTE = "Or an intent: 'frontier' (best available), 'balanced', 'fast'; 'auto' picks per tool."


class BaseTool(ABC):
    """
    Abstract base class for all ZEN MCP tools.

    This class defines the interface that all tools must implement and provides
    common functionality for request handling, model creation, and response formatting.

    CONVERSATION-AWARE FILE PROCESSING:
    This base class implements the sophisticated dual prioritization strategy for
    conversation-aware file handling across all tools:

    1. FILE DEDUPLICATION WITH NEWEST-FIRST PRIORITY:
       - When same file appears in multiple conversation turns, newest reference wins
       - Prevents redundant file embedding while preserving most recent file state
       - Cross-tool file tracking ensures consistent behavior across analyze → codereview → debug

    2. CONVERSATION CONTEXT INTEGRATION:
       - All tools receive enhanced prompts with conversation history via reconstruct_thread_context()
       - File references from previous turns are preserved and accessible
       - Cross-tool knowledge transfer maintains full context without manual file re-specification

    3. TOKEN-AWARE FILE EMBEDDING:
       - Respects model-specific token allocation budgets from ModelContext
       - Prioritizes conversation history, then newest files, then remaining content
       - Graceful degradation when token limits are approached

    4. STATELESS-TO-STATEFUL BRIDGING:
       - Tools operate on stateless MCP requests but access full conversation state
       - Conversation memory automatically injected via continuation_id parameter
       - Enables natural AI-to-AI collaboration across tool boundaries

    To create a new tool:
    1. Create a new class that inherits from BaseTool
    2. Implement all abstract methods
    3. Define a request model that inherits from ToolRequest
    4. Register the tool in server.py's TOOLS dictionary
    """

    # Class-level cache for OpenRouter registry to avoid multiple loads
    _openrouter_registry_cache = None
    _custom_registry_cache = None

    @classmethod
    def _get_openrouter_registry(cls):
        """Get cached OpenRouter registry instance, creating if needed."""
        # Use BaseTool class directly to ensure cache is shared across all subclasses
        if BaseTool._openrouter_registry_cache is None:
            from providers.registries.openrouter import OpenRouterModelRegistry

            BaseTool._openrouter_registry_cache = OpenRouterModelRegistry()
            logger.debug("Created cached OpenRouter registry instance")
        return BaseTool._openrouter_registry_cache

    @classmethod
    def _get_custom_registry(cls):
        """Get cached custom-endpoint registry instance."""
        if BaseTool._custom_registry_cache is None:
            from providers.registries.custom import CustomEndpointModelRegistry

            BaseTool._custom_registry_cache = CustomEndpointModelRegistry()
            logger.debug("Created cached Custom registry instance")
        return BaseTool._custom_registry_cache

    def __init__(self):
        # Cache tool metadata at initialization to avoid repeated calls
        self.name = self.get_name()
        self.description = self.get_description()
        self.default_temperature = self.get_default_temperature()
        # Tool initialization complete

    @abstractmethod
    def get_name(self) -> str:
        """
        Return the unique name identifier for this tool.

        This name is used by MCP clients to invoke the tool and must be
        unique across all registered tools.

        Returns:
            str: The tool's unique name (e.g., "review_code", "analyze")
        """
        pass

    @abstractmethod
    def get_description(self) -> str:
        """
        Return a detailed description of what this tool does.

        This description is shown to MCP clients (like Claude / Codex / Gemini) to help them
        understand when and how to use the tool. It should be comprehensive
        and include trigger phrases.

        Returns:
            str: Detailed tool description with usage examples
        """
        pass

    @abstractmethod
    def get_input_schema(self) -> dict[str, Any]:
        """
        Return the JSON Schema that defines this tool's parameters.

        This schema is used by MCP clients to validate inputs before
        sending requests. It should match the tool's request model.

        Returns:
            Dict[str, Any]: JSON Schema object defining required and optional parameters
        """
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Return the system prompt that configures the AI model's behavior.

        This prompt sets the context and instructions for how the model
        should approach the task. It's prepended to the user's request.

        Returns:
            str: System prompt with role definition and instructions
        """
        pass

    def get_capability_system_prompts(self, capabilities: Optional["ModelCapabilities"]) -> list[str]:
        """Return additional system prompt snippets gated on model capabilities.

        Subclasses can override this hook to append capability-specific
        instructions (for example, enabling code-generation exports when a
        model advertises support). The default implementation returns an empty
        list so no extra instructions are appended.

        Args:
            capabilities: The resolved capabilities for the active model.

        Returns:
            List of prompt fragments to append after the base system prompt.
        """

        return []

    def _augment_system_prompt_with_capabilities(
        self, base_prompt: str, capabilities: Optional["ModelCapabilities"]
    ) -> str:
        """Merge capability-driven prompt addenda with the base system prompt."""

        additions: list[str] = []
        if capabilities is not None:
            additions = [fragment.strip() for fragment in self.get_capability_system_prompts(capabilities) if fragment]

        if not additions:
            return base_prompt

        addition_text = "\n\n".join(additions)
        if not base_prompt:
            return addition_text

        suffix = "" if base_prompt.endswith("\n\n") else "\n\n"
        return f"{base_prompt}{suffix}{addition_text}"

    def get_annotations(self) -> Optional[dict[str, Any]]:
        """
        Return optional annotations for this tool.

        Annotations provide hints about tool behavior without being security-critical.
        They help MCP clients make better decisions about tool usage.

        Returns:
            Optional[dict]: Dictionary with annotation fields like readOnlyHint, destructiveHint, etc.
                           Returns None if no annotations are needed.
        """
        return None

    def requires_model(self) -> bool:
        """
        Return whether this tool requires AI model access.

        Tools that override execute() to do pure data processing (like planner)
        should return False to skip model resolution at the MCP boundary.

        Returns:
            bool: True if tool needs AI model access (default), False for data-only tools
        """
        return True

    def is_effective_auto_mode(self) -> bool:
        """
        Check if we're in effective auto mode for schema generation.

        This determines whether the model parameter should be required in the tool schema.
        Used at initialization time when schemas are generated.

        Returns:
            bool: True if model parameter should be required in the schema
        """
        from config import DEFAULT_MODEL
        from providers.registry import ModelProviderRegistry

        # Case 1: Explicit auto mode
        if DEFAULT_MODEL.lower() == "auto":
            return True

        # Case 2: Model not available (fallback to auto mode)
        if DEFAULT_MODEL.lower() != "auto":
            provider = ModelProviderRegistry.get_provider_for_model(DEFAULT_MODEL)
            if not provider:
                return True

        return False

    def _should_require_model_selection(self, model_name: str) -> bool:
        """
        Check if we should require the CLI to select a model at runtime.

        This is called during request execution to determine if we need
        to return an error asking the CLI to provide a model parameter.

        Args:
            model_name: The model name from the request or DEFAULT_MODEL

        Returns:
            bool: True if we should require model selection
        """
        # NOTE: Auto mode is now handled by _resolve_model_context() before this check.
        # If "auto" reaches here, it indicates a code path that bypassed resolution.
        if model_name.lower() == "auto":
            logger_instance = logging.getLogger(f"tools.{self.name}")
            logger_instance.error(
                f"Auto mode reached validation without resolution in {self.name} tool. "
                "This indicates a code path that bypassed model resolution."
            )
            return True

        # Check if requested model is available
        from providers.registry import ModelProviderRegistry

        provider = ModelProviderRegistry.get_provider_for_model(model_name)
        if not provider:
            logger_instance = logging.getLogger(f"tools.{self.name}")
            logger_instance.warning(f"Model '{model_name}' is not available with current API keys.")
            return True

        return False

    def _get_available_models(self) -> list[str]:
        """
        Get list of models available from enabled providers.

        Only returns models from providers that have valid API keys configured.
        This fixes the namespace collision bug where models from disabled providers
        were shown to the CLI, causing routing conflicts.

        Returns:
            List of model names from enabled providers only
        """
        from providers.registry import ModelProviderRegistry

        # Get models from enabled providers only (those with valid API keys)
        all_models = ModelProviderRegistry.get_available_model_names()

        # Add OpenRouter models if OpenRouter is configured
        openrouter_key = get_env("OPENROUTER_API_KEY")
        if openrouter_key and openrouter_key != "your_openrouter_api_key_here":
            try:
                registry = self._get_openrouter_registry()
                # Add all aliases from the registry (includes OpenRouter cloud models)
                for alias in registry.list_aliases():
                    if alias not in all_models:
                        all_models.append(alias)
            except Exception as e:
                import logging

                logging.debug(f"Failed to add OpenRouter models to enum: {e}")

        # Add custom models if custom API is configured
        custom_url = get_env("CUSTOM_API_URL")
        if custom_url:
            try:
                registry = self._get_custom_registry()
                for alias in registry.list_aliases():
                    if alias not in all_models:
                        all_models.append(alias)
            except Exception as e:
                import logging

                logging.debug(f"Failed to add custom models to enum: {e}")

        # Remove duplicates while preserving order
        seen = set()
        unique_models = []
        for model in all_models:
            if model not in seen:
                seen.add(model)
                unique_models.append(model)

        return unique_models

    def _format_available_models_list(self) -> str:
        """Return a human-friendly list of available models or guidance when none found."""

        summaries, total, has_restrictions = self._get_ranked_model_summaries()
        if not summaries:
            return (
                "No models detected. Configure provider credentials or set DEFAULT_MODEL to a valid option. "
                "If the user requested a specific model, respond with this notice instead of substituting another model."
            )
        display = "; ".join(summaries)
        remainder = total - len(summaries)
        if remainder > 0:
            display = f"{display}; +{remainder} more (use the `listmodels` tool for the full roster)"
        return display

    @staticmethod
    def _format_context_window(tokens: int) -> Optional[str]:
        """Convert a raw context window into a short display string."""

        if not tokens or tokens <= 0:
            return None

        if tokens >= 1_000_000:
            if tokens % 1_000_000 == 0:
                return f"{tokens // 1_000_000}M ctx"
            return f"{tokens / 1_000_000:.1f}M ctx"

        if tokens >= 1_000:
            if tokens % 1_000 == 0:
                return f"{tokens // 1_000}K ctx"
            return f"{tokens / 1_000:.1f}K ctx"

        return f"{tokens} ctx"

    def _collect_ranked_capabilities(self) -> list[tuple[int, str, Any]]:
        """Gather available model capabilities sorted by capability rank."""

        from providers.registry import ModelProviderRegistry

        ranked: list[tuple[int, str, Any]] = []
        available = ModelProviderRegistry.get_available_models(respect_restrictions=True)

        for model_name, provider_type in available.items():
            provider = ModelProviderRegistry.get_provider(provider_type)
            if not provider:
                continue

            try:
                capabilities = provider.get_capabilities(model_name)
            except ValueError:
                continue

            rank = capabilities.get_effective_capability_rank()
            ranked.append((rank, model_name, capabilities))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return ranked

    @staticmethod
    def _normalize_model_identifier(name: str) -> str:
        """Normalize model names for deduplication across providers."""

        normalized = name.lower()
        if ":" in normalized:
            normalized = normalized.split(":", 1)[0]
        if "/" in normalized:
            normalized = normalized.split("/", 1)[-1]
        return normalized

    def _get_ranked_model_summaries(self, limit: int = 5) -> tuple[list[str], int, bool]:
        """Return formatted, ranked model summaries and restriction status."""

        ranked = self._collect_ranked_capabilities()

        # Build allowlist map (provider -> lowercase names) when restrictions are active
        allowed_map: dict[Any, set[str]] = {}
        try:
            from utils.model_restrictions import get_restriction_service

            restriction_service = get_restriction_service()
            if restriction_service:
                from providers.shared import ProviderType

                for provider_type in ProviderType:
                    allowed = restriction_service.get_allowed_models(provider_type)
                    if allowed:
                        allowed_map[provider_type] = {name.lower() for name in allowed if name}
        except Exception:
            allowed_map = {}

        filtered: list[tuple[int, str, Any]] = []
        seen_normalized: set[str] = set()

        for rank, model_name, capabilities in ranked:
            canonical_name = getattr(capabilities, "model_name", model_name)
            canonical_lower = canonical_name.lower()
            alias_lower = model_name.lower()
            provider_type = getattr(capabilities, "provider", None)

            if allowed_map:
                if provider_type not in allowed_map:
                    continue
                allowed_set = allowed_map[provider_type]
                if canonical_lower not in allowed_set and alias_lower not in allowed_set:
                    continue

            normalized = self._normalize_model_identifier(canonical_name)
            if normalized in seen_normalized:
                continue

            seen_normalized.add(normalized)
            filtered.append((rank, canonical_name, capabilities))

        summaries: list[str] = []
        for rank, canonical_name, capabilities in filtered[:limit]:
            details: list[str] = []

            context_str = self._format_context_window(capabilities.context_window)
            if context_str:
                details.append(context_str)

            if capabilities.supports_extended_thinking:
                details.append("thinking")

            if capabilities.allow_code_generation:
                details.append("code-gen")

            base = f"{canonical_name} (score {rank}"
            if details:
                base = f"{base}, {', '.join(details)}"
            summaries.append(f"{base})")

        return summaries, len(filtered), bool(allowed_map)

    def _get_restriction_note(self) -> Optional[str]:
        """Return a string describing active per-provider allowlists, if any."""

        env_labels = {
            "OPENAI_ALLOWED_MODELS": "OpenAI",
            "GOOGLE_ALLOWED_MODELS": "Google",
            "ANTHROPIC_ALLOWED_MODELS": "Anthropic",
            "XAI_ALLOWED_MODELS": "X.AI",
            "OPENROUTER_ALLOWED_MODELS": "OpenRouter",
            "DIAL_ALLOWED_MODELS": "DIAL",
        }

        notes: list[str] = []
        for env_var, label in env_labels.items():
            raw = get_env(env_var)
            if not raw:
                continue

            models = sorted({token.strip() for token in raw.split(",") if token.strip()})
            if not models:
                continue

            notes.append(f"{label}: {', '.join(models)}")

        if not notes:
            return None

        return "Policy allows only → " + "; ".join(notes)

    def _build_model_unavailable_message(self, model_name: str) -> str:
        """Compose a consistent error message for unavailable model scenarios."""

        tool_category = self.get_model_category()
        suggested_model = ModelProviderRegistry.get_preferred_fallback_model(tool_category)
        available_models_text = self._format_available_models_list()

        return (
            f"Model '{model_name}' is not available with current API keys. "
            f"Available models: {available_models_text}. "
            f"Suggested model for {self.get_name()}: '{suggested_model}' "
            f"(category: {tool_category.value}). If the user explicitly requested a model, you MUST use that exact name or report this error back—do not substitute another model."
        )

    def _build_auto_mode_required_message(self) -> str:
        """Compose the auto-mode prompt when an explicit model selection is required."""

        tool_category = self.get_model_category()
        suggested_model = ModelProviderRegistry.get_preferred_fallback_model(tool_category)
        available_models_text = self._format_available_models_list()

        return (
            "Model parameter is required in auto mode. "
            f"Available models: {available_models_text}. "
            f"Suggested model for {self.get_name()}: '{suggested_model}' "
            f"(category: {tool_category.value}). When the user names a model, relay that exact name—never swap in another option."
        )

    def get_model_field_schema(self) -> dict[str, Any]:
        """
        Generate the model field schema based on auto mode configuration.

        When auto mode is enabled, the model parameter becomes required
        and includes detailed descriptions of each model's capabilities.

        Returns:
            Dict containing the model field JSON schema
        """

        from config import DEFAULT_MODEL

        # Use the centralized effective auto mode check
        if self.is_effective_auto_mode():
            description = (
                "Currently in auto model selection mode. CRITICAL: When the user names a model, you MUST use that exact name unless the server rejects it. "
                "If no model is provided, you may use the `listmodels` tool to review options and select an appropriate match. "
                f"{INTENT_MODELS_NOTE}"
            )
            summaries, total, restricted = self._get_ranked_model_summaries()
            remainder = max(0, total - len(summaries))
            if summaries:
                top_line = "; ".join(summaries)
                if remainder > 0:
                    label = "Allowed models" if restricted else "Top models"
                    top_line = f"{label}: {top_line}; +{remainder} more via `listmodels`."
                else:
                    label = "Allowed models" if restricted else "Top models"
                    top_line = f"{label}: {top_line}."
                description = f"{description} {top_line}"

            restriction_note = self._get_restriction_note()
            if restriction_note and (remainder > 0 or not summaries):
                description = f"{description} {restriction_note}."
            return {
                "type": "string",
                "description": description,
            }

        description = (
            f"The default model is '{DEFAULT_MODEL}'. Override only when the user explicitly requests a different model, and use that exact name. "
            "If the requested model fails validation, surface the server error instead of substituting another model. When unsure, use the `listmodels` tool for details. "
            f"{INTENT_MODELS_NOTE}"
        )
        summaries, total, restricted = self._get_ranked_model_summaries()
        remainder = max(0, total - len(summaries))
        if summaries:
            top_line = "; ".join(summaries)
            if remainder > 0:
                label = "Allowed models" if restricted else "Preferred alternatives"
                top_line = f"{label}: {top_line}; +{remainder} more via `listmodels`."
            else:
                label = "Allowed models" if restricted else "Preferred alternatives"
                top_line = f"{label}: {top_line}."
            description = f"{description} {top_line}"

        restriction_note = self._get_restriction_note()
        if restriction_note and (remainder > 0 or not summaries):
            description = f"{description} {restriction_note}."

        return {
            "type": "string",
            "description": description,
        }

    def get_default_temperature(self) -> float:
        """
        Return the default temperature setting for this tool.

        Override this method to set tool-specific temperature defaults.
        Lower values (0.0-0.3) for analytical tasks, higher (0.7-1.0) for creative tasks.

        Returns:
            float: Default temperature between 0.0 and 1.0
        """
        return 0.5

    def wants_line_numbers_by_default(self) -> bool:
        """
        Return whether this tool wants line numbers added to code files by default.

        By default, ALL tools get line numbers for precise code references.
        Line numbers are essential for accurate communication about code locations.

        Returns:
            bool: True if line numbers should be added by default for this tool
        """
        return True  # All tools get line numbers by default for consistency

    def get_default_thinking_mode(self) -> str:
        """
        Return the default thinking mode for this tool.

        Thinking mode controls computational budget for reasoning.
        Override for tools that need more or less reasoning depth.

        Returns:
            str: One of "minimal", "low", "medium", "high", "max"
        """
        return "medium"  # Default to medium thinking for better reasoning

    def get_model_category(self) -> "ToolModelCategory":
        """
        Return the model category for this tool.

        Model category influences which model is selected in auto mode.
        Override to specify whether your tool needs extended reasoning,
        fast response, or balanced capabilities.

        Returns:
            ToolModelCategory: Category that influences model selection
        """
        from tools.models import ToolModelCategory

        return ToolModelCategory.BALANCED

    @abstractmethod
    def get_request_model(self):
        """
        Return the Pydantic model class used for validating requests.

        This model should inherit from ToolRequest and define all
        parameters specific to this tool.

        Returns:
            Type[ToolRequest]: The request model class
        """
        pass

    def validate_file_paths(self, request) -> Optional[str]:
        """
        Validate that all file paths in the request are absolute.

        This is a critical security function that prevents path traversal attacks
        and ensures all file access is properly controlled. All file paths must
        be absolute to avoid ambiguity and security issues.

        Args:
            request: The validated request object

        Returns:
            Optional[str]: Error message if validation fails, None if all paths are valid
        """
        # Only validate files/paths if they exist in the request
        file_fields = [
            "absolute_file_paths",
            "file",
            "path",
            "directory",
            "notebooks",
            "test_examples",
            "style_guide_examples",
            "files_checked",
            "relevant_files",
        ]

        for field_name in file_fields:
            if hasattr(request, field_name):
                field_value = getattr(request, field_name)
                if field_value is None:
                    continue

                # Handle both single paths and lists of paths
                paths_to_check = field_value if isinstance(field_value, list) else [field_value]

                for path in paths_to_check:
                    if path and not os.path.isabs(path):
                        return f"All file paths must be FULL absolute paths. Invalid path: '{path}'"

        return None

    def _validate_token_limit(self, content: str, content_type: str = "Content") -> None:
        """
        Validate that user-provided content doesn't exceed the MCP prompt size limit.

        This enforcement is strictly for text crossing the MCP transport boundary
        (i.e., user input). Internal prompt construction may exceed this size and is
        governed by model-specific token limits.

        Args:
            content: The user-originated content to validate
            content_type: Description of the content type for error messages

        Raises:
            ValueError: If content exceeds the character size limit
        """
        if not content:
            logger.debug(f"{self.name} tool {content_type.lower()} validation skipped (no content)")
            return

        char_count = len(content)
        if char_count > MCP_PROMPT_SIZE_LIMIT:
            token_estimate = estimate_tokens(content)
            error_msg = (
                f"{char_count:,} characters (~{token_estimate:,} tokens). "
                f"Maximum is {MCP_PROMPT_SIZE_LIMIT:,} characters."
            )
            logger.error(f"{self.name} tool {content_type.lower()} validation failed: {error_msg}")
            raise ValueError(f"{content_type} too large: {error_msg}")

        token_estimate = estimate_tokens(content)
        logger.debug(
            f"{self.name} tool {content_type.lower()} validation passed: "
            f"{char_count:,} characters (~{token_estimate:,} tokens)"
        )

    def get_model_provider(self, model_name: str) -> ModelProvider:
        """
        Get the appropriate model provider for the given model name.

        This method performs runtime validation to ensure the requested model
        is actually available with the current API key configuration.

        Args:
            model_name: Name of the model to get provider for

        Returns:
            ModelProvider: The provider instance for the model

        Raises:
            ValueError: If the model is not available or provider not found
        """
        try:
            provider = ModelProviderRegistry.get_provider_for_model(model_name)
            if not provider:
                logger.error(f"No provider found for model '{model_name}' in {self.name} tool")
                raise ValueError(self._build_model_unavailable_message(model_name))

            return provider
        except Exception as e:
            logger.error(f"Failed to get provider for model '{model_name}' in {self.name} tool: {e}")
            raise

    # === CONVERSATION AND FILE HANDLING METHODS ===

    def get_conversation_embedded_files(self, continuation_id: Optional[str]) -> list[str]:
        """
        Get list of files already embedded in conversation history.

        This method returns the list of files that have already been embedded
        in the conversation history for a given continuation thread. Tools can
        use this to avoid re-embedding files that are already available in the
        conversation context.

        Args:
            continuation_id: Thread continuation ID, or None for new conversations

        Returns:
            list[str]: List of file paths already embedded in conversation history
        """
        if not continuation_id:
            # New conversation, no files embedded yet
            return []

        thread_context = get_thread(continuation_id)
        if not thread_context:
            # Thread not found, no files embedded
            return []

        embedded_files = get_conversation_file_list(thread_context)
        logger.debug(f"[FILES] {self.name}: Found {len(embedded_files)} embedded files")
        return embedded_files

    def filter_new_files(self, requested_files: list[str], continuation_id: Optional[str]) -> list[str]:
        """
        Filter out files that are already embedded in conversation history.

        This method prevents duplicate file embeddings by filtering out files that have
        already been embedded in the conversation history. This optimizes token usage
        while ensuring tools still have logical access to all requested files through
        conversation history references.

        Args:
            requested_files: List of files requested for current tool execution
            continuation_id: Thread continuation ID, or None for new conversations

        Returns:
            list[str]: List of files that need to be embedded (not already in history)
        """
        logger.debug(f"[FILES] {self.name}: Filtering {len(requested_files)} requested files")

        if not continuation_id:
            # New conversation, all files are new
            logger.debug(f"[FILES] {self.name}: New conversation, all {len(requested_files)} files are new")
            return requested_files

        try:
            embedded_files = set(self.get_conversation_embedded_files(continuation_id))
            logger.debug(f"[FILES] {self.name}: Found {len(embedded_files)} embedded files in conversation")

            # Safety check: If no files are marked as embedded but we have a continuation_id,
            # this might indicate an issue with conversation history. Be conservative.
            if not embedded_files:
                logger.debug(f"{self.name} tool: No files found in conversation history for thread {continuation_id}")
                logger.debug(
                    f"[FILES] {self.name}: No embedded files found, returning all {len(requested_files)} requested files"
                )
                return requested_files

            # Return only files that haven't been embedded yet
            new_files = [f for f in requested_files if f not in embedded_files]
            logger.debug(
                f"[FILES] {self.name}: After filtering: {len(new_files)} new files, {len(requested_files) - len(new_files)} already embedded"
            )
            logger.debug(f"[FILES] {self.name}: New files to embed: {new_files}")

            # Log filtering results for debugging
            if len(new_files) < len(requested_files):
                skipped = [f for f in requested_files if f in embedded_files]
                logger.debug(
                    f"{self.name} tool: Filtering {len(skipped)} files already in conversation history: {', '.join(skipped)}"
                )
                logger.debug(f"[FILES] {self.name}: Skipped (already embedded): {skipped}")

            return new_files

        except Exception as e:
            # If there's any issue with conversation history lookup, be conservative
            # and include all files rather than risk losing access to needed files
            logger.warning(f"{self.name} tool: Error checking conversation history for {continuation_id}: {e}")
            logger.warning(f"{self.name} tool: Including all requested files as fallback")
            logger.debug(
                f"[FILES] {self.name}: Exception in filter_new_files, returning all {len(requested_files)} files as fallback"
            )
            return requested_files

    def format_conversation_turn(self, turn: ConversationTurn) -> list[str]:
        """
        Format a conversation turn for display in conversation history.

        Tools can override this to provide custom formatting for their responses
        while maintaining the standard structure for cross-tool compatibility.

        This method is called by build_conversation_history when reconstructing
        conversation context, allowing each tool to control how its responses
        appear in subsequent conversation turns.

        Args:
            turn: The conversation turn to format (from utils.conversation_memory)

        Returns:
            list[str]: Lines of formatted content for this turn

        Example:
            Default implementation returns:
            ["Files used in this turn: file1.py, file2.py", "", "Response content..."]

            Tools can override to add custom sections, formatting, or metadata display.
        """
        parts = []

        # Add files context if present
        if turn.files:
            parts.append(f"Files used in this turn: {', '.join(turn.files)}")
            parts.append("")  # Empty line for readability

        # Add the actual content
        parts.append(turn.content)

        return parts

    def handle_prompt_file(self, files: Optional[list[str]]) -> tuple[Optional[str], Optional[list[str]]]:
        """
        Check for and handle prompt.txt in the absolute file paths list.

        If prompt.txt is found, reads its content and removes it from the files list.
        This file is treated specially as the main prompt, not as an embedded file.
        A prompt.txt that holds media or binary content (read_file_content returns a
        MEDIA FILE (NOT ATTACHED) or BINARY FILE placeholder) is not a prompt: it stays in
        the files list, so classify_media can attach it as media or it is reported as binary.

        This mechanism allows us to work around MCP's ~25K token limit by having
        the CLI save large prompts to a file, effectively using the file transfer
        mechanism to bypass token constraints while preserving response capacity.

        Args:
            files: List of absolute file paths (will be translated for current environment)

        Returns:
            tuple: (prompt_content, updated_files_list)
        """
        if not files:
            return None, files

        prompt_content = None
        updated_files = []

        for file_path in files:

            # Check if the filename is exactly "prompt.txt"
            # This ensures we don't match files like "myprompt.txt" or "prompt.txt.bak"
            if os.path.basename(file_path) == "prompt.txt":
                try:
                    # Read prompt.txt content and extract just the text
                    content, _ = read_file_content(file_path)
                    if content.startswith(NOT_TEXT_FILE_HEADERS):
                        # Media or binary content behind the name prompt.txt is not a prompt. Keep it in the
                        # file list so media detection attaches it (or reports it) instead of dropping it.
                        logger.info(f"{self.name}: {file_path} is not a text prompt; keeping it in the file list")
                        updated_files.append(file_path)
                        continue
                    # Extract the content between the file markers
                    if "--- BEGIN FILE:" in content and "--- END FILE:" in content:
                        lines = content.split("\n")
                        in_content = False
                        content_lines = []
                        for line in lines:
                            if line.startswith("--- BEGIN FILE:"):
                                in_content = True
                                continue
                            elif line.startswith("--- END FILE:"):
                                break
                            elif in_content:
                                content_lines.append(line)
                        prompt_content = "\n".join(content_lines)
                    else:
                        # Fallback: if it's already raw content (from tests or direct input)
                        # and doesn't have error markers, use it directly
                        if not content.startswith("\n--- ERROR"):
                            prompt_content = content
                        else:
                            prompt_content = None
                except Exception:
                    # If we can't read the file, we'll just skip it
                    # The error will be handled elsewhere
                    pass
            else:
                # Keep the original path in the files list (will be translated later by read_files)
                updated_files.append(file_path)

        return prompt_content, updated_files if updated_files else None

    def get_prompt_content_for_size_validation(self, user_content: str) -> str:
        """
        Get the content that should be validated for MCP prompt size limits.

        This hook method allows tools to specify what content should be checked
        against the MCP transport size limit. By default, it returns the user content,
        but can be overridden to exclude conversation history when needed.

        Args:
            user_content: The user content that would normally be validated

        Returns:
            The content that should actually be validated for size limits
        """
        # Default implementation: validate the full user content
        return user_content

    def check_prompt_size(self, text: str) -> Optional[dict[str, Any]]:
        """
        Check if USER INPUT text is too large for MCP transport boundary.

        IMPORTANT: This method should ONLY be used to validate user input that crosses
        the CLI ↔ MCP Server transport boundary. It should NOT be used to limit
        internal MCP Server operations.

        Args:
            text: The user input text to check (NOT internal prompt content)

        Returns:
            Optional[Dict[str, Any]]: Response asking for file handling if too large, None otherwise
        """
        if text and len(text) > MCP_PROMPT_SIZE_LIMIT:
            return {
                "status": "resend_prompt",
                "content": (
                    f"MANDATORY ACTION REQUIRED: The prompt is too large for MCP's token limits (>{MCP_PROMPT_SIZE_LIMIT:,} characters). "
                    "YOU MUST IMMEDIATELY save the prompt text to a temporary file named 'prompt.txt' in the working directory. "
                    "DO NOT attempt to shorten or modify the prompt. SAVE IT AS-IS to 'prompt.txt'. "
                    "Then resend the request, passing the absolute file path to 'prompt.txt' as part of the tool call, "
                    "along with any other files you wish to share as context. Leave the prompt text itself empty or very brief in the new request. "
                    "This is the ONLY way to handle large prompts - you MUST follow these exact steps."
                ),
                "content_type": "text",
                "metadata": {
                    "prompt_size": len(text),
                    "limit": MCP_PROMPT_SIZE_LIMIT,
                    "instructions": "MANDATORY: Save prompt to 'prompt.txt' in current folder and provide full path when recalling this tool.",
                },
            }
        return None

    def _prepare_file_content_for_prompt(
        self,
        request_files: list[str],
        continuation_id: Optional[str],
        context_description: str = "New files",
        max_tokens: Optional[int] = None,
        reserve_tokens: int = 1_000,
        remaining_budget: Optional[int] = None,
        arguments: Optional[dict] = None,
        model_context: Optional[Any] = None,
    ) -> tuple[str, list[str]]:
        """
        Centralized file processing implementing dual prioritization strategy.

        This method is the heart of conversation-aware file processing across all tools.

        Args:
            request_files: List of files requested for current tool execution
            continuation_id: Thread continuation ID, or None for new conversations
            context_description: Description for token limit validation (e.g. "Code", "New files")
            max_tokens: Maximum tokens to use (defaults to remaining budget or model-specific content allocation)
            reserve_tokens: Tokens to reserve for additional prompt content (default 1K)
            remaining_budget: Remaining token budget after conversation history (from server.py)
            arguments: Original tool arguments (used to extract _remaining_tokens if available)
            model_context: Model context object with all model information including token allocation

        Returns:
            tuple[str, list[str]]: (formatted_file_content, actually_processed_files)
                - formatted_file_content: Formatted file content string ready for prompt inclusion
                - actually_processed_files: List of individual file paths that were actually read and embedded
                  (directories are expanded to individual files)
        """
        # The media this model call attaches (own plus re-attached earlier media), when the caller planned it
        from utils.media import MediaPlan, classify_media, estimate_media_tokens_for

        plan = getattr(self, "_media_plan", None)
        if not isinstance(plan, MediaPlan):
            plan = None
        if not request_files and not (plan and (plan.attachments or plan.omitted)):
            return "", []

        effective_max_tokens = self._file_token_budget(
            max_tokens=max_tokens,
            reserve_tokens=reserve_tokens,
            remaining_budget=remaining_budget,
            arguments=arguments,
            model_context=model_context,
        )

        # Native media (utils/media.py) is attached to the request by the caller, never read as text.
        # Split it out with the same classification the caller uses, so the prompt announces exactly
        # what is attached, and reserve its estimated tokens before sizing the text-file budget.
        request_files, media = classify_media(request_files)
        if plan is None:
            plan = MediaPlan.own_only(media)
        if plan.attachments:
            media_context = model_context or getattr(self, "_model_context", None)
            effective_max_tokens -= estimate_media_tokens_for(plan.attachments, media_context)

        # Ensure we have a reasonable minimum budget
        effective_max_tokens = max(1000, effective_max_tokens)

        files_to_embed = self.filter_new_files(request_files, continuation_id)
        logger.debug(f"[FILES] {self.name}: Will embed {len(files_to_embed)} files after filtering")

        # Log the specific files for debugging/testing
        if files_to_embed:
            logger.info(
                f"[FILE_PROCESSING] {self.name} tool will embed new files: {', '.join([os.path.basename(f) for f in files_to_embed])}"
            )
        else:
            logger.info(
                f"[FILE_PROCESSING] {self.name} tool: No new files to embed (all files already in conversation history)"
            )

        content_parts = []
        actually_processed_files = []

        # Read content of new files only
        if files_to_embed:
            logger.debug(f"{self.name} tool embedding {len(files_to_embed)} new files: {', '.join(files_to_embed)}")
            logger.debug(
                f"[FILES] {self.name}: Starting file embedding with token budget {effective_max_tokens + reserve_tokens:,}"
            )
            try:
                # Before calling read_files, expand directories to get individual file paths
                from utils.file_utils import expand_paths

                expanded_files = expand_paths(files_to_embed)
                logger.debug(
                    f"[FILES] {self.name}: Expanded {len(files_to_embed)} paths to {len(expanded_files)} individual files"
                )

                file_content = read_files(
                    files_to_embed,
                    max_tokens=effective_max_tokens + reserve_tokens,
                    reserve_tokens=reserve_tokens,
                    include_line_numbers=self.wants_line_numbers_by_default(),
                )
                # Note: No need to validate against MCP_PROMPT_SIZE_LIMIT here
                # read_files already handles token-aware truncation based on model's capabilities
                content_parts.append(file_content)

                # Track the expanded files as actually processed
                actually_processed_files.extend(expanded_files)

                # Estimate tokens for debug logging
                from utils.token_utils import estimate_tokens

                content_tokens = estimate_tokens(file_content)
                logger.debug(
                    f"{self.name} tool successfully embedded {len(files_to_embed)} files ({content_tokens:,} tokens)"
                )
                logger.debug(f"[FILES] {self.name}: Successfully embedded files - {content_tokens:,} tokens used")
                logger.debug(
                    f"[FILES] {self.name}: Actually processed {len(actually_processed_files)} individual files"
                )
            except Exception as e:
                logger.error(f"{self.name} tool failed to embed files {files_to_embed}: {type(e).__name__}: {e}")
                logger.debug(f"[FILES] {self.name}: File embedding failed - {type(e).__name__}: {e}")
                raise
        else:
            logger.debug(f"[FILES] {self.name}: No files to embed after filtering")

        # Generate note about files already in conversation history
        if continuation_id and len(files_to_embed) < len(request_files):
            embedded_files = self.get_conversation_embedded_files(continuation_id)
            skipped_files = [f for f in request_files if f in embedded_files]
            if skipped_files:
                logger.debug(
                    f"{self.name} tool skipping {len(skipped_files)} files already in conversation history: {', '.join(skipped_files)}"
                )
                logger.debug(f"[FILES] {self.name}: Adding note about {len(skipped_files)} skipped files")
                if content_parts:
                    content_parts.append("\n\n")
                note_lines = [
                    "--- NOTE: Additional files referenced in conversation history ---",
                    "The following files are already available in our conversation context:",
                    "\n".join(f"  - {f}" for f in skipped_files),
                    "--- END NOTE ---",
                ]
                content_parts.append("\n".join(note_lines))
            else:
                logger.debug(f"[FILES] {self.name}: No skipped files to note")

        media_section = plan.prompt_section()
        if media_section:
            content_parts.append(media_section)
            actually_processed_files.extend(attachment.path for attachment in media)

        result = "".join(content_parts) if content_parts else ""
        logger.debug(
            f"[FILES] {self.name}: _prepare_file_content_for_prompt returning {len(result)} chars, {len(actually_processed_files)} processed files"
        )
        return result, actually_processed_files

    def _file_token_budget(
        self,
        max_tokens: Optional[int] = None,
        reserve_tokens: int = 1_000,
        remaining_budget: Optional[int] = None,
        arguments: Optional[dict] = None,
        model_context: Optional[Any] = None,
    ) -> int:
        """Tokens this request's files (text and media together) may take, as _prepare_file_content_for_prompt sizes
        them before reserving media: the remaining budget after history (``_remaining_tokens``), else
        ``max_tokens``, else the model's file allocation, each less ``reserve_tokens``. Re-attach trims earlier media
        against this same number (_plan_call_media)."""
        # Extract remaining budget from arguments if available
        if remaining_budget is None:
            # Use provided arguments or fall back to stored arguments from execute()
            args_to_use = arguments or getattr(self, "_current_arguments", {})
            remaining_budget = args_to_use.get("_remaining_tokens")

        # Use remaining budget if provided, otherwise fall back to max_tokens or model-specific default
        if remaining_budget is not None:
            return remaining_budget - reserve_tokens
        if max_tokens is not None:
            return max_tokens - reserve_tokens

        # Use model_context for token allocation
        if not model_context:
            # Try to get from stored attributes as fallback
            model_context = getattr(self, "_model_context", None)
            if not model_context:
                logger.error(
                    f"[FILES] {self.name}: _prepare_file_content_for_prompt called without model_context. "
                    "This indicates an incorrect call sequence in the tool's implementation."
                )
                raise RuntimeError("Model context not provided for file preparation.")

        # This is now the single source of truth for token allocation.
        try:
            token_allocation = model_context.calculate_token_allocation()
            # Standardize on `file_tokens` for consistency and correctness.
            logger.debug(
                f"[FILES] {self.name}: Using model context for {model_context.model_name}: "
                f"{token_allocation.file_tokens:,} file tokens from {token_allocation.total_tokens:,} total"
            )
            return token_allocation.file_tokens - reserve_tokens
        except Exception as e:
            logger.error(
                f"[FILES] {self.name}: Failed to calculate token allocation from model context: {e}", exc_info=True
            )
            # If the context exists but calculation fails, we still need to prevent a crash.
            # A loud error is logged, and we fall back to a safe default.
            return 100_000 - reserve_tokens

    def get_websearch_instruction(self, tool_specific: Optional[str] = None) -> str:
        """
        Generate standardized web search instruction.

        Args:
            tool_specific: Optional tool-specific search guidance

        Returns:
            str: Web search instruction to append to prompt
        """

        base_instruction = """

WEB SEARCH CAPABILITY: You can request the calling agent to perform web searches to enhance your analysis with current information!

IMPORTANT: When you identify areas where web searches would significantly improve your response (such as checking current documentation, finding recent solutions, verifying best practices, or gathering community insights), you MUST explicitly instruct the agent to perform specific web searches and then respond back using the continuation_id from this response to continue the analysis.

Use clear, direct language based on the value of the search:

For valuable supplementary information: "Please perform a web search on '[specific topic/query]' and then continue this analysis using the continuation_id from this response if you find relevant information."

For important missing information: "Please search for '[specific topic/query]' and respond back with the findings using the continuation_id from this response - this information is needed to provide a complete analysis."

For critical/essential information: "SEARCH REQUIRED: Please immediately perform a web search on '[specific topic/query]' and respond back with the results using the continuation_id from this response. Cannot provide accurate analysis without this current information."

This ensures you get the most current and comprehensive information while maintaining conversation context through the continuation_id."""

        if tool_specific:
            return f"""{base_instruction}

{tool_specific}

When recommending searches, be specific about what information you need and why it would improve your analysis."""

        # Default instruction for all tools
        return f"""{base_instruction}

Consider requesting searches for:
- Current documentation and API references
- Recent best practices and patterns
- Known issues and community solutions
- Framework updates and compatibility
- Security advisories and patches
- Performance benchmarks and optimizations

When recommending searches, be specific about what information you need and why it would improve your analysis. Always remember to instruct agent to use the continuation_id from this response when providing search results."""

    def get_language_instruction(self) -> str:
        """
        Generate language instruction based on LOCALE configuration.

        Returns:
            str: Language instruction to prepend to prompt, or empty string if
                 no locale set
        """
        # Read LOCALE directly from environment to support dynamic changes
        # Tests can monkeypatch LOCALE via the environment helper (or .env when override is enforced)

        locale = (get_env("LOCALE", "") or "").strip()

        if not locale:
            return ""

        # Simple language instruction
        return f"Always respond in {locale}.\n\n"

    # === ABSTRACT METHODS FOR SIMPLE TOOLS ===

    @abstractmethod
    async def prepare_prompt(self, request) -> str:
        """
        Prepare the complete prompt for the AI model.

        This method should construct the full prompt by combining:
        - System prompt from get_system_prompt()
        - File content from _prepare_file_content_for_prompt()
        - Conversation history from reconstruct_thread_context()
        - User's request and any tool-specific context

        Args:
            request: The validated request object

        Returns:
            str: Complete prompt ready for the AI model
        """
        pass

    def format_response(self, response: str, request, model_info: dict = None) -> str:
        """
        Format the AI model's response for the user.

        This method allows tools to post-process the model's response,
        adding structure, validation, or additional context.

        The default implementation returns the response unchanged.
        Tools can override this method to add custom formatting.

        Args:
            response: Raw response from the AI model
            request: The original request object
            model_info: Optional model information and metadata

        Returns:
            str: Formatted response ready for the user
        """
        return response

    # === IMPLEMENTATION METHODS ===
    # These will be provided in a full implementation but are inherited from current base.py
    # for now to maintain compatibility.

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Execute the tool - will be inherited from existing base.py for now."""
        # This will be implemented by importing from the current base.py
        # for backward compatibility during the migration
        raise NotImplementedError("Subclasses must implement execute method")

    def _should_require_model_selection(self, model_name: str) -> bool:
        """
        Check if we should require the CLI to select a model at runtime.

        This is called during request execution to determine if we need
        to return an error asking the CLI to provide a model parameter.

        Args:
            model_name: The model name from the request or DEFAULT_MODEL

        Returns:
            bool: True if we should require model selection
        """
        # NOTE: Auto mode is now handled by _resolve_model_context() before this check.
        # If "auto" reaches here, it indicates a code path that bypassed resolution.
        if model_name.lower() == "auto":
            logger.error(
                f"Auto mode reached validation without resolution in {self.name} tool. "
                "This indicates a code path that bypassed model resolution."
            )
            return True

        # Check if requested model is available
        from providers.registry import ModelProviderRegistry

        provider = ModelProviderRegistry.get_provider_for_model(model_name)
        if not provider:
            logger.warning(f"Model '{model_name}' is not available with current API keys.")
            return True

        return False

    def _get_available_models(self) -> list[str]:
        """
        Get list of models available from enabled providers.

        Only returns models from providers that have valid API keys configured.
        This fixes the namespace collision bug where models from disabled providers
        were shown to the CLI, causing routing conflicts.

        Returns:
            List of model names from enabled providers only
        """
        from providers.registry import ModelProviderRegistry

        # Get models from enabled providers only (those with valid API keys)
        all_models = ModelProviderRegistry.get_available_model_names()

        # Add OpenRouter models and their aliases when OpenRouter is configured
        openrouter_key = get_env("OPENROUTER_API_KEY")
        if openrouter_key and openrouter_key != "your_openrouter_api_key_here":
            try:
                registry = self._get_openrouter_registry()

                for alias in registry.list_aliases():
                    if alias not in all_models:
                        all_models.append(alias)
            except Exception as exc:  # pragma: no cover - logged for observability
                import logging

                logging.debug(f"Failed to add OpenRouter models to enum: {exc}")

        # Add custom models (and their aliases) when a custom endpoint is available
        custom_url = get_env("CUSTOM_API_URL")
        if custom_url:
            try:
                registry = self._get_custom_registry()
                for alias in registry.list_aliases():
                    if alias not in all_models:
                        all_models.append(alias)
            except Exception as exc:  # pragma: no cover - logged for observability
                import logging

                logging.debug(f"Failed to add custom models to enum: {exc}")

        # Remove duplicates while preserving insertion order
        seen: set[str] = set()
        unique_models: list[str] = []
        for model in all_models:
            if model not in seen:
                seen.add(model)
                unique_models.append(model)

        return unique_models

    def _resolve_model_context(self, arguments: dict, request) -> tuple[str, Any]:
        """
        Resolve model context and name using centralized logic.

        This method extracts the model resolution logic from execute() so it can be
        reused by tools that override execute() (like debug tool) without duplicating code.

        Args:
            arguments: Dictionary of arguments from the MCP client
            request: The validated request object

        Returns:
            tuple[str, ModelContext]: (resolved_model_name, model_context)

        Raises:
            ValueError: If model resolution fails or model selection is required
        """
        # MODEL RESOLUTION NOW HAPPENS AT MCP BOUNDARY
        # Extract pre-resolved model context from server.py
        model_context = arguments.get("_model_context")
        resolved_model_name = arguments.get("_resolved_model_name")

        if model_context and resolved_model_name:
            # Model was already resolved at MCP boundary
            model_name = resolved_model_name
            logger.debug(f"Using pre-resolved model '{model_name}' from MCP boundary")
        else:
            # Fallback for direct execute calls (CLI mode)
            model_name = getattr(request, "model", None)
            if not model_name:
                from config import DEFAULT_MODEL

                model_name = DEFAULT_MODEL
            logger.debug(f"Using fallback model resolution for '{model_name}' (CLI mode)")

            # Resolve 'auto' or an intent word ('frontier', 'balanced', 'fast'). Any other name is a model and is
            # used exactly as named: it never reaches the resolver.
            if ModelProviderRegistry.is_model_intent(model_name):
                from utils.media import media_kinds_from_arguments

                intent = model_name.strip().lower()
                tool_category = self.get_model_category()
                # Route on attached media, the thread's earlier media included: a follow-up re-attaches it
                # (_plan_call_media), and explicit-only providers must never get it unnamed. Raises
                # MediaNotSupportedError (a ValueError) if no model takes it.
                required_media = media_kinds_from_arguments(arguments)
                continuation_id = arguments.get("continuation_id")
                thread = get_thread(continuation_id) if continuation_id else None
                if thread is not None:
                    required_media |= get_conversation_media_kinds(thread)
                model_name = ModelProviderRegistry.resolve_model_intent(
                    intent, tool_category, required_media=required_media
                )
                logger.info(
                    f"{intent} resolved to '{model_name}' for {self.get_name()} tool (category: {tool_category.value})"
                )

            # Check if model is available
            if self._should_require_model_selection(model_name):
                # Build error message for unavailable model
                error_message = self._build_model_unavailable_message(model_name)
                raise ValueError(error_message)

            # Create model context for CLI mode
            from utils.model_context import ModelContext

            model_context = ModelContext(model_name)

        return model_name, model_context

    def validate_and_correct_temperature(self, temperature: float, model_context: Any) -> tuple[float, list[str]]:
        """
        Validate and correct temperature for the specified model.

        This method ensures that the temperature value is within the valid range
        for the specific model being used. Different models have different temperature
        constraints (e.g., o1 models require temperature=1.0, GPT models support 0-2).

        Args:
            temperature: Temperature value to validate
            model_context: Model context object containing model name, provider, and capabilities

        Returns:
            Tuple of (corrected_temperature, warning_messages)
        """
        try:
            # Use model context capabilities directly - clean OOP approach
            capabilities = model_context.capabilities
            constraint = capabilities.temperature_constraint

            warnings = []
            if not constraint.validate(temperature):
                corrected = constraint.get_corrected_value(temperature)
                warning = (
                    f"Temperature {temperature} invalid for {model_context.model_name}. "
                    f"{constraint.get_description()}. Using {corrected} instead."
                )
                warnings.append(warning)
                return corrected, warnings

            return temperature, warnings

        except Exception as e:
            # If validation fails for any reason, use the original temperature
            # and log a warning (but don't fail the request)
            logger.warning(f"Temperature validation failed for {model_context.model_name}: {e}")
            return temperature, [f"Temperature validation failed: {e}"]

    def _media_from_paths(self, paths) -> list:
        """Media attachments (utils.media.MediaAttachment) among explicit file paths."""
        from utils.media import classify_media

        return classify_media(paths)[1]

    def _validate_media_support(self, media: list, model_context: Any) -> None:
        """Fail fast unless every attachment is within size limits and the model's flags AND its
        provider's encoder cover it. For the media a call names itself: earlier turns' media the model
        cannot take is left out with a note instead (_plan_call_media)."""
        if not media:
            return
        from providers.registry import ModelProviderRegistry
        from tools.models import ToolOutput
        from tools.shared.exceptions import ToolExecutionError
        from utils.media import MediaNotSupportedError, check_media_sizes, format_media_error, required_kinds

        metadata = {"tool_name": self.get_name(), "model": model_context.model_name}
        try:
            check_media_sizes(media)
        except MediaNotSupportedError as exc:
            output = ToolOutput(status="error", content=str(exc), content_type="text", metadata=metadata)
            raise ToolExecutionError(output.model_dump_json()) from exc

        required = required_kinds(media)
        supported = model_context.capabilities.supported_media_kinds() & frozenset(model_context.provider.MEDIA_KINDS)
        missing = required - supported
        if not missing:
            return
        capable = ModelProviderRegistry.find_media_capable_models(required)
        content = format_media_error(model_context.model_name, missing, media, capable)
        metadata.update({"missing_media": sorted(kind.value for kind in missing), "capable_models": capable})
        output = ToolOutput(status="error", content=content, content_type="text", metadata=metadata)
        raise ToolExecutionError(output.model_dump_json())

    def _plan_call_media(
        self,
        own_media: list,
        continuation_id: Optional[str],
        model_context: Any,
        budget_tokens: Optional[int],
        own_text_files: Optional[list[str]] = None,
        request_text_bytes: Optional[int] = None,
    ):
        """What one model call attaches (utils.media.MediaPlan): ``own_media`` (already validated), plus the media
        earlier turns of the thread attached (re-attach), in first-seen order.

        Earlier media is left out, with a note for the prompt, when its file is gone, the model or its provider's
        encoder cannot take its kind, or it does not fit the provider's inline request size or the token budget,
        oldest first. ``budget_tokens`` is the number the call's file embedding sizes text and media with (the
        tool's file budget, net of read_files' reserve). ``own_text_files`` are the files that embedding reads as
        text: the call's own files come first, so earlier media gets only what their estimated tokens leave
        (floor 0). Simple tools pass none: over MCP their text is already in the history, which ``_remaining_tokens``
        is net of. ``request_text_bytes``: the prompt and system prompt's size when the caller knows it, for the
        headroom left under a provider's inline request cap (utils.media.inline_media_allowance). Without earlier
        media the plan is ``own_media`` as is, so first turns are unchanged and nothing is read twice.
        """
        from utils.media import MediaPlan, classify_media, plan_media

        thread = get_thread(continuation_id) if continuation_id else None
        earlier = get_conversation_media_list(thread) if thread is not None else []
        if not earlier:
            return MediaPlan.own_only(own_media)
        if budget_tokens is not None and own_text_files:
            from utils.file_utils import estimate_text_files_tokens

            own_text = estimate_text_files_tokens(
                classify_media(list(own_text_files))[0],
                include_line_numbers=self.wants_line_numbers_by_default(),
                limit=budget_tokens,
            )
            budget_tokens = max(0, budget_tokens - own_text)
        provider = model_context.provider
        supported = model_context.capabilities.supported_media_kinds() & frozenset(provider.MEDIA_KINDS)
        max_request_bytes = getattr(provider, "MEDIA_REQUEST_MAX_BYTES", None)
        if not isinstance(max_request_bytes, int) or isinstance(max_request_bytes, bool):
            max_request_bytes = None
        return plan_media(
            own_media,
            earlier,
            get_conversation_media_first_seen(thread),
            supported=supported,
            model_name=model_context.model_name,
            budget_tokens=budget_tokens,
            model_context=model_context,
            max_request_bytes=max_request_bytes,
            request_text_bytes=request_text_bytes,
        )

    def _validate_image_limits(
        self, images: Optional[list[str]], model_context: Optional[Any] = None, continuation_id: Optional[str] = None
    ) -> Optional[dict]:
        """
        Validate image size and count against model capabilities.

        This performs strict validation to ensure we don't exceed model-specific
        image limits. Uses capability-based validation with actual model
        configuration rather than hard-coded limits.

        Args:
            images: List of image paths/data URLs to validate
            model_context: Model context object containing model name, provider, and capabilities
            continuation_id: Optional continuation ID for conversation context

        Returns:
            Optional[dict]: Error response if validation fails, None if valid
        """
        if not images:
            return None

        # Import here to avoid circular imports
        import base64
        from pathlib import Path

        if not model_context:
            # Get from tool's stored context as fallback
            model_context = getattr(self, "_model_context", None)
            if not model_context:
                logger.warning("No model context available for image validation")
                return None

        try:
            # Use model context capabilities directly - clean OOP approach
            capabilities = model_context.capabilities
            model_name = model_context.model_name
        except Exception as e:
            logger.warning(f"Failed to get capabilities from model_context for image validation: {e}")
            # Generic error response when capabilities cannot be accessed
            model_name = getattr(model_context, "model_name", "unknown")
            return {
                "status": "error",
                "content": self._build_model_unavailable_message(model_name),
                "content_type": "text",
                "metadata": {
                    "error_type": "validation_error",
                    "model_name": model_name,
                    "supports_images": None,  # Unknown since model capabilities unavailable
                    "image_count": len(images) if images else 0,
                },
            }

        # Check if model supports images
        if not capabilities.supports_images:
            return {
                "status": "error",
                "content": (
                    f"Image support not available: Model '{model_name}' does not support image processing. "
                    f"Please use a vision-capable model such as 'flash', 'sol', "
                    f"or 'opus' for image analysis tasks."
                ),
                "content_type": "text",
                "metadata": {
                    "error_type": "validation_error",
                    "model_name": model_name,
                    "supports_images": False,
                    "image_count": len(images),
                },
            }

        # Get model image limits from capabilities
        max_images = 5  # Default max number of images
        max_size_mb = capabilities.max_image_size_mb

        # Check image count
        if len(images) > max_images:
            return {
                "status": "error",
                "content": (
                    f"Too many images: Model '{model_name}' supports a maximum of {max_images} images, "
                    f"but {len(images)} were provided. Please reduce the number of images."
                ),
                "content_type": "text",
                "metadata": {
                    "error_type": "validation_error",
                    "model_name": model_name,
                    "image_count": len(images),
                    "max_images": max_images,
                },
            }

        # Calculate total size of all images
        total_size_mb = 0.0
        for image_path in images:
            try:
                if image_path.startswith("data:image/"):
                    # Handle data URL: data:image/png;base64,iVBORw0...
                    _, data = image_path.split(",", 1)
                    # Base64 encoding increases size by ~33%, so decode to get actual size
                    actual_size = len(base64.b64decode(data))
                    total_size_mb += actual_size / (1024 * 1024)
                else:
                    # Handle file path
                    path = Path(image_path)
                    if path.exists():
                        file_size = path.stat().st_size
                        total_size_mb += file_size / (1024 * 1024)
                    else:
                        logger.warning(f"Image file not found: {image_path}")
                        # Assume a reasonable size for missing files to avoid breaking validation
                        total_size_mb += 1.0  # 1MB assumption
            except Exception as e:
                logger.warning(f"Failed to get size for image {image_path}: {e}")
                # Assume a reasonable size for problematic files
                total_size_mb += 1.0  # 1MB assumption

        # Apply 40MB cap for custom models if needed
        effective_limit_mb = max_size_mb
        try:
            from providers.shared import ProviderType

            # ModelCapabilities dataclass has provider field defined
            if capabilities.provider == ProviderType.CUSTOM:
                effective_limit_mb = min(max_size_mb, 40.0)
        except Exception:
            pass

        # Validate against size limit
        if total_size_mb > effective_limit_mb:
            return {
                "status": "error",
                "content": (
                    f"Image size limit exceeded: Model '{model_name}' supports maximum {effective_limit_mb:.1f}MB "
                    f"for all images combined, but {total_size_mb:.1f}MB was provided. "
                    f"Please reduce image sizes or count and try again."
                ),
                "content_type": "text",
                "metadata": {
                    "error_type": "validation_error",
                    "model_name": model_name,
                    "total_size_mb": round(total_size_mb, 2),
                    "limit_mb": round(effective_limit_mb, 2),
                    "image_count": len(images),
                    "supports_images": True,
                },
            }

        # All validations passed
        logger.debug(f"Image validation passed: {len(images)} images, {total_size_mb:.1f}MB total")
        return None

    def _parse_response(self, raw_text: str, request, model_info: Optional[dict] = None):
        """Parse response - will be inherited for now."""
        # Implementation inherited from current base.py
        raise NotImplementedError("Subclasses must implement _parse_response method")
