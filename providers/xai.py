"""X.AI (GROK) model provider implementation."""

import logging
from typing import TYPE_CHECKING, ClassVar, Optional

if TYPE_CHECKING:
    from tools.models import ToolModelCategory

from .openai_compatible import OpenAICompatibleProvider
from .registries.xai import XAIModelRegistry
from .registry_provider_mixin import RegistryBackedProviderMixin
from .shared import ModelCapabilities, ProviderType

logger = logging.getLogger(__name__)


class XAIModelProvider(RegistryBackedProviderMixin, OpenAICompatibleProvider):
    """Integration for X.AI's GROK models exposed over an OpenAI-style API.

    Publishes capability metadata for the officially supported deployments and
    maps tool-category preferences to the appropriate GROK model.
    """

    FRIENDLY_NAME = "X.AI"

    REGISTRY_CLASS = XAIModelRegistry
    MODEL_CAPABILITIES: ClassVar[dict[str, ModelCapabilities]] = {}

    def __init__(self, api_key: str, **kwargs):
        """Initialize X.AI provider with API key."""
        # Set X.AI base URL
        kwargs.setdefault("base_url", "https://api.x.ai/v1")
        self._ensure_registry()
        super().__init__(api_key, **kwargs)
        self._invalidate_capability_cache()

    def get_provider_type(self) -> ProviderType:
        """Get the provider type."""
        return ProviderType.XAI

    def get_preferred_model(self, category: "ToolModelCategory", allowed_models: list[str]) -> Optional[str]:
        """Get XAI's preferred model for a given category from allowed models.

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
            for model in preferences:
                if model in allowed_models:
                    return model
            return None

        if category == ToolModelCategory.EXTENDED_REASONING:
            # Grok 4.3 is the SOTA flagship with configurable reasoning effort, 1M context.
            preferred = find_first(
                [
                    "grok-4.3",
                    "grok-4.20-beta-0309-reasoning",
                    "grok-3-fast",
                ]
            )
            return preferred if preferred else allowed_models[0]

        elif category == ToolModelCategory.FAST_RESPONSE:
            # Grok 4.3 (current SOTA) supports reasoning_effort=none for latency-sensitive use cases.
            # Callers should pass reasoning_effort=none to skip thinking.
            preferred = find_first(
                [
                    "grok-4.3",
                    "grok-4.20-beta-0309-non-reasoning",
                    "grok-3-fast",
                    "grok-3-mini-fast",
                ]
            )
            return preferred if preferred else allowed_models[0]

        else:  # BALANCED or default
            preferred = find_first(
                [
                    "grok-4.3",
                    "grok-4.20-beta-0309-reasoning",
                    "grok-3-fast",
                ]
            )
            return preferred if preferred else allowed_models[0]


# Load registry data at import time
XAIModelProvider._ensure_registry()
