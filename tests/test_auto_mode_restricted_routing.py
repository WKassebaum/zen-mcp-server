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


# ---------------------------------------------------------------------------
# OpenAI / xAI: with no allowed model on the FAST list, FAST_RESPONSE takes the lowest-ranked one
# ---------------------------------------------------------------------------


def test_openai_fast_response_uses_the_small_allowed_model():
    picks = _picks({"OPENAI_API_KEY": "test-key", "OPENAI_ALLOWED_MODELS": "gpt-5-nano,gpt-6-astra"})
    assert picks[FAST] == "gpt-5-nano"
    assert picks[EXTENDED] == "gpt-6-astra"


def test_openai_fast_response_falls_back_to_the_lowest_ranked_model():
    # Neither model is on the FAST list; the old fallback returned allowed_models[0], the most capable.
    picks = _picks({"OPENAI_API_KEY": "test-key", "OPENAI_ALLOWED_MODELS": "gpt-6-astra,gpt-5.6-terra"})
    assert picks[FAST] == "gpt-5.6-terra"


@pytest.mark.parametrize(
    "allowed,expected",
    [
        ("gpt-5.5-pro,gpt-5.6-terra", "gpt-5.6-terra"),
        ("o3,gpt-4.1", "gpt-4.1"),
    ],
)
def test_openai_balanced_list_covers_terra_and_gpt_4_1(allowed, expected):
    picks = _picks({"OPENAI_API_KEY": "test-key", "OPENAI_ALLOWED_MODELS": allowed})
    assert picks[BALANCED] == expected


def test_xai_fast_response_falls_back_to_an_allowed_canonical_model():
    # grok-4.20-0309-reasoning is the only xAI model on no FAST list.
    picks = _picks({"XAI_API_KEY": "test-key", "XAI_ALLOWED_MODELS": "grok-4.20-0309-reasoning"})
    assert picks[FAST] == "grok-4.20-0309-reasoning"


def test_xai_fast_response_fallback_skips_aliases_and_takes_the_lowest_rank():
    # Called directly: through the registry an allowed alias always brings its canonical name, which the
    # FAST list matches. Aliases are not on the list, so this reaches the fallback with the list in rank order.
    from providers.xai import XAIModelProvider

    provider = XAIModelProvider(api_key="test-key")
    assert provider.get_preferred_model(FAST, ["grok4.7", "grok4.20"]) == "grok-4.20-0309-reasoning"


def test_anthropic_fast_response_falls_back_to_the_lowest_ranked_model():
    # Same fallback as OpenAI and xAI: neither model is on Anthropic's FAST list (Haiku, Sonnet 5.5, Sonnet 4.6).
    picks = _picks({"ANTHROPIC_API_KEY": "test-key", "ANTHROPIC_ALLOWED_MODELS": "claude-fable-5-1,claude-opus-4-8"})
    assert picks[FAST] == "claude-opus-4-8"
    assert picks[EXTENDED] == "claude-fable-5-1"


@pytest.mark.parametrize(
    "allowed,expected",
    [
        ("gpt-5.5,gpt-5.5-pro", "gpt-5.5"),  # same rank: the premium -pro model used to win the name tie-break
        ("gpt-6-astra,gpt-5.4-pro", "gpt-6-astra"),  # gpt-5.4-pro ranks lower but is premium
        ("gpt-5.5-pro", "gpt-5.5-pro"),  # nothing else allowed
        ("gpt-5.5,o3", "gpt-5.5"),  # o3 scores 14, below the FAST_RESPONSE floor
    ],
)
def test_openai_fast_response_fallback_skips_premium_and_below_floor_models(allowed, expected):
    picks = _picks({"OPENAI_API_KEY": "test-key", "OPENAI_ALLOWED_MODELS": allowed})
    assert picks[FAST] == expected


# ---------------------------------------------------------------------------
# OpenRouter, Azure, DIAL and Custom state no preference: the first provider with allowed models picks by rank
# ---------------------------------------------------------------------------


def test_openrouter_allow_list_sends_chat_to_the_cheaper_capable_model():
    # The docstring example: chat used to go to Opus 5.5 (alphabetical). mistral-large scores 14, below the
    # FAST_RESPONSE floor of 15. Opus 5.5 and Sonnet 5.5 rank the same (106): Sonnet wins only on the name tie-break.
    picks = _picks({"OPENROUTER_API_KEY": "test-key", "OPENROUTER_ALLOWED_MODELS": "opus,sonnet,mistral"})
    assert picks == {
        EXTENDED: "anthropic/claude-opus-5.5",
        BALANCED: "anthropic/claude-opus-5.5",
        FAST: "anthropic/claude-sonnet-5.5",
    }


def test_openrouter_chat_skips_premium_models():
    # o3-pro ranks below Sonnet 5.5 and clears the floor, but it is a premium model
    picks = _picks(
        {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_ALLOWED_MODELS": "anthropic/claude-sonnet-5.5,openai/o3-pro"}
    )
    assert picks[FAST] == "anthropic/claude-sonnet-5.5"


def test_fast_response_takes_the_lowest_ranked_model_when_none_reaches_the_floor():
    picks = _picks({"OPENROUTER_API_KEY": "test-key", "OPENROUTER_ALLOWED_MODELS": "flash-2.5,gpt5nano"})
    assert picks[FAST] == "openai/gpt-5-nano"
    assert picks[EXTENDED] == "google/gemini-2.5-flash"


def test_custom_endpoint_keeps_every_category_ahead_of_openrouter():
    # Custom comes before OpenRouter in PROVIDER_PRIORITY_ORDER and has allowed models, so it decides even though
    # it states no preference. An OpenRouterProvider.get_preferred_model override once moved FAST_RESPONSE here
    # from llama3.2 to openai/gpt-6-luna.
    picks = _picks({"OPENROUTER_API_KEY": "test-key", "CUSTOM_API_URL": "http://localhost:11434/v1"})
    assert picks == {EXTENDED: "llama3.2", BALANCED: "llama3.2", FAST: "llama3.2"}
