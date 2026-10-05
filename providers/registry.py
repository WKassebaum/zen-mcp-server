"""Model provider registry for managing available providers."""

import logging
from typing import TYPE_CHECKING, Optional

from utils.env import get_env

from .base import ModelProvider
from .shared import ProviderType

if TYPE_CHECKING:
    from tools.models import ToolModelCategory

# Words that stand for a pick instead of naming a model, as 'auto' does (resolve_model_intent). Case-insensitive. No
# catalog name or alias may use one: tests/test_intent_models.py checks every conf/*_models.json.
INTENT_MODELS = ("frontier", "balanced", "fast")


class ModelProviderRegistry:
    """Central catalogue of provider implementations used by the MCP server.

    Role
        Holds the mapping between :class:`ProviderType` values and concrete
        :class:`ModelProvider` subclasses/factories.  At runtime the registry
        is responsible for instantiating providers, caching them for reuse, and
        mediating lookup of providers and model names in provider priority
        order.

    Core responsibilities
        * Resolve API keys and other runtime configuration for each provider
        * Lazily create provider instances so unused backends incur no cost
        * Expose convenience methods for enumerating available models and
          locating which provider can service a requested model name or alias
        * Honour the project-wide provider priority policy so namespaces (or
          alias collisions) are resolved deterministically.
    """

    _instance = None

    # Provider priority order for model selection
    # Native APIs first, then custom endpoints, then catch-all providers
    PROVIDER_PRIORITY_ORDER = [
        ProviderType.XAI,  # Direct X.AI GROK access (flagship priority)
        ProviderType.GOOGLE,  # Direct Gemini access
        ProviderType.ANTHROPIC,  # Direct Anthropic Claude access
        ProviderType.OPENAI,  # Direct OpenAI access
        ProviderType.AZURE,  # Azure-hosted OpenAI deployments
        ProviderType.DIAL,  # DIAL unified API access
        ProviderType.CUSTOM,  # Local/self-hosted models
        ProviderType.OPENROUTER,  # Catch-all for cloud models
    ]

    # Environment variable holding each provider's API key
    API_KEY_ENV_VARS = {
        ProviderType.GOOGLE: "GEMINI_API_KEY",
        ProviderType.OPENAI: "OPENAI_API_KEY",
        ProviderType.ANTHROPIC: "ANTHROPIC_API_KEY",
        ProviderType.AZURE: "AZURE_OPENAI_API_KEY",
        ProviderType.XAI: "XAI_API_KEY",
        ProviderType.OPENROUTER: "OPENROUTER_API_KEY",
        ProviderType.CUSTOM: "CUSTOM_API_KEY",  # Can be empty for providers that don't need auth
        ProviderType.DIAL: "DIAL_API_KEY",
    }

    def __new__(cls):
        """Singleton pattern for registry."""
        if cls._instance is None:
            logging.debug("REGISTRY: Creating new registry instance")
            cls._instance = super().__new__(cls)
            # Initialize instance dictionaries on first creation
            cls._instance._providers = {}
            cls._instance._initialized_providers = {}
            logging.debug(f"REGISTRY: Created instance {cls._instance}")
        return cls._instance

    @classmethod
    def register_provider(cls, provider_type: ProviderType, provider_class: type[ModelProvider]) -> None:
        """Register a new provider class.

        Args:
            provider_type: Type of the provider (e.g., ProviderType.GOOGLE)
            provider_class: Class that implements ModelProvider interface
        """
        instance = cls()
        instance._providers[provider_type] = provider_class
        # Invalidate any cached instance so subsequent lookups use the new registration
        instance._initialized_providers.pop(provider_type, None)

    @classmethod
    def get_provider(cls, provider_type: ProviderType, force_new: bool = False) -> Optional[ModelProvider]:
        """Get an initialized provider instance.

        Args:
            provider_type: Type of provider to get
            force_new: Force creation of new instance instead of using cached

        Returns:
            Initialized ModelProvider instance or None if not available
        """
        instance = cls()

        # Return cached instance if available and not forcing new
        if not force_new and provider_type in instance._initialized_providers:
            return instance._initialized_providers[provider_type]

        # Check if provider class is registered
        if provider_type not in instance._providers:
            return None

        # Get API key from environment
        api_key = cls._get_api_key_for_provider(provider_type)

        # Get provider class or factory function
        provider_class = instance._providers[provider_type]

        # For custom providers, handle special initialization requirements
        if provider_type == ProviderType.CUSTOM:
            # Check if it's a factory function (callable but not a class)
            if callable(provider_class) and not isinstance(provider_class, type):
                # Factory function - call it with api_key parameter
                provider = provider_class(api_key=api_key)
            else:
                # Regular class - need to handle URL requirement
                custom_url = get_env("CUSTOM_API_URL", "") or ""
                if not custom_url:
                    if api_key:  # Key is set but URL is missing
                        logging.warning("CUSTOM_API_KEY set but CUSTOM_API_URL missing – skipping Custom provider")
                    return None
                # Use empty string as API key for custom providers that don't need auth (e.g., Ollama)
                # This allows the provider to be created even without CUSTOM_API_KEY being set
                api_key = api_key or ""
                # Initialize custom provider with both API key and base URL
                provider = provider_class(api_key=api_key, base_url=custom_url)
        elif provider_type == ProviderType.GOOGLE:
            # For Gemini, check if custom base URL is configured
            if not api_key:
                return None
            gemini_base_url = get_env("GEMINI_BASE_URL")
            provider_kwargs = {"api_key": api_key}
            if gemini_base_url:
                provider_kwargs["base_url"] = gemini_base_url
                logging.info(f"Initialized Gemini provider with custom endpoint: {gemini_base_url}")
            provider = provider_class(**provider_kwargs)
        elif provider_type == ProviderType.AZURE:
            if not api_key:
                return None

            azure_endpoint = get_env("AZURE_OPENAI_ENDPOINT")
            if not azure_endpoint:
                logging.warning("AZURE_OPENAI_ENDPOINT missing – skipping Azure OpenAI provider")
                return None

            azure_version = get_env("AZURE_OPENAI_API_VERSION")
            provider = provider_class(
                api_key=api_key,
                azure_endpoint=azure_endpoint,
                api_version=azure_version,
            )
        else:
            if not api_key:
                return None
            # Initialize non-custom provider with just API key
            provider = provider_class(api_key=api_key)

        # Cache the instance
        instance._initialized_providers[provider_type] = provider

        return provider

    @classmethod
    def get_provider_for_model(cls, model_name: str) -> Optional[ModelProvider]:
        """Get provider instance for a specific model name.

        Provider priority order:
        1. Native APIs (GOOGLE, OPENAI) - Most direct and efficient
        2. CUSTOM - For local/private models with specific endpoints
        3. OPENROUTER - Catch-all for cloud models via unified API

        Args:
            model_name: Name of the model (e.g., "gemini-2.5-flash", "gpt5")

        Returns:
            ModelProvider instance that supports this model
        """
        logging.debug(f"get_provider_for_model called with model_name='{model_name}'")

        # Check providers in priority order
        instance = cls()
        logging.debug(f"Registry instance: {instance}")
        logging.debug(f"Available providers in registry: {list(instance._providers.keys())}")

        for provider_type in cls.PROVIDER_PRIORITY_ORDER:
            if provider_type in instance._providers:
                logging.debug(f"Found {provider_type} in registry")
                # Get or create provider instance
                provider = cls.get_provider(provider_type)
                if provider and provider.validate_model_name(model_name):
                    logging.debug(f"{provider_type} validates model {model_name}")
                    return provider
                else:
                    logging.debug(f"{provider_type} does not validate model {model_name}")
            else:
                logging.debug(f"{provider_type} not found in registry")

        logging.debug(f"No provider found for model {model_name}")
        return None

    @classmethod
    def get_available_providers(cls) -> list[ProviderType]:
        """Get list of registered provider types."""
        instance = cls()
        return list(instance._providers.keys())

    @classmethod
    def get_available_models(cls, respect_restrictions: bool = True) -> dict[str, ProviderType]:
        """Get mapping of all available models to their providers.

        Args:
            respect_restrictions: If True, filter out models not allowed by restrictions

        Returns:
            Dict mapping model names to provider types
        """
        # Import here to avoid circular imports
        from utils.model_restrictions import get_restriction_service

        restriction_service = get_restriction_service() if respect_restrictions else None
        models: dict[str, ProviderType] = {}
        instance = cls()

        for provider_type in instance._providers:
            provider = cls.get_provider(provider_type)
            if not provider:
                continue

            try:
                available = provider.list_models(respect_restrictions=respect_restrictions)
            except NotImplementedError:
                logging.warning("Provider %s does not implement list_models", provider_type)
                continue

            if restriction_service and restriction_service.has_restrictions(provider_type):
                restricted_display = cls._collect_restricted_display_names(
                    provider,
                    provider_type,
                    available,
                    restriction_service,
                )
                if restricted_display:
                    for model_name in restricted_display:
                        models[model_name] = provider_type
                    continue

            for model_name in available:
                # =====================================================================================
                # CRITICAL: Prevent double restriction filtering (Fixed Issue #98)
                # =====================================================================================
                # Previously, both the provider AND registry applied restrictions, causing
                # double-filtering that resulted in "no models available" errors.
                #
                # Logic: If respect_restrictions=True, provider already filtered models,
                # so registry should NOT filter them again.
                # TEST COVERAGE: tests/test_provider_routing_bugs.py::TestOpenRouterAliasRestrictions
                # =====================================================================================
                if (
                    restriction_service
                    and not respect_restrictions  # Only filter if provider didn't already filter
                    and not restriction_service.is_allowed(provider_type, model_name)
                ):
                    logging.debug("Model %s filtered by restrictions", model_name)
                    continue
                models[model_name] = provider_type

        return models

    @classmethod
    def _collect_restricted_display_names(
        cls,
        provider: ModelProvider,
        provider_type: ProviderType,
        available: list[str],
        restriction_service,
    ) -> list[str] | None:
        """Derive the human-facing model list when restrictions are active."""

        allowed_models = restriction_service.get_allowed_models(provider_type)
        if not allowed_models:
            return None

        allowed_details: list[tuple[str, int]] = []

        for model_name in sorted(allowed_models):
            try:
                capabilities = provider.get_capabilities(model_name)
            except (AttributeError, ValueError):
                continue

            try:
                rank = capabilities.get_effective_capability_rank()
                rank_value = float(rank)
            except (AttributeError, TypeError, ValueError):
                rank_value = 0.0

            allowed_details.append((model_name, rank_value))

        if allowed_details:
            allowed_details.sort(key=lambda item: (-item[1], item[0]))
            return [name for name, _ in allowed_details]

        # Fallback: intersect the allowlist with the provider-advertised names.
        available_lookup = {name.lower(): name for name in available}
        display_names: list[str] = []
        for model_name in sorted(allowed_models):
            lowered = model_name.lower()
            if lowered in available_lookup:
                display_names.append(available_lookup[lowered])

        return display_names

    @classmethod
    def get_available_model_names(cls, provider_type: Optional[ProviderType] = None) -> list[str]:
        """Get list of available model names, optionally filtered by provider.

        This respects model restrictions automatically.

        Args:
            provider_type: Optional provider to filter by

        Returns:
            List of available model names
        """
        available_models = cls.get_available_models(respect_restrictions=True)

        if provider_type:
            # Filter by specific provider
            return [name for name, ptype in available_models.items() if ptype == provider_type]
        else:
            # Return all available models
            return list(available_models.keys())

    @classmethod
    def _get_api_key_for_provider(cls, provider_type: ProviderType) -> Optional[str]:
        """Get API key for a provider from environment variables.

        Args:
            provider_type: Provider type to get API key for

        Returns:
            API key string or None if not found
        """
        env_var = cls.API_KEY_ENV_VARS.get(provider_type)
        if not env_var:
            return None

        return get_env(env_var)

    @classmethod
    def _get_allowed_models_for_provider(cls, provider: ModelProvider, provider_type: ProviderType) -> list[str]:
        """Get a list of allowed canonical model names for a given provider.

        Args:
            provider: The provider instance to get models for
            provider_type: The provider type for restriction checking

        Returns:
            List of model names that are both supported and allowed
        """
        from utils.model_restrictions import get_restriction_service

        restriction_service = get_restriction_service()

        allowed_models = []

        # Get the provider's supported models
        try:
            # Use list_models to get all supported models (handles both regular and custom providers)
            supported_models = provider.list_models(respect_restrictions=False)
        except (NotImplementedError, AttributeError):
            # Fallback to provider-declared capability maps if list_models not implemented
            model_map = getattr(provider, "MODEL_CAPABILITIES", None)
            supported_models = list(model_map.keys()) if isinstance(model_map, dict) else []

        # Filter by restrictions
        for model_name in supported_models:
            if restriction_service.is_allowed(provider_type, model_name):
                allowed_models.append(model_name)

        return allowed_models

    @classmethod
    def _filter_models_for_media(cls, provider, model_names: list[str], required_media: frozenset) -> list[str]:
        """Keep models whose flags cover required_media on a provider that can encode it.

        A model that takes media only when named (takes_media_only_when_named) is never kept: auto mode, intent
        words and find_media_capable_models never pick it for media. A model the user names is checked against its
        own flags instead (_validate_media_support).
        """
        if not required_media:
            return model_names
        if not provider.MEDIA_AUTO_ROUTING or not required_media <= frozenset(provider.MEDIA_KINDS):
            return []
        capable = []
        for name in model_names:
            if cls.takes_media_only_when_named(provider, name):
                continue
            try:
                if required_media <= provider.get_capabilities(name).supported_media_kinds():
                    capable.append(name)
            except (AttributeError, ValueError):
                continue
        return capable

    @classmethod
    def takes_media_only_when_named(cls, provider, model_name: str) -> bool:
        """Whether ``model_name`` may get media only when a call names it: its provider has MEDIA_AUTO_ROUTING False
        (xAI), or it is a Grok model on OpenRouter. xAI reads attached files through a paid search tool, so this holds
        for x-ai/* models whatever the OpenRouter catalog flags say."""
        if not getattr(provider, "MEDIA_AUTO_ROUTING", True):
            return True
        try:
            provider_type = provider.get_provider_type()
        except Exception:
            return False
        return provider_type == ProviderType.OPENROUTER and cls._model_vendor(provider_type, model_name) == "xai"

    @classmethod
    def find_media_capable_models(cls, required_media: frozenset, limit: int = 5) -> list[str]:
        """Canonical names of available models (current keys and restrictions) that take required_media, best first.

        get_available_models() lists aliases too; every alias resolves to the same capabilities, so
        dedupe on the canonical ``model_name`` or one model would be listed under several names.
        Media breadth is not part of the capability rank; here it breaks ties between equal ranks.
        Explicit-only providers (MEDIA_AUTO_ROUTING False) are left out, as in auto mode.
        """
        keys: dict[str, tuple[int, int]] = {}
        for model_name, provider_type in cls.get_available_models(respect_restrictions=True).items():
            provider = cls.get_provider(provider_type)
            if not provider or not cls._filter_models_for_media(provider, [model_name], required_media):
                continue
            capabilities = provider.get_capabilities(model_name)
            keys.setdefault(
                capabilities.model_name,
                (
                    capabilities.get_effective_capability_rank(),
                    len(capabilities.supported_media_kinds() & frozenset(provider.MEDIA_KINDS)),
                ),
            )
        ranked = sorted(keys.items(), key=lambda item: (-item[1][0], -item[1][1], item[0]))
        return [name for name, _ in ranked[:limit]]

    @classmethod
    def _pick_by_rank(cls, provider: ModelProvider, category: "ToolModelCategory", allowed_models: list[str]) -> str:
        """Pick from a provider that states no preference by ranking its allowed canonical models.

        EXTENDED_REASONING and BALANCED take the highest-ranked model. FAST_RESPONSE takes the provider's
        pick_fast_by_rank: the lowest-ranked model, skipping premium and low-scored ones while others remain.
        """
        from tools.models import ToolModelCategory

        if category == ToolModelCategory.FAST_RESPONSE:
            return provider.pick_fast_by_rank(allowed_models) or allowed_models[0]
        ranked = provider.rank_models(allowed_models)
        return ranked[0].model_name if ranked else allowed_models[0]

    @classmethod
    def get_preferred_fallback_model(
        cls, tool_category: Optional["ToolModelCategory"] = None, required_media: frozenset = frozenset()
    ) -> str:
        """Get the preferred fallback model based on provider priority and tool category.

        The first provider in PROVIDER_PRIORITY_ORDER that has allowed models (respecting restrictions and
        required_media) decides:
        1. It picks from its allowed list (get_preferred_model).
        2. If it states no preference (Azure, DIAL, Custom, or OpenRouter with nothing on its lists allowed), the
           registry ranks that provider's allowed models by capability (_pick_by_rank). A later provider is never
           asked: its preference (OpenRouter's lists) would beat a higher-priority provider such as Custom.

        Args:
            tool_category: Optional category to influence model selection

        Returns:
            Model name string for fallback use
        """
        from tools.models import ToolModelCategory

        effective_category = tool_category or ToolModelCategory.BALANCED

        for provider_type in cls.PROVIDER_PRIORITY_ORDER:
            provider = cls.get_provider(provider_type)
            if not provider:
                continue
            allowed_models = cls._get_allowed_models_for_provider(provider, provider_type)
            allowed_models = cls._filter_models_for_media(provider, allowed_models, required_media)
            if not allowed_models:
                continue

            preferred_model = provider.get_preferred_model(effective_category, allowed_models)
            if preferred_model:
                logging.debug(
                    f"Provider {provider_type.value} selected '{preferred_model}' for category '{effective_category.value}'"
                )
                return preferred_model

            ranked_model = cls._pick_by_rank(provider, effective_category, allowed_models)
            logging.debug(
                f"Provider {provider_type.value} states no preference; picked '{ranked_model}' by rank "
                f"for category '{effective_category.value}'"
            )
            return ranked_model

        # Media that no available model can take: refuse rather than return a model that would drop it
        if required_media:
            from utils.media import MediaNotSupportedError, format_kinds, providers_hint

            raise MediaNotSupportedError(
                f"No available model can take {format_kinds(required_media)} input: {providers_hint(required_media)}."
            )

        # Ultimate fallback if no providers have models
        logging.warning("No models available from any provider, using default fallback")
        return "gemini-3.8-flash"

    @classmethod
    def is_model_intent(cls, name: Optional[str]) -> bool:
        """Whether ``name`` is 'auto' or an intent word (INTENT_MODELS) rather than a model name."""
        return isinstance(name, str) and name.strip().lower() in ("auto", *INTENT_MODELS)

    @classmethod
    def resolve_model_intent(
        cls,
        name: Optional[str],
        tool_category: "ToolModelCategory",
        required_media: frozenset = frozenset(),
    ) -> Optional[str]:
        """The model 'auto' or an intent word stands for; None for any other name, which is used exactly as named.

        - auto: the tool category's pick (get_preferred_fallback_model).
        - fast / balanced: the FAST_RESPONSE / BALANCED pick, whatever the tool's category.
        - frontier: the highest-ranked allowed model across every configured provider, premium included. Ties
          break by PROVIDER_PRIORITY_ORDER, then canonical name.

        Every word respects restrictions and required_media, so explicit-only providers (MEDIA_AUTO_ROUTING False)
        never get media this way. Raises MediaNotSupportedError when no available model takes required_media.
        """
        from tools.models import ToolModelCategory

        if not cls.is_model_intent(name):
            return None
        word = name.strip().lower()
        if word == "frontier":
            best = None
            for _provider_type, ranked in cls._ranked_allowed_models(required_media):
                # Providers come in priority order and rank_models breaks a tie by name, so a later provider
                # wins only by ranking strictly higher.
                if best is None or ranked[0].get_effective_capability_rank() > best.get_effective_capability_rank():
                    best = ranked[0]
            if best is not None:
                return best.model_name
            # Nothing allowed anywhere: the category pick raises for media, or returns the default fallback
            return cls.get_preferred_fallback_model(tool_category, required_media=required_media)
        category = {"fast": ToolModelCategory.FAST_RESPONSE, "balanced": ToolModelCategory.BALANCED}.get(
            word, tool_category
        )
        return cls.get_preferred_fallback_model(category, required_media=required_media)

    @classmethod
    def frontier_panel(cls, limit: int = 4, required_media: frozenset = frozenset()) -> list[str]:
        """The top model of each vendor, as consensus consults them for 'frontier' or an empty model list.

        Providers are visited in PROVIDER_PRIORITY_ORDER, each model highest rank first, and a model joins the panel
        when its vendor (_model_vendor) is not on it yet. A native provider adds its top allowed model; OpenRouter
        adds the top model of each vendor not already there, so a native Anthropic key and OpenRouter never give
        two Anthropic models. Restrictions and required_media apply as in resolve_model_intent. Stops at ``limit``.
        """
        panel: list[str] = []
        vendors: set[str] = set()
        for provider_type, ranked in cls._ranked_allowed_models(required_media):
            for capabilities in ranked:
                vendor = cls._model_vendor(provider_type, capabilities.model_name)
                if vendor in vendors:
                    continue
                vendors.add(vendor)
                panel.append(capabilities.model_name)
                if len(panel) >= limit:
                    return panel
        return panel

    # OpenRouter id prefixes of the vendors that also have a native provider
    _OPENROUTER_VENDORS = {"x-ai": "xai", "google": "google", "anthropic": "anthropic", "openai": "openai"}

    @classmethod
    def _model_vendor(cls, provider_type: ProviderType, model_name: str) -> str:
        """Who makes the model: the provider type, or for OpenRouter the id prefix ('x-ai/grok-4.7' -> 'xai').

        Custom, Azure and DIAL count as their own provider type.
        """
        if provider_type != ProviderType.OPENROUTER:
            return provider_type.value
        prefix = model_name.split("/", 1)[0].lower()
        return cls._OPENROUTER_VENDORS.get(prefix, prefix)

    @classmethod
    def configured_key_names(cls) -> list[str]:
        """Env vars of the providers that are configured, in PROVIDER_PRIORITY_ORDER (Custom: CUSTOM_API_URL)."""
        names = []
        for provider_type in cls.PROVIDER_PRIORITY_ORDER:
            if cls.get_provider(provider_type) is not None:
                names.append(
                    "CUSTOM_API_URL" if provider_type == ProviderType.CUSTOM else cls.API_KEY_ENV_VARS[provider_type]
                )
        return names

    @classmethod
    def _ranked_allowed_models(cls, required_media: frozenset = frozenset()):
        """(provider type, capabilities highest rank first) for each configured provider, in priority order.

        Only allowed models that take required_media are listed (explicit-only providers take none), and a
        provider left with no model is skipped.
        """
        for provider_type in cls.PROVIDER_PRIORITY_ORDER:
            provider = cls.get_provider(provider_type)
            if not provider:
                continue
            allowed_models = cls._get_allowed_models_for_provider(provider, provider_type)
            allowed_models = cls._filter_models_for_media(provider, allowed_models, required_media)
            ranked = provider.rank_models(allowed_models) if allowed_models else []
            if ranked:
                yield provider_type, ranked

    @classmethod
    def get_available_providers_with_keys(cls) -> list[ProviderType]:
        """Get list of provider types that have valid API keys.

        Returns:
            List of ProviderType values for providers with valid API keys
        """
        available = []
        instance = cls()
        for provider_type in instance._providers:
            if cls.get_provider(provider_type) is not None:
                available.append(provider_type)
        return available

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached provider instances."""
        instance = cls()
        instance._initialized_providers.clear()

    @classmethod
    def reset_for_testing(cls) -> None:
        """Reset the registry to a clean state for testing.

        This provides a safe, public API for tests to clean up registry state
        without directly manipulating private attributes.
        """
        cls._instance = None
        if hasattr(cls, "_providers"):
            cls._providers = {}

    @classmethod
    def unregister_provider(cls, provider_type: ProviderType) -> None:
        """Unregister a provider (mainly for testing)."""
        instance = cls()
        instance._providers.pop(provider_type, None)
        instance._initialized_providers.pop(provider_type, None)
