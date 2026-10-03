"""ANTHROPIC_ALLOWED_MODELS restricts the native Anthropic provider like the other *_ALLOWED_MODELS variables."""

import logging
import os
from unittest.mock import patch

import pytest

from providers.anthropic import AnthropicProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ProviderType
from utils.model_restrictions import ModelRestrictionService, get_restriction_service


def _clear_providers():
    """Clear cached/registered providers so prior tests cannot leak state (as in tests/test_listmodels.py)."""
    import utils.model_restrictions

    ModelProviderRegistry.clear_cache()
    for provider_type in list(ProviderType):
        ModelProviderRegistry.unregister_provider(provider_type)
    utils.model_restrictions._restriction_service = None


def _configure():
    from server import configure_providers

    _clear_providers()
    configure_providers()


@pytest.fixture(autouse=True)
def _restore_registry():
    yield
    _clear_providers()  # conftest's autouse fixture re-registers Google/OpenAI/xAI for later tests


def test_anthropic_has_an_allow_list_variable():
    assert ModelRestrictionService.ENV_VARS[ProviderType.ANTHROPIC] == "ANTHROPIC_ALLOWED_MODELS"


def test_allow_list_restricts_native_claude():
    env = {"ANTHROPIC_API_KEY": "test-key", "ANTHROPIC_ALLOWED_MODELS": "sonnet"}
    with patch.dict(os.environ, env, clear=True):
        _configure()
        service = get_restriction_service()
        assert service.has_restrictions(ProviderType.ANTHROPIC)
        assert service.get_restriction_summary() == {"anthropic": ["sonnet"]}

        assert isinstance(ModelProviderRegistry.get_provider_for_model("sonnet"), AnthropicProvider)
        assert ModelProviderRegistry.get_provider_for_model("opus") is None
        available = ModelProviderRegistry.get_available_models(respect_restrictions=True)
        assert "claude-sonnet-5-5" in available
        assert "claude-opus-5-5" not in available
        assert set(available.values()) == {ProviderType.ANTHROPIC}


def test_server_validates_the_anthropic_allow_list(caplog):
    env = {"ANTHROPIC_API_KEY": "test-key", "ANTHROPIC_ALLOWED_MODELS": "sonnet,not-a-claude"}
    with patch.dict(os.environ, env, clear=True), caplog.at_level(logging.WARNING):
        _configure()
    assert "Model 'not-a-claude' in ANTHROPIC_ALLOWED_MODELS is not a recognized anthropic model" in caplog.text


def test_restriction_note_names_the_anthropic_allow_list():
    from tools.chat import ChatTool

    with patch.dict(os.environ, {"ANTHROPIC_ALLOWED_MODELS": "sonnet,haiku"}):
        note = ChatTool()._get_restriction_note()
    assert note is not None and "Anthropic: haiku, sonnet" in note
