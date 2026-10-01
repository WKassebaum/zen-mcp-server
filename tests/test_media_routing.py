"""Auto mode picks only models whose flags and provider encoder cover the attached media."""

from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.registry import ModelProviderRegistry
from tools.models import ToolModelCategory
from utils.media import MediaKind, MediaNotSupportedError

ALL = frozenset(MediaKind)


@pytest.fixture
def gemini_encodes_media():
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", ALL):
        yield


def test_auto_mode_without_media_is_unchanged():
    before = ModelProviderRegistry.get_preferred_fallback_model(ToolModelCategory.FAST_RESPONSE)
    after = ModelProviderRegistry.get_preferred_fallback_model(
        ToolModelCategory.FAST_RESPONSE, required_media=frozenset()
    )
    assert before == after


def test_auto_mode_with_video_picks_capable_model(gemini_encodes_media):
    model = ModelProviderRegistry.get_preferred_fallback_model(
        ToolModelCategory.FAST_RESPONSE, required_media=frozenset({MediaKind.VIDEO})
    )
    provider = ModelProviderRegistry.get_provider_for_model(model)
    assert MediaKind.VIDEO in provider.get_capabilities(model).supported_media_kinds()


def test_auto_mode_with_media_and_no_encoder_raises():
    # Gemini has flags from Task 6 but no encoder until Task 15 (MEDIA_KINDS empty) -> nothing can serve it.
    with pytest.raises(MediaNotSupportedError, match="GEMINI_API_KEY"):
        ModelProviderRegistry.get_preferred_fallback_model(
            ToolModelCategory.FAST_RESPONSE, required_media=frozenset({MediaKind.VIDEO})
        )


def test_media_uses_first_available_when_no_provider_states_a_preference(gemini_encodes_media):
    # OpenRouter, Custom, DIAL and Azure return no preference; a capable first-available model must still win.
    with patch.object(GeminiModelProvider, "get_preferred_model", return_value=None):
        model = ModelProviderRegistry.get_preferred_fallback_model(
            ToolModelCategory.FAST_RESPONSE, required_media=frozenset({MediaKind.PDF})
        )
    provider = ModelProviderRegistry.get_provider_for_model(model)
    assert MediaKind.PDF in provider.get_capabilities(model).supported_media_kinds()


def test_find_media_capable_models(gemini_encodes_media):
    models = ModelProviderRegistry.find_media_capable_models(frozenset({MediaKind.PDF}), limit=3)
    assert 0 < len(models) <= 3
    assert all(m.startswith("gemini") for m in models)
    assert len(models) == len(set(models))
    for name in models:  # canonical names only, never aliases such as "flash"
        assert ModelProviderRegistry.get_provider_for_model(name).get_capabilities(name).model_name == name
