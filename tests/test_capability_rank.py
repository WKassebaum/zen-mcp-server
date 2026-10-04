"""Capability rank: no upper clamp, and media breadth only breaks ties when picking media-capable models.

The rank orders the auto-mode "Top models" hint, listmodels and the capable models a media refusal suggests.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.anthropic import AnthropicProvider
from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ModelCapabilities, ProviderType
from providers.xai import XAIModelProvider
from utils.media import MediaKind, classify_media, format_media_error

PDF = frozenset({MediaKind.PDF})
ZEBRA_PDF = str(Path(__file__).parent / "fixtures" / "media" / "zebra.pdf")

# Every feature bonus a flagship can earn, so only intelligence_score differs below.
FLAGSHIP = {
    "context_window": 1_048_576,
    "max_output_tokens": 65_536,
    "supports_extended_thinking": True,
    "supports_function_calling": True,
    "supports_json_mode": True,
    "supports_images": True,
}


def _caps(name: str = "m", **fields) -> ModelCapabilities:
    return ModelCapabilities(provider=ProviderType.GOOGLE, model_name=name, friendly_name=name, **fields)


def _ranked(providers) -> list[tuple[int, str]]:
    """(rank, canonical name) across the providers' catalogs, sorted the way every rank sort site does."""
    rows = [
        (caps.get_effective_capability_rank(), name)
        for provider in providers
        for name, caps in provider.get_all_model_capabilities().items()
    ]
    return sorted(rows, key=lambda row: (-row[0], row[1]))


def test_score_20_outranks_19_when_everything_else_is_equal():
    top = _caps(intelligence_score=20, **FLAGSHIP).get_effective_capability_rank()
    next_best = _caps(intelligence_score=19, **FLAGSHIP).get_effective_capability_rank()
    assert top > next_best > 100


def test_native_catalog_top_five_are_the_20_score_flagships():
    providers = [
        cls(api_key="test-key")
        for cls in (GeminiModelProvider, OpenAIModelProvider, AnthropicProvider, XAIModelProvider)
    ]
    top_five = [name for _rank, name in _ranked(providers)[:5]]
    assert set(top_five) == {"claude-fable-5-1", "gpt-6-astra", "gemini-3.1-pro-preview", "gpt-6-sol", "grok-4.7"}
    assert not any(name.startswith("claude-opus-4") for name in top_five)


class _MediaProvider:
    """Just enough provider for find_media_capable_models: an encoder for every kind and fixed capabilities."""

    MEDIA_KINDS = frozenset(MediaKind)
    MEDIA_AUTO_ROUTING = True

    def __init__(self, *capabilities: ModelCapabilities):
        self._capabilities = {caps.model_name: caps for caps in capabilities}

    def get_capabilities(self, name: str) -> ModelCapabilities:
        return self._capabilities[name]


def test_media_breadth_breaks_ties_only_in_media_capable_selection():
    provider = _MediaProvider(
        _caps("a-pdf-only", intelligence_score=15, supports_pdf=True),
        _caps("b-pdf-and-video", intelligence_score=15, supports_pdf=True, supports_video=True),
        _caps("c-pdf-and-json", intelligence_score=15, supports_pdf=True, supports_json_mode=True),
    )
    available = dict.fromkeys(provider._capabilities, ProviderType.GOOGLE)
    with (
        patch.object(ModelProviderRegistry, "get_available_models", return_value=available),
        patch.object(ModelProviderRegistry, "get_provider", return_value=provider),
    ):
        picks = ModelProviderRegistry.find_media_capable_models(PDF)
    # Rank first (JSON mode is a rank bonus, video is not), then the model taking more media kinds, then the name.
    assert picks == ["c-pdf-and-json", "b-pdf-and-video", "a-pdf-only"]


def test_media_tie_break_counts_only_kinds_the_provider_can_send():
    provider = _MediaProvider(
        _caps("a-pdf", intelligence_score=15, supports_pdf=True),
        _caps("b-pdf-flagged-video", intelligence_score=15, supports_pdf=True, supports_video=True),
    )
    provider.MEDIA_KINDS = frozenset({MediaKind.PDF})  # its encoder cannot send the video the flag claims
    available = dict.fromkeys(provider._capabilities, ProviderType.GOOGLE)
    with (
        patch.object(ModelProviderRegistry, "get_available_models", return_value=available),
        patch.object(ModelProviderRegistry, "get_provider", return_value=provider),
    ):
        picks = ModelProviderRegistry.find_media_capable_models(PDF)
    assert picks == ["a-pdf", "b-pdf-flagged-video"]  # equal: the name decides


def test_rank_models_skips_names_whose_lookup_raises():
    provider = OpenAIModelProvider(api_key="test-key")
    real_lookup = provider.get_capabilities

    def lookup(name):
        if name == "broken":
            raise AttributeError("no registry entry")
        if name == "unknown":
            raise ValueError("unsupported model")
        return real_lookup(name)

    with patch.object(provider, "get_capabilities", side_effect=lookup):
        assert [caps.model_name for caps in provider.rank_models(["broken", "gpt-5.5", "unknown"])] == ["gpt-5.5"]


@pytest.fixture
def gemini_anthropic_openai_keys():
    """Register exactly the Gemini, Anthropic and OpenAI providers, as the MCP server would for those keys."""
    import utils.model_restrictions
    from server import configure_providers

    def clear():
        ModelProviderRegistry.clear_cache()
        for provider_type in list(ProviderType):
            ModelProviderRegistry.unregister_provider(provider_type)
        utils.model_restrictions._restriction_service = None

    env = dict.fromkeys(("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"), "test-key")
    with patch.dict(os.environ, env, clear=True):
        clear()
        configure_providers()
        yield
    clear()  # conftest's autouse fixture re-registers Google/OpenAI/xAI for later tests


def test_pdf_refusal_suggests_current_flagships_not_older_opus(gemini_anthropic_openai_keys):
    capable = ModelProviderRegistry.find_media_capable_models(PDF)
    media = classify_media([ZEBRA_PDF])[1]
    message = format_media_error("o3-mini", PDF, media, capable)

    assert len(capable) == 5
    assert "claude-fable-5-1" in capable
    assert "claude-opus-4" not in message
