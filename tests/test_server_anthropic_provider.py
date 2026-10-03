"""The MCP server registers the native Anthropic provider when ANTHROPIC_API_KEY is set."""

import os
from unittest.mock import patch

import pytest

from providers.anthropic import AnthropicProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ProviderType
from tools.models import ToolModelCategory


def _clear_providers():
    """Clear cached/registered providers so prior tests cannot leak state (as in tests/test_listmodels.py)."""
    import utils.model_restrictions

    ModelProviderRegistry.clear_cache()
    for provider_type in list(ProviderType):
        ModelProviderRegistry.unregister_provider(provider_type)
    utils.model_restrictions._restriction_service = None


def _configure():
    """Register providers from exactly ``env`` (os.environ must already be patched to it)."""
    from server import configure_providers

    _clear_providers()
    configure_providers()


@pytest.fixture(autouse=True)
def _restore_registry():
    yield
    _clear_providers()  # conftest's autouse fixture re-registers Google/OpenAI/xAI for later tests


def test_anthropic_key_alone_registers_the_native_provider():
    env = {"ANTHROPIC_API_KEY": "test-key"}
    with patch.dict(os.environ, env, clear=True):
        _configure()
        assert ProviderType.ANTHROPIC in ModelProviderRegistry.get_available_providers()
        assert isinstance(ModelProviderRegistry.get_provider_for_model("claude-opus-5-5"), AnthropicProvider)


def test_native_anthropic_wins_over_openrouter():
    env = {"ANTHROPIC_API_KEY": "test-key", "OPENROUTER_API_KEY": "test-key"}
    with patch.dict(os.environ, env, clear=True):
        _configure()
        assert isinstance(ModelProviderRegistry.get_provider_for_model("opus"), AnthropicProvider)


def test_placeholder_anthropic_key_is_ignored():
    env = {"ANTHROPIC_API_KEY": "your_anthropic_api_key_here", "GEMINI_API_KEY": "test-key"}
    with patch.dict(os.environ, env, clear=True):
        _configure()
        assert ProviderType.ANTHROPIC not in ModelProviderRegistry.get_available_providers()


def test_auto_mode_routing_is_unchanged_by_the_anthropic_key():
    usual = {"XAI_API_KEY": "test-key", "GEMINI_API_KEY": "test-key", "OPENAI_API_KEY": "test-key"}

    def picks(env):
        with patch.dict(os.environ, env, clear=True):
            _configure()
            return {
                category: ModelProviderRegistry.get_preferred_fallback_model(category) for category in ToolModelCategory
            }

    before = picks(usual)
    after = picks({**usual, "ANTHROPIC_API_KEY": "test-key"})
    assert len(before) == 3
    assert after == before


def test_no_keys_error_lists_the_anthropic_key():
    from server import configure_providers

    with patch.dict(os.environ, {}, clear=True):
        _clear_providers()
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            configure_providers()


def _picks(env):
    with patch.dict(os.environ, env, clear=True):
        _configure()
        return {
            category: ModelProviderRegistry.get_preferred_fallback_model(category) for category in ToolModelCategory
        }


def test_auto_mode_prefers_claude_over_openai_without_xai_or_gemini():
    # With xAI or Gemini configured they win every category (see the test above). Without them, Anthropic comes
    # before OpenAI in PROVIDER_PRIORITY_ORDER, so auto mode now picks Claude, as the CLI already did.
    order = ModelProviderRegistry.PROVIDER_PRIORITY_ORDER
    assert order.index(ProviderType.ANTHROPIC) < order.index(ProviderType.OPENAI)

    openai_only = _picks({"OPENAI_API_KEY": "test-key"})
    picks = _picks({"OPENAI_API_KEY": "test-key", "ANTHROPIC_API_KEY": "test-key"})
    assert picks == {
        ToolModelCategory.EXTENDED_REASONING: "claude-fable-5-1",
        ToolModelCategory.FAST_RESPONSE: "claude-haiku-4-5-20251001",
        ToolModelCategory.BALANCED: "claude-sonnet-5-5",
    }
    assert all(not model.startswith("claude-") for model in openai_only.values())
