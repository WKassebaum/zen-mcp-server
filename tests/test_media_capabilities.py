import json

from providers.registries.gemini import GeminiModelRegistry
from providers.shared import ModelCapabilities, ProviderType
from utils.media import MediaKind


def _caps(**flags):
    return ModelCapabilities(provider=ProviderType.GOOGLE, model_name="m", friendly_name="M", **flags)


def test_media_flags_default_false():
    caps = _caps()
    assert caps.supported_media_kinds() == frozenset()


def test_supported_media_kinds():
    caps = _caps(supports_pdf=True, supports_video=True)
    assert caps.supported_media_kinds() == frozenset({MediaKind.PDF, MediaKind.VIDEO})


def test_media_flags_leave_rank_unchanged():
    # Media flags only break ties in ModelProviderRegistry.find_media_capable_models (tests/test_capability_rank.py).
    base = _caps(intelligence_score=15).get_effective_capability_rank()
    richer = _caps(intelligence_score=15, supports_pdf=True, supports_audio=True, supports_video=True)
    assert richer.get_effective_capability_rank() == base


def test_flagship_rank_is_not_clamped_and_ignores_media_flags():
    # 19 * 5, plus 3 for a 1M context, 2 output, 3 thinking, and 1 each for functions, JSON and images.
    flagship = {
        "intelligence_score": 19,
        "context_window": 1_048_576,
        "max_output_tokens": 65_536,
        "supports_extended_thinking": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_images": True,
    }
    assert _caps(**flagship).get_effective_capability_rank() == 106
    with_media = _caps(**flagship, supports_pdf=True, supports_audio=True, supports_video=True)
    assert with_media.get_effective_capability_rank() == 106


def test_registry_loads_media_flags_from_catalog(tmp_path):
    catalog = tmp_path / "gemini_models.json"
    catalog.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "model_name": "test-media-model",
                        "context_window": 1_000_000,
                        "max_output_tokens": 8_192,
                        "supports_pdf": True,
                        "supports_audio": True,
                    }
                ]
            }
        )
    )

    caps = GeminiModelRegistry(config_path=str(catalog)).get_capabilities("test-media-model")

    assert caps is not None
    assert caps.provider == ProviderType.GOOGLE
    assert caps.supports_pdf is True
    assert caps.supports_audio is True
    assert caps.supports_video is False
    assert caps.supported_media_kinds() == frozenset({MediaKind.PDF, MediaKind.AUDIO})
