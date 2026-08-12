"""Tests for X.AI provider implementation."""

import os
from unittest.mock import MagicMock, patch

import pytest

from providers.shared import ProviderType
from providers.xai import XAIModelProvider


class TestXAIProvider:
    """Test X.AI provider functionality."""

    def setup_method(self):
        """Set up clean state before each test."""
        # Clear restriction service cache before each test
        import utils.model_restrictions

        utils.model_restrictions._restriction_service = None

    def teardown_method(self):
        """Clean up after each test to avoid singleton issues."""
        # Clear restriction service cache after each test
        import utils.model_restrictions

        utils.model_restrictions._restriction_service = None

    @patch.dict(os.environ, {"XAI_API_KEY": "test-key"})
    def test_initialization(self):
        """Test provider initialization."""
        provider = XAIModelProvider("test-key")
        assert provider.api_key == "test-key"
        assert provider.get_provider_type() == ProviderType.XAI
        assert provider.base_url == "https://api.x.ai/v1"

    def test_initialization_with_custom_url(self):
        """Test provider initialization with custom base URL."""
        provider = XAIModelProvider("test-key", base_url="https://custom.x.ai/v1")
        assert provider.api_key == "test-key"
        assert provider.base_url == "https://custom.x.ai/v1"

    def test_model_validation(self):
        """Test model name validation."""
        provider = XAIModelProvider("test-key")

        # Test valid models (bare grok/grok4/grok-4 aliases live on flagship grok-4.6; grok-3 aliases on grok-3-fast)
        assert provider.validate_model_name("grok-4") is True  # alias on grok-4.6
        assert provider.validate_model_name("grok4") is True
        assert provider.validate_model_name("grok") is True
        assert provider.validate_model_name("grok-3") is True  # alias on grok-3-fast
        assert provider.validate_model_name("grok-3-fast") is True
        assert provider.validate_model_name("grokfast") is True

        # Test invalid model
        assert provider.validate_model_name("invalid-model") is False
        assert provider.validate_model_name("gpt-4") is False
        assert provider.validate_model_name("gemini-pro") is False

    def test_resolve_model_name(self):
        """Test model name resolution."""
        provider = XAIModelProvider("test-key")

        # Test shorthand resolution
        assert provider._resolve_model_name("grok") == "grok-4.6"
        assert provider._resolve_model_name("grok4") == "grok-4.6"
        # grok3 / grok-3 / grokfast all resolve to grok-3-fast (only surviving Grok 3 SKU)
        assert provider._resolve_model_name("grok3") == "grok-3-fast"
        assert provider._resolve_model_name("grokfast") == "grok-3-fast"
        assert provider._resolve_model_name("grok3fast") == "grok-3-fast"

        # Family/retired slugs alias onto current SOTA
        assert provider._resolve_model_name("grok-4") == "grok-4.6"
        assert provider._resolve_model_name("grok-3") == "grok-3-fast"
        assert provider._resolve_model_name("grok-3-fast") == "grok-3-fast"

    def test_get_capabilities_grok3_legacy_alias(self):
        """Test that retired grok-3 slug resolves to grok-3-fast capabilities."""
        provider = XAIModelProvider("test-key")

        capabilities = provider.get_capabilities("grok-3")
        assert capabilities.model_name == "grok-3-fast"
        assert capabilities.friendly_name == "X.AI (Grok 3 Fast)"
        assert capabilities.context_window == 131_072
        assert capabilities.provider == ProviderType.XAI
        assert not capabilities.supports_extended_thinking
        assert capabilities.supports_system_prompts is True
        assert capabilities.supports_streaming is True
        assert capabilities.supports_function_calling is True

        # Test temperature range
        assert capabilities.temperature_constraint.min_temp == 0.0
        assert capabilities.temperature_constraint.max_temp == 2.0
        assert capabilities.temperature_constraint.default_temp == 0.3

    def test_get_capabilities_grok4_legacy_alias(self):
        """Test that the grok-4 family slug resolves to grok-4.6 capabilities."""
        provider = XAIModelProvider("test-key")

        capabilities = provider.get_capabilities("grok-4")
        assert capabilities.model_name == "grok-4.6"
        assert capabilities.friendly_name == "X.AI (Grok 4.6)"
        assert capabilities.context_window == 500_000
        assert capabilities.provider == ProviderType.XAI
        assert capabilities.supports_extended_thinking is True
        assert capabilities.supports_system_prompts is True
        assert capabilities.supports_streaming is True
        assert capabilities.supports_function_calling is True
        assert capabilities.supports_json_mode is True
        assert capabilities.supports_images is True

        # Test temperature range
        assert capabilities.temperature_constraint.min_temp == 0.0
        assert capabilities.temperature_constraint.max_temp == 2.0
        assert capabilities.temperature_constraint.default_temp == 0.3

    def test_get_capabilities_with_shorthand(self):
        """Test getting model capabilities with shorthand."""
        provider = XAIModelProvider("test-key")

        capabilities = provider.get_capabilities("grok")
        assert capabilities.model_name == "grok-4.6"  # Should resolve to full name
        assert capabilities.context_window == 500_000

        capabilities_fast = provider.get_capabilities("grokfast")
        assert capabilities_fast.model_name == "grok-3-fast"  # Should resolve to full name

    def test_unsupported_model_capabilities(self):
        """Test error handling for unsupported models."""
        provider = XAIModelProvider("test-key")

        with pytest.raises(ValueError, match="Unsupported model 'invalid-model' for provider xai"):
            provider.get_capabilities("invalid-model")

    def test_extended_thinking_flags(self):
        """X.AI capabilities should expose extended thinking support correctly."""
        provider = XAIModelProvider("test-key")

        # grok-4/grok aliases resolve to grok-4.6 (grok-4.5/grok-4.3 also support reasoning effort)
        thinking_aliases = ["grok-4", "grok", "grok4", "grok-4.5", "grok-4.3", "grok-4.20-beta-0309-reasoning"]
        for alias in thinking_aliases:
            assert provider.get_capabilities(alias).supports_extended_thinking is True

        # grok-3 alias resolves to grok-3-fast (no extended thinking)
        non_thinking_aliases = ["grok-3", "grok-3-fast", "grokfast"]
        for alias in non_thinking_aliases:
            assert provider.get_capabilities(alias).supports_extended_thinking is False

    def test_provider_type(self):
        """Test provider type identification."""
        provider = XAIModelProvider("test-key")
        assert provider.get_provider_type() == ProviderType.XAI

    @patch.dict(os.environ, {"XAI_ALLOWED_MODELS": "grok-3-fast"})
    def test_model_restrictions(self):
        """Test model restrictions functionality."""
        # Clear cached restriction service
        import utils.model_restrictions
        from providers.registry import ModelProviderRegistry

        utils.model_restrictions._restriction_service = None
        ModelProviderRegistry.reset_for_testing()

        provider = XAIModelProvider("test-key")

        # grok-3-fast should be allowed
        assert provider.validate_model_name("grok-3-fast") is True
        assert provider.validate_model_name("grokfast") is True  # alias for grok-3-fast
        assert provider.validate_model_name("grok-3") is True  # also alias for grok-3-fast

        # grok should be blocked (resolves to grok-4.6 which is not allowed)
        assert provider.validate_model_name("grok") is False

        # grok-3-mini should be blocked by restrictions
        assert provider.validate_model_name("grok-3-mini") is False

    @patch.dict(os.environ, {"XAI_ALLOWED_MODELS": "grok,grok-3-fast"})
    def test_multiple_model_restrictions(self):
        """Restrictions should allow aliases for Grok 4.1 Fast."""
        # Clear cached restriction service
        import utils.model_restrictions
        from providers.registry import ModelProviderRegistry

        utils.model_restrictions._restriction_service = None
        ModelProviderRegistry.reset_for_testing()

        provider = XAIModelProvider("test-key")

        # Shorthand "grok" should be allowed (alias itself is in the allow-list)
        assert provider.validate_model_name("grok") is True

        # "grok-3-fast" should be allowed (explicitly listed)
        assert provider.validate_model_name("grok-3-fast") is True

        # Shorthand "grokfast" should be allowed (resolves to grok-3-fast)
        assert provider.validate_model_name("grokfast") is True

        # grok-3-mini should not be allowed (not in restriction list)
        assert provider.validate_model_name("grok-3-mini") is False

    @patch.dict(os.environ, {"XAI_ALLOWED_MODELS": "grok,grok-3-fast,grok-4.3"})
    def test_both_shorthand_and_full_name_allowed(self):
        """Test that aliases and canonical names can be allowed together."""
        # Clear cached restriction service
        import utils.model_restrictions

        utils.model_restrictions._restriction_service = None

        provider = XAIModelProvider("test-key")

        # Shorthand "grok" and full name "grok-4.3" both allowed
        assert provider.validate_model_name("grok") is True  # Alias in allow-list (resolves to grok-4.6)
        assert provider.validate_model_name("grok-4.3") is True
        assert provider.validate_model_name("grok-3-fast") is True

        # grok-3-mini should not be allowed
        assert provider.validate_model_name("grok-3-mini") is False

    @patch.dict(os.environ, {"XAI_ALLOWED_MODELS": ""})
    def test_empty_restrictions_allows_all(self):
        """Test that empty restrictions allow all models."""
        # Clear cached restriction service
        import utils.model_restrictions

        utils.model_restrictions._restriction_service = None

        provider = XAIModelProvider("test-key")

        assert provider.validate_model_name("grok-4.3") is True
        assert provider.validate_model_name("grok-3-fast") is True
        assert provider.validate_model_name("grok") is True
        assert provider.validate_model_name("grok4") is True

    def test_friendly_name(self):
        """Test friendly name constant."""
        provider = XAIModelProvider("test-key")
        assert provider.FRIENDLY_NAME == "X.AI"

        capabilities = provider.get_capabilities("grok-3-fast")
        assert capabilities.friendly_name == "X.AI (Grok 3 Fast)"

    def test_supported_models_structure(self):
        """Test that MODEL_CAPABILITIES has the correct structure."""
        provider = XAIModelProvider("test-key")

        # Check that all expected base models are present
        assert "grok-4.6" in provider.MODEL_CAPABILITIES
        assert "grok-4.5" in provider.MODEL_CAPABILITIES
        assert "grok-4.3" in provider.MODEL_CAPABILITIES
        assert "grok-build-0.1" in provider.MODEL_CAPABILITIES
        assert "grok-3-fast" in provider.MODEL_CAPABILITIES

        # Check model configs have required fields
        from providers.shared import ModelCapabilities

        grok43_config = provider.MODEL_CAPABILITIES["grok-4.3"]
        assert isinstance(grok43_config, ModelCapabilities)
        assert hasattr(grok43_config, "context_window")
        assert hasattr(grok43_config, "supports_extended_thinking")
        assert hasattr(grok43_config, "aliases")
        assert grok43_config.context_window == 1_000_000
        assert grok43_config.supports_extended_thinking is True

        # Bare grok/grok4/grok-4 aliases live on flagship grok-4.6; retired grok-4-0709 stays on grok-4.3
        grok46_config = provider.MODEL_CAPABILITIES["grok-4.6"]
        assert grok46_config.context_window == 500_000
        assert grok46_config.supports_extended_thinking is True
        assert "grok" in grok46_config.aliases
        assert "grok4" in grok46_config.aliases
        assert "grok-4" in grok46_config.aliases
        assert "grok-4-0709" in grok43_config.aliases

        # grok-4.5 demoted to a pinned-only entry (no bare aliases)
        grok45_config = provider.MODEL_CAPABILITIES["grok-4.5"]
        assert grok45_config.context_window == 500_000
        assert "grok" not in grok45_config.aliases

        # grok-code-fast-1 was renamed upstream to grok-build-0.1; old slugs alias onto it
        grokbuild_config = provider.MODEL_CAPABILITIES["grok-build-0.1"]
        assert grokbuild_config.context_window == 256_000
        assert "grok-code-fast-1" in grokbuild_config.aliases

        grok3fast_config = provider.MODEL_CAPABILITIES["grok-3-fast"]
        assert grok3fast_config.context_window == 131_072
        assert grok3fast_config.supports_extended_thinking is False
        # grok-3 retired slug aliases onto grok-3-fast (only surviving Grok 3 SKU)
        assert "grok3fast" in grok3fast_config.aliases
        assert "grokfast" in grok3fast_config.aliases
        assert "grok-3" in grok3fast_config.aliases
        assert "grok3" in grok3fast_config.aliases

    @patch("providers.openai_compatible.OpenAI")
    def test_generate_content_resolves_alias_before_api_call(self, mock_openai_class):
        """Test that generate_content resolves aliases before making API calls.

        This is the CRITICAL test that ensures aliases like 'grok' get resolved
        to the flagship model before being sent to X.AI API.
        """
        # Set up mock OpenAI client
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Mock the completion response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "grok-4.6"  # API returns the resolved model name
        mock_response.id = "test-id"
        mock_response.created = 1234567890
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15

        mock_client.chat.completions.create.return_value = mock_response

        provider = XAIModelProvider("test-key")

        # Call generate_content with alias 'grok'
        result = provider.generate_content(
            prompt="Test prompt",
            model_name="grok",
            temperature=0.7,  # This should be resolved to "grok-4.6"
        )

        # Verify the API was called with the RESOLVED model name
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]

        # CRITICAL ASSERTION: The API should receive "grok-4.6", not "grok"
        assert call_kwargs["model"] == "grok-4.6", f"Expected 'grok-4.6' but API received '{call_kwargs['model']}'"

        # Verify other parameters
        assert call_kwargs["temperature"] == 0.7
        assert len(call_kwargs["messages"]) == 1
        assert call_kwargs["messages"][0]["role"] == "user"
        assert call_kwargs["messages"][0]["content"] == "Test prompt"

        # Verify response
        assert result.content == "Test response"
        assert result.model_name == "grok-4.6"  # Should be the resolved name

    @patch("providers.openai_compatible.OpenAI")
    def test_generate_content_other_aliases(self, mock_openai_class):
        """Test other alias resolutions in generate_content."""
        from unittest.mock import MagicMock

        # Set up mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.chat.completions.create.return_value = mock_response

        provider = XAIModelProvider("test-key")

        # Test grok4 -> grok-4.6
        mock_response.model = "grok-4.6"
        provider.generate_content(prompt="Test", model_name="grok4", temperature=0.7)
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "grok-4.6"

        # Test grok-4 family slug -> grok-4.6 (follows flagship)
        mock_response.model = "grok-4.6"
        provider.generate_content(prompt="Test", model_name="grok-4", temperature=0.7)
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "grok-4.6"

        # Test retired grok-3 slug -> grok-3-fast (only surviving Grok 3 SKU)
        mock_response.model = "grok-3-fast"
        provider.generate_content(prompt="Test", model_name="grok3", temperature=0.7)
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "grok-3-fast"
