"""Auto-mode picks per tool category when an allow-list, or the set of configured keys, narrows the choice.

Each case registers exactly the providers the MCP server would for ``env`` and asks the registry for its pick in
every category. No provider is called.
"""

import os
from unittest.mock import patch

import pytest

from providers.registry import ModelProviderRegistry
from providers.shared import ProviderType
from tools.models import ToolModelCategory

EXTENDED = ToolModelCategory.EXTENDED_REASONING
BALANCED = ToolModelCategory.BALANCED
FAST = ToolModelCategory.FAST_RESPONSE


def _clear_providers():
    import utils.model_restrictions

    ModelProviderRegistry.clear_cache()
    for provider_type in list(ProviderType):
        ModelProviderRegistry.unregister_provider(provider_type)
    utils.model_restrictions._restriction_service = None


@pytest.fixture(autouse=True)
def _restore_registry():
    yield
    _clear_providers()  # conftest's autouse fixture re-registers Google/OpenAI/xAI for later tests


def _picks(env: dict[str, str]) -> dict[ToolModelCategory, str]:
    """Each category's auto-mode pick, plus a check that the picked name resolves to an allowed model."""
    from server import configure_providers

    with patch.dict(os.environ, env, clear=True):
        _clear_providers()
        configure_providers()
        picks = {
            category: ModelProviderRegistry.get_preferred_fallback_model(category) for category in ToolModelCategory
        }
        for model in picks.values():
            assert ModelProviderRegistry.get_provider_for_model(model) is not None, model
    return picks


# ---------------------------------------------------------------------------
# Gemini: candidates rank by intelligence_score, not by reverse string order
# ---------------------------------------------------------------------------


def test_gemini_flash_beats_flash_lite_when_both_are_allowed():
    picks = _picks({"GEMINI_API_KEY": "test-key", "GOOGLE_ALLOWED_MODELS": "gemini-3.5-flash,gemini-3.5-flash-lite"})
    assert picks[EXTENDED] == "gemini-3.5-flash"
    assert picks[BALANCED] == "gemini-3.5-flash"
    assert picks[FAST] == "gemini-3.5-flash"


def test_gemini_alias_only_allow_list_still_routes_to_the_better_model():
    picks = _picks({"GEMINI_API_KEY": "test-key", "GOOGLE_ALLOWED_MODELS": "flash-3.5,flashlite"})
    assert picks[EXTENDED] == "gemini-3.5-flash"
    assert picks[BALANCED] == "gemini-3.5-flash"


def test_gemini_alias_does_not_outrank_a_newer_model():
    # Reverse string order put the alias "gemini3.5-flash" above "gemini-3.8-flash" ('3' sorts after '-').
    picks = _picks({"GEMINI_API_KEY": "test-key", "GOOGLE_ALLOWED_MODELS": "gemini3.5-flash,gemini-3.8-flash"})
    assert picks[EXTENDED] == "gemini-3.8-flash"
    assert picks[BALANCED] == "gemini-3.8-flash"
    assert picks[FAST] == "gemini-3.8-flash"
