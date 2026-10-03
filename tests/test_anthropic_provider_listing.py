"""listmodels and version report the native Anthropic provider like the other native providers."""

import json
import os
from unittest.mock import patch

import pytest

from providers.registry import ModelProviderRegistry
from providers.shared import ProviderType
from tools.listmodels import ListModelsTool
from tools.version import VersionTool


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


async def _listmodels_content(env):
    with patch.dict(os.environ, env, clear=True):
        _configure()
        result = await ListModelsTool().execute({})
    return json.loads(result[0].text)


@pytest.mark.asyncio
async def test_listmodels_with_only_an_anthropic_key_reports_anthropic_configured():
    response = await _listmodels_content({"ANTHROPIC_API_KEY": "test-key", "DEFAULT_MODEL": "auto"})
    content = response["content"]

    assert "## Anthropic ✅" in content
    assert "`claude-opus-5-5`" in content
    assert "`opus` → `claude-opus-5-5`" in content
    assert "**Configured Providers**: 1" in content
    assert response["metadata"]["configured_providers"] == 1
    assert "Google Gemini ❌" in content
    assert "OpenRouter ❌" in content


@pytest.mark.asyncio
async def test_listmodels_without_an_anthropic_key_names_the_key_to_set():
    response = await _listmodels_content({"GEMINI_API_KEY": "test-key", "DEFAULT_MODEL": "auto"})
    content = response["content"]

    assert "## Anthropic ❌" in content
    assert "Not configured (set ANTHROPIC_API_KEY)" in content


@pytest.mark.asyncio
async def test_listmodels_lists_native_claude_alongside_openrouter():
    env = {"ANTHROPIC_API_KEY": "test-key", "OPENROUTER_API_KEY": "test-key", "DEFAULT_MODEL": "auto"}
    content = (await _listmodels_content(env))["content"]

    native = content.split("## Anthropic ✅", 1)[1].split("## OpenRouter", 1)[0]
    assert "`claude-opus-5-5`" in native
    assert "**Configured Providers**: 2" in content


@pytest.mark.asyncio
async def test_version_reports_anthropic_configured():
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key", "DEFAULT_MODEL": "auto"}, clear=True):
        _configure()
        with patch("tools.version.fetch_github_version", return_value=None):  # no network
            result = await VersionTool().execute({})
    content = json.loads(result[0].text)["content"]

    assert "- **Anthropic**: ✅ Configured" in content
    assert "- **Google Gemini**: ❌ Not configured" in content
