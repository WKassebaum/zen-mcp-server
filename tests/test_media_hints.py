"""Messages for media no available model can take: which key to configure, or why a configured provider cannot."""

from pathlib import Path
from unittest.mock import patch

import pytest

import utils.model_restrictions
from providers.anthropic import AnthropicProvider
from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.openrouter import OpenRouterProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ModelCapabilities, ProviderType
from utils.media import MEDIA_PROVIDERS, MediaKind, classify_media, format_media_error, providers_hint

MP4 = str(Path(__file__).parent / "fixtures" / "media" / "otter.mp4")
VIDEO = frozenset({MediaKind.VIDEO})
AUDIO = frozenset({MediaKind.AUDIO})
PDF = frozenset({MediaKind.PDF})
ENCODERS = {
    "google": GeminiModelProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIModelProvider,
    "openrouter": OpenRouterProvider,
}


@pytest.fixture
def fresh_restrictions(monkeypatch):
    """Let a test change *_ALLOWED_MODELS: the restriction service caches the env on first use."""
    monkeypatch.setattr(utils.model_restrictions, "_restriction_service", None)


def test_hint_names_key_when_provider_is_not_configured(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    ModelProviderRegistry.clear_cache()
    try:
        assert providers_hint(VIDEO) == "configure GEMINI_API_KEY or OPENROUTER_API_KEY"
    finally:
        ModelProviderRegistry.clear_cache()


def test_hint_when_configured_provider_has_no_encoder():
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset()):
        hint = providers_hint(VIDEO)
    # OPENROUTER_API_KEY is unset in unit tests, so it is named first as a key to configure.
    assert (
        hint
        == "configure OPENROUTER_API_KEY; GEMINI_API_KEY is configured, but that provider cannot send video input yet"
    )


def test_hint_blames_allow_list_when_restricted(monkeypatch, fresh_restrictions):
    # gemini-2.5-flash takes pdf and video but not audio (tests/media_probe_matrix.py), so this
    # allow-list really does exclude every model that can take audio.
    monkeypatch.setenv("GOOGLE_ALLOWED_MODELS", "gemini-2.5-flash")
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        hint = providers_hint(AUDIO)
    assert hint.startswith("configure OPENROUTER_API_KEY; ")  # the only key left to configure
    assert "GEMINI_API_KEY is configured, but GOOGLE_ALLOWED_MODELS excludes" in hint


def test_hint_when_no_model_in_the_catalog_takes_the_mix(fresh_restrictions):
    # Pretend every Gemini model takes PDF only, so no model takes the audio/pdf/video mix at all.
    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)),
        patch.object(ModelCapabilities, "supported_media_kinds", return_value=frozenset({MediaKind.PDF})),
    ):
        hint = providers_hint(frozenset(MediaKind))
    assert hint == (
        "configure OPENROUTER_API_KEY; "
        "GEMINI_API_KEY is configured, but none of its models takes audio/pdf/video input in one request"
    )


def test_allow_list_is_not_blamed_when_no_model_takes_the_mix(monkeypatch, fresh_restrictions):
    monkeypatch.setenv("GOOGLE_ALLOWED_MODELS", "gemini-2.5-flash")
    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)),
        patch.object(ModelCapabilities, "supported_media_kinds", return_value=frozenset({MediaKind.PDF})),
    ):
        hint = providers_hint(AUDIO)
    assert "GOOGLE_ALLOWED_MODELS" not in hint
    assert "none of its models takes audio input" in hint


def test_format_media_error_lists_capable_models():
    media = classify_media([MP4])[1]
    message = format_media_error("o3", VIDEO, media, ["gemini-3.8-flash"])
    assert message == (
        "Model 'o3' cannot take video input (otter.mp4). "
        "Models available with your current keys that can: gemini-3.8-flash."
    )


def test_format_media_error_without_capable_models_gives_hint():
    media = classify_media([MP4])[1]
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset()):
        message = format_media_error("o3", VIDEO, media, [])
    assert "No available model supports it: configure OPENROUTER_API_KEY; GEMINI_API_KEY is configured" in message


@pytest.fixture
def no_media_keys(monkeypatch):
    """No Gemini, Anthropic, OpenAI or OpenRouter provider is available."""
    for key in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    ModelProviderRegistry.clear_cache()
    yield
    ModelProviderRegistry.clear_cache()


def test_pdf_hint_names_every_key_that_unlocks_pdf(no_media_keys):
    assert providers_hint(PDF) == (
        "configure GEMINI_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY or OPENROUTER_API_KEY"
    )


def test_audio_and_video_hints_name_gemini_and_openrouter(no_media_keys):
    assert providers_hint(AUDIO) == "configure GEMINI_API_KEY or OPENROUTER_API_KEY"
    assert providers_hint(VIDEO) == "configure GEMINI_API_KEY or OPENROUTER_API_KEY"


def test_media_providers_promise_only_what_the_encoders_send():
    # A hint must never send the user to a key whose provider would then refuse the file.
    assert {entry[0] for entry in MEDIA_PROVIDERS} == set(ENCODERS)
    for provider_value, _key_env, _allow_env, supported in MEDIA_PROVIDERS:
        assert supported == ENCODERS[provider_value].MEDIA_KINDS, provider_value


def test_media_providers_follow_the_provider_priority_order():
    order = [ProviderType(entry[0]) for entry in MEDIA_PROVIDERS]
    assert order == [p for p in ModelProviderRegistry.PROVIDER_PRIORITY_ORDER if p in order]


def _only_anthropic_configured(monkeypatch):
    anthropic = AnthropicProvider(api_key="test-key")
    monkeypatch.setattr(
        ModelProviderRegistry,
        "get_provider",
        classmethod(
            lambda cls, provider_type, force_new=False: anthropic if provider_type is ProviderType.ANTHROPIC else None
        ),
    )


def test_provider_without_an_allow_list_is_never_blamed_for_one(monkeypatch, fresh_restrictions):
    # A MEDIA_PROVIDERS entry with no *_ALLOWED_MODELS variable (None) must never be blamed for a restriction.
    # Every current entry has one, so pretend Anthropic does not.
    _only_anthropic_configured(monkeypatch)
    without_allow_list = tuple(
        (value, key, None if value == "anthropic" else allow, kinds) for value, key, allow, kinds in MEDIA_PROVIDERS
    )
    with (
        patch("utils.media.MEDIA_PROVIDERS", without_allow_list),
        patch.object(ModelCapabilities, "supported_media_kinds", return_value=PDF),
        patch.object(utils.model_restrictions.ModelRestrictionService, "has_restrictions", return_value=True),
    ):
        hint = providers_hint(PDF)
    assert "None" not in hint
    assert hint == "configure GEMINI_API_KEY or OPENAI_API_KEY or OPENROUTER_API_KEY"


def test_hint_blames_the_anthropic_allow_list(monkeypatch, fresh_restrictions):
    _only_anthropic_configured(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_ALLOWED_MODELS", "none-such")
    assert providers_hint(PDF) == (
        "configure GEMINI_API_KEY or OPENAI_API_KEY or OPENROUTER_API_KEY; "
        "ANTHROPIC_API_KEY is configured, but ANTHROPIC_ALLOWED_MODELS excludes every model that can take pdf input"
    )
