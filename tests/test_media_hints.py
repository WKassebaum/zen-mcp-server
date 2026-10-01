"""Messages for media no available model can take: which key to configure, or why a configured provider cannot."""

from pathlib import Path
from unittest.mock import patch

import pytest

import utils.model_restrictions
from providers.gemini import GeminiModelProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ModelCapabilities
from utils.media import MediaKind, classify_media, format_media_error, providers_hint

MP4 = str(Path(__file__).parent / "fixtures" / "media" / "otter.mp4")
VIDEO = frozenset({MediaKind.VIDEO})
AUDIO = frozenset({MediaKind.AUDIO})


@pytest.fixture
def fresh_restrictions(monkeypatch):
    """Let a test change *_ALLOWED_MODELS: the restriction service caches the env on first use."""
    monkeypatch.setattr(utils.model_restrictions, "_restriction_service", None)


def test_hint_names_key_when_provider_is_not_configured(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    ModelProviderRegistry.clear_cache()
    try:
        assert providers_hint(VIDEO) == "configure GEMINI_API_KEY"
    finally:
        ModelProviderRegistry.clear_cache()


def test_hint_when_configured_provider_has_no_encoder():
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset()):
        hint = providers_hint(VIDEO)
    assert hint.startswith("GEMINI_API_KEY is configured") and "cannot send video input yet" in hint


def test_hint_blames_allow_list_when_restricted(monkeypatch, fresh_restrictions):
    # gemini-2.5-flash takes pdf and video but not audio (tests/media_probe_matrix.py), so this
    # allow-list really does exclude every model that can take audio.
    monkeypatch.setenv("GOOGLE_ALLOWED_MODELS", "gemini-2.5-flash")
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        hint = providers_hint(AUDIO)
    assert not hint.startswith("configure")
    assert "GEMINI_API_KEY is configured, but GOOGLE_ALLOWED_MODELS excludes" in hint


def test_hint_when_no_model_in_the_catalog_takes_the_mix(fresh_restrictions):
    # Pretend every Gemini model takes PDF only, so no model takes the audio/pdf/video mix at all.
    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)),
        patch.object(ModelCapabilities, "supported_media_kinds", return_value=frozenset({MediaKind.PDF})),
    ):
        hint = providers_hint(frozenset(MediaKind))
    assert hint == "GEMINI_API_KEY is configured, but none of its models takes audio/pdf/video input in one request"


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
    assert "No available model supports it: GEMINI_API_KEY is configured" in message
