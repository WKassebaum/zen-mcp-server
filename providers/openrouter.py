"""OpenRouter provider implementation."""

import logging
from typing import TYPE_CHECKING, ClassVar, Optional

from utils.env import get_env

from .openai_compatible import OpenAICompatibleProvider
from .registries.openrouter import OpenRouterModelRegistry
from .shared import (
    ModelCapabilities,
    ProviderType,
    RangeTemperatureConstraint,
)

if TYPE_CHECKING:
    from tools.models import ToolModelCategory


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
