"""OpenRouter provider implementation."""

import logging
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from utils.env import get_env
from utils.media import MediaKind

from .openai_compatible import OpenAICompatibleProvider
from .registries.openrouter import OpenRouterModelRegistry
from .shared import (
    ModelCapabilities,
    ProviderType,
    RangeTemperatureConstraint,
)

if TYPE_CHECKING:
    from tools.models import ToolModelCategory


# The text part that carries Claude's prompt-cache breakpoint right after the last file part of an anthropic/* media
# request. OpenRouter's chat schema takes cache_control on text parts only, so the breakpoint needs a text part of its
# own before the changing prompt text. Fixed, so it caches with the files on every turn.
CLAUDE_CACHE_BREAKPOINT_TEXT = "The attached files end here."


class OpenRouterParsedMediaError(RuntimeError):
    """OpenRouter turned an attached file into text instead of passing it to the model natively. Never retried."""


def _field(obj: Any, name: str) -> Any:
    """``obj[name]`` for a dict, else the attribute, else the openai SDK model's extra field; None when absent.

    OpenRouter's own response fields (``openrouter_metadata``, file annotations) reach the SDK's models as extras.
    """
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    value = getattr(obj, name, None)
    if value is None:
        extra = getattr(obj, "model_extra", None)
        if isinstance(extra, dict):
            value = extra.get(name)
    return value


def _items(value: Any) -> list:
    """``value`` if it is a list or tuple, else no items (absent, None, or a test double)."""
    return list(value) if isinstance(value, (list, tuple)) else []


class OpenRouterProvider(OpenAICompatibleProvider):
    """Client for OpenRouter's multi-model aggregation service.

    Role
        Surface OpenRouter’s dynamic catalogue through the same interface as
        native providers so tools can reference OpenRouter models and aliases
        without special cases.

    Characteristics
        * Pulls live model definitions from :class:`OpenRouterModelRegistry`
          (aliases, provider-specific metadata, capability hints)
        * Applies alias-aware restriction checks before exposing models to the
          registry or tooling
        * Reuses :class:`OpenAICompatibleProvider` infrastructure for request
          execution so OpenRouter endpoints behave like standard OpenAI-style
          APIs.
    """

    FRIENDLY_NAME = "OpenRouter"

    # PDF as `file` parts, audio as `input_audio`, video as `video_url` (Responses API: input_file, input_audio,
    # input_video). Which model takes which kind is per model: its supports_pdf/audio/video flags, set only after a
    # live probe through this provider. Requests ask for the native PDF engine and refuse a parsed response
    # (_check_media_response). No x-ai/* model is flagged, so Grok never gets media through OpenRouter.
    MEDIA_KINDS = frozenset(MediaKind)
    # Counted base64-encoded. OpenRouter documents no inline limit; 32 MB is the smallest upstream request body limit
    # (Anthropic's), so it holds whichever upstream serves the request.
    MEDIA_REQUEST_MAX_BYTES = 32_000_000
    # The highest native provider rate (OpenAI's gpt-6 models); per-model rates in conf/openrouter_models.json.
    PDF_TOKENS_PER_PAGE = 4_000

    # Custom headers required by OpenRouter
    DEFAULT_HEADERS = {
        "HTTP-Referer": get_env("OPENROUTER_REFERER", "https://github.com/BeehiveInnovations/zen-mcp-server")
        or "https://github.com/BeehiveInnovations/zen-mcp-server",
        "X-Title": get_env("OPENROUTER_TITLE", "Zen MCP Server") or "Zen MCP Server",
    }

    # Model registry for managing configurations and aliases
    _registry: OpenRouterModelRegistry | None = None

    # Auto-mode picks per tool category (ToolModelCategory value), first allowed wins. They mirror the native
    # providers' first choices, interleaving vendors, with ids exactly as in conf/openrouter_models.json. With none
    # of a list allowed, the registry ranks the allowed models instead (ModelProviderRegistry._pick_by_rank).
    PREFERRED_MODELS: ClassVar[dict[str, tuple[str, ...]]] = {
        "extended_reasoning": (
            "openai/gpt-6-astra",
            "anthropic/claude-fable-5.1",
            "google/gemini-3.1-pro-preview",
            "x-ai/grok-4.7",
            "anthropic/claude-opus-5.5",
            "openai/gpt-6-sol",
        ),
        "balanced": (
            "openai/gpt-6-sol",
            "anthropic/claude-sonnet-5.5",
            "google/gemini-3.1-pro-preview",
            "x-ai/grok-4.7",
            "openai/gpt-5.6-sol",
        ),
        "fast_response": (
            "openai/gpt-6-luna",
            "google/gemini-3.5-flash",
            "anthropic/claude-sonnet-5.5",
            "x-ai/grok-4.6",
            "google/gemini-3.6-flash",
        ),
    }

    def __init__(self, api_key: str, **kwargs):
        """Initialize OpenRouter provider.

        Args:
            api_key: OpenRouter API key
            **kwargs: Additional configuration
        """
        base_url = "https://openrouter.ai/api/v1"
        self._alias_cache: dict[str, str] = {}
        super().__init__(api_key, base_url=base_url, **kwargs)

        # Initialize model registry
        if OpenRouterProvider._registry is None:
            OpenRouterProvider._registry = OpenRouterModelRegistry()
            # Log loaded models and aliases only on first load
            models = self._registry.list_models()
            aliases = self._registry.list_aliases()
            logging.info(f"OpenRouter loaded {len(models)} models with {len(aliases)} aliases")

    # ------------------------------------------------------------------
    # Capability surface
    # ------------------------------------------------------------------

    def _lookup_capabilities(
        self,
        canonical_name: str,
        requested_name: str | None = None,
    ) -> ModelCapabilities | None:
        """Fetch OpenRouter capabilities from the registry or build a generic fallback."""

        capabilities = self._registry.get_capabilities(canonical_name)
        if capabilities:
            return capabilities

        base_identifier = canonical_name.split(":", 1)[0]
        if "/" in base_identifier:
            logging.debug(
                "Using generic OpenRouter capabilities for %s (provider/model format detected)", canonical_name
            )
            generic = ModelCapabilities(
                provider=ProviderType.OPENROUTER,
                model_name=canonical_name,
                friendly_name=self.FRIENDLY_NAME,
                intelligence_score=9,
                context_window=32_768,
                max_output_tokens=32_768,
                supports_extended_thinking=False,
                supports_system_prompts=True,
                supports_streaming=True,
                supports_function_calling=False,
                temperature_constraint=RangeTemperatureConstraint(0.0, 2.0, 1.0),
            )
            generic._is_generic = True
            return generic

        logging.debug(
            "Rejecting unknown OpenRouter model '%s' (no provider prefix); requires explicit configuration",
            canonical_name,
        )
        return None

    # ------------------------------------------------------------------
    # Media: native reading only
    # ------------------------------------------------------------------

    def _media_prefix_parts(self, model_name: str, media_parts: list[dict], responses_api: bool) -> list[dict]:
        """For an anthropic/* model on Chat Completions, a fixed text part carrying Claude's cache breakpoint follows
        the last media part, so the system prompt and the files are cached and the prompt text after them is not.

        OpenRouter's chat schema takes ``cache_control`` on text parts only. Other models cache prefixes on their own.
        """
        if responses_api or not model_name.lower().startswith("anthropic/"):
            return media_parts
        breakpoint_part = {"type": "text", "text": CLAUDE_CACHE_BREAKPOINT_TEXT, "cache_control": {"type": "ephemeral"}}
        return [*media_parts, breakpoint_part]

    def _media_request_options(self, media: list) -> dict[str, dict]:
        """The router-metadata header for any media; the native PDF engine when a PDF is attached.

        - ``X-OpenRouter-Metadata: enabled`` adds ``openrouter_metadata`` to the response, whose pipeline shows a
          file-parser stage when parsing ran.
        - The file-parser plugin set to the native engine: without it, a model that cannot read PDFs itself gets
          them parsed (mistral-ocr by default) and answers from extracted text.
        - No provider pinning (``provider.order``): the parse check guards correctness, and pinning would cut
          availability.

        The client's attribution headers (DEFAULT_HEADERS) stay: the SDK merges extra_headers into them.
        """
        options: dict[str, dict] = {"extra_headers": {"X-OpenRouter-Metadata": "enabled"}}
        if any(attachment.kind == MediaKind.PDF for attachment in media):
            options["extra_body"] = {"plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}]}
        return options

    def _check_media_response(self, response, model_name: str, media_attached: list[dict]) -> None:
        """Raise OpenRouterParsedMediaError when OpenRouter parsed a file into text instead of passing it natively.

        Parsed responses carry file annotations (``type: "file"``) on the message (Chat Completions) or on an output
        text part (Responses API), and router metadata whose pipeline has a parser stage. Native responses carry
        neither; absent fields mean native. The request is not retried, with or without the media.
        """
        parsed_names = self._parsed_file_names(response)
        if parsed_names is None:
            return
        names = (
            parsed_names
            or [record["name"] for record in media_attached if record.get("kind") == MediaKind.PDF.value]
            or [record["name"] for record in media_attached]
        )
        raise OpenRouterParsedMediaError(
            f"OpenRouter parsed {', '.join(names)} into text instead of passing it to {model_name} natively; "
            "zen only sends media to models that read it themselves."
        )

    @staticmethod
    def _parsed_file_names(response) -> Optional[list[str]]:
        """None when the response shows no parsing; else the parsed files' names (empty when none is named)."""
        annotations = [
            annotation
            for choice in _items(_field(response, "choices"))
            for annotation in _items(_field(_field(choice, "message"), "annotations"))
        ] + [
            annotation
            for item in _items(_field(response, "output"))
            for part in _items(_field(item, "content"))
            for annotation in _items(_field(part, "annotations"))
        ]
        # Chat Completions marks a parsed file with a "file" annotation; /responses with a "file_citation" one
        # (live, 2026-10-04: the cloudflare-ai engine left no other trace). Native replies carry neither.
        file_annotations = [
            annotation for annotation in annotations if _field(annotation, "type") in ("file", "file_citation")
        ]
        pipeline = _items(_field(_field(response, "openrouter_metadata"), "pipeline"))
        parser_ran = any(
            isinstance(_field(stage, "name"), str) and "parser" in _field(stage, "name").lower() for stage in pipeline
        )
        if not file_annotations and not parser_ran:
            return None
        names = [
            _field(_field(annotation, "file"), "name") or _field(annotation, "filename")
            for annotation in file_annotations
        ]
        return list(dict.fromkeys(name for name in names if isinstance(name, str) and name))

    def _is_error_retryable(self, error: Exception) -> bool:
        """A parsed response is final: resending the file would only be parsed (and billed) again."""
        if isinstance(error, OpenRouterParsedMediaError):
            return False
        return super()._is_error_retryable(error)

    # ------------------------------------------------------------------
    # Provider identity
    # ------------------------------------------------------------------

    def get_provider_type(self) -> ProviderType:
        """Identify this provider for restrictions and logging."""
        return ProviderType.OPENROUTER

    def get_preferred_model(self, category: "ToolModelCategory", allowed_models: list[str]) -> Optional[str]:
        """The first id on this category's PREFERRED_MODELS list that is allowed; None when none is.

        allowed_models mixes aliases and canonical ids, so it is compared as canonical ids. None hands the pick to
        the registry's rank-based fallback. The registry asks only the first provider with allowed models, so this
        never beats Custom, Azure or DIAL.
        """
        allowed = {self._resolve_model_name(name) for name in allowed_models}
        for model_name in self.PREFERRED_MODELS.get(category.value, ()):
            if model_name in allowed:
                return model_name
        return None

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    def list_models(
        self,
        *,
        respect_restrictions: bool = True,
        include_aliases: bool = True,
        lowercase: bool = False,
        unique: bool = False,
    ) -> list[str]:
        """Return formatted OpenRouter model names, respecting alias-aware restrictions."""

        if not self._registry:
            return []

        from utils.model_restrictions import get_restriction_service

        restriction_service = get_restriction_service() if respect_restrictions else None
        allowed_configs: dict[str, ModelCapabilities] = {}

        for model_name in self._registry.list_models():
            config = self._registry.resolve(model_name)
            if not config:
                continue

            # Custom models belong to CustomProvider; skip them here so the two
            # providers don't race over the same registrations (important for tests
            # that stub the registry with minimal objects lacking attrs).
            if config.provider == ProviderType.CUSTOM:
                continue

            if restriction_service:
                allowed = restriction_service.is_allowed(self.get_provider_type(), model_name)

                if not allowed and config.aliases:
                    for alias in config.aliases:
                        if restriction_service.is_allowed(self.get_provider_type(), alias):
                            allowed = True
                            break

                if not allowed:
                    continue

            allowed_configs[model_name] = config

        if not allowed_configs:
            return []

        # When restrictions are in place, don't include aliases to avoid confusion
        # Only return the canonical model names that are actually allowed
        actual_include_aliases = include_aliases and not respect_restrictions

        return ModelCapabilities.collect_model_names(
            allowed_configs,
            include_aliases=actual_include_aliases,
            lowercase=lowercase,
            unique=unique,
        )

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    def _resolve_model_name(self, model_name: str) -> str:
        """Resolve aliases defined in the OpenRouter registry."""

        cache_key = model_name.lower()
        if cache_key in self._alias_cache:
            return self._alias_cache[cache_key]

        config = self._registry.resolve(model_name)
        if config:
            if config.model_name != model_name:
                logging.debug("Resolved model alias '%s' to '%s'", model_name, config.model_name)
            resolved = config.model_name
            self._alias_cache[cache_key] = resolved
            self._alias_cache.setdefault(resolved.lower(), resolved)
            return resolved

        logging.debug(f"Model '{model_name}' not found in registry, using as-is")
        self._alias_cache[cache_key] = model_name
        return model_name

    def get_all_model_capabilities(self) -> dict[str, ModelCapabilities]:
        """Expose registry-backed OpenRouter capabilities."""

        if not self._registry:
            return {}

        capabilities: dict[str, ModelCapabilities] = {}
        for model_name in self._registry.list_models():
            config = self._registry.resolve(model_name)
            if not config:
                continue

            # See note in list_models: respect the CustomProvider boundary.
            if config.provider == ProviderType.CUSTOM:
                continue

            capabilities[model_name] = config
        return capabilities
