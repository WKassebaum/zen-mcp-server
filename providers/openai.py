"""OpenAI model provider implementation."""

import logging
from typing import TYPE_CHECKING, ClassVar, Optional

if TYPE_CHECKING:
    from tools.models import ToolModelCategory

from utils.media import MediaKind

from .openai_compatible import OpenAICompatibleProvider
from .registries.openai import OpenAIModelRegistry
from .registry_provider_mixin import RegistryBackedProviderMixin
from .shared import ModelCapabilities, ProviderType

logger = logging.getLogger(__name__)


class OpenAIModelProvider(RegistryBackedProviderMixin, OpenAICompatibleProvider):
    """Implementation that talks to api.openai.com using rich model metadata.

    In addition to the built-in catalogue, the provider can surface models
    defined in ``conf/custom_models.json`` (for organisations running their own
    OpenAI-compatible gateways) while still respecting restriction policies.
    """

    REGISTRY_CLASS = OpenAIModelRegistry
    MODEL_CAPABILITIES: ClassVar[dict[str, ModelCapabilities]] = {}
    # The media encoder lives in OpenAICompatibleProvider; only this subclass, xAI and OpenRouter opt in, so
    # Azure, DIAL and Custom keep refusing media through ensure_media_encodable.
    MEDIA_KINDS = frozenset({MediaKind.PDF})
    # OpenAI accepts up to 50 MB of file input per request; counted base64-encoded to stay on the safe side.
    MEDIA_REQUEST_MAX_BYTES = 50_000_000
    # Extracted text plus a page image per page. Measured 2026-10-03 on a letter-size scanned page: gpt-6-luna and
    # gpt-6-astra (Responses API) 2,902 tokens, gpt-5.5 (Chat Completions) 1,025. Sized for the gpt-6 models plus
    # 1,000 for a dense page's text. Models measured lower set their own pdf_tokens_per_page in conf/openai_models.json.
    PDF_TOKENS_PER_PAGE = 4_000

    def __init__(self, api_key: str, **kwargs):
        """Initialize OpenAI provider with API key."""
        self._ensure_registry()
        # Set default OpenAI base URL, allow override for regions/custom endpoints
        kwargs.setdefault("base_url", "https://api.openai.com/v1")
        super().__init__(api_key, **kwargs)
        self._invalidate_capability_cache()

    # ------------------------------------------------------------------
    # Capability surface
    # ------------------------------------------------------------------

    def _lookup_capabilities(
        self,
        canonical_name: str,
        requested_name: Optional[str] = None,
    ) -> Optional[ModelCapabilities]:
        """Look up OpenAI capabilities from built-ins or the custom registry."""

        self._ensure_registry()
        builtin = super()._lookup_capabilities(canonical_name, requested_name)
        if builtin is not None:
            return builtin

        try:
            from .registries.openrouter import OpenRouterModelRegistry

            registry = OpenRouterModelRegistry()
            config = registry.get_model_config(canonical_name)

            if config and config.provider == ProviderType.OPENAI:
                return config

        except Exception as exc:  # pragma: no cover - registry failures are non-critical
            logger.debug(f"Could not resolve custom OpenAI model '{canonical_name}': {exc}")

        return None

    def _finalise_capabilities(
        self,
        capabilities: ModelCapabilities,
        canonical_name: str,
        requested_name: str,
    ) -> ModelCapabilities:
        """Ensure registry-sourced models report the correct provider type."""

        if capabilities.provider != ProviderType.OPENAI:
            capabilities.provider = ProviderType.OPENAI
        return capabilities

    def _raise_unsupported_model(self, model_name: str) -> None:
        raise ValueError(f"Unsupported OpenAI model: {model_name}")

    # ------------------------------------------------------------------
    # Provider identity
    # ------------------------------------------------------------------

    def get_provider_type(self) -> ProviderType:
        """Get the provider type."""
        return ProviderType.OPENAI

    # ------------------------------------------------------------------
    # Provider preferences
    # ------------------------------------------------------------------

    def get_preferred_model(self, category: "ToolModelCategory", allowed_models: list[str]) -> Optional[str]:
        """Get OpenAI's preferred model for a given category from allowed models.

        Args:
            category: The tool category requiring a model
            allowed_models: Pre-filtered list of models allowed by restrictions

        Returns:
            Preferred model name or None
        """
        from tools.models import ToolModelCategory

        if not allowed_models:
            return None

        # Helper to find first available from preference list
        def find_first(preferences: list[str]) -> Optional[str]:
            """Return first available model from preference list."""
            for model in preferences:
                if model in allowed_models:
                    return model
            return None

        if category == ToolModelCategory.EXTENDED_REASONING:
            # Prefer the most capable models for deep reasoning and coding tasks
            # GPT-6 Astra is the current flagship (Sept 2026); GPT-6 Sol is the cheaper high-end tier.
            # Only IDs the OpenAI API currently serves belong here - the gpt-5.x-thinking/-instant
            # ChatGPT names and o3-pro return "model does not exist" upstream.
            preferred = find_first(
                [
                    "gpt-6-astra",
                    "gpt-6-sol",
                    "gpt-5.6-sol",
                    "gpt-5.5-pro",
                    "gpt-5.5",
                    "gpt-5.4-pro",
                    "gpt-5.4",
                    "gpt-5.2",
                    "gpt-5.2-pro",
                    "gpt-5-pro",
                    "gpt-5",
                    "o3",
                ]
            )
            return preferred if preferred else allowed_models[0]

        elif category == ToolModelCategory.FAST_RESPONSE:
            # Prefer fast, cost-efficient models
            # GPT-6 Luna is the fast/low-cost GPT-6 tier ($0.10/$0.50), GPT-5.4 as capable fallback
            preferred = find_first(
                [
                    "gpt-6-luna",
                    "gpt-5.6-luna",
                    "gpt-5.4",
                    "gpt-5.2",
                    "gpt-5.1",
                    "gpt-5",
                    "gpt-5-mini",
                    "o4-mini",
                    "o3-mini",
                    "gpt-5-nano",
                ]
            )
            if preferred:
                return preferred
            # No allowed model is on the list: take the lowest-ranked one (allowed_models[0] is the most capable).
            return self.pick_fast_by_rank(allowed_models) or allowed_models[0]

        else:  # BALANCED or default
            # Prefer GPT-6 Sol for best all-round performance per dollar (1.05M context, $2/$10)
            preferred = find_first(
                [
                    "gpt-6-sol",
                    "gpt-5.6-sol",
                    "gpt-5.6-terra",
                    "gpt-5.5",
                    "gpt-5.4",
                    "gpt-5.4-pro",
                    "gpt-5.2",
                    "gpt-5.1",
                    "gpt-5",
                    "gpt-5.2-pro",
                    "gpt-5-mini",
                    "gpt-4.1",
                    "o4-mini",
                    "o3-mini",
                ]
            )
            return preferred if preferred else allowed_models[0]


# Load registry data at import time so dependent providers (Azure) can reuse it
OpenAIModelProvider._ensure_registry()
