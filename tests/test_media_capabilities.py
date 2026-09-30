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


def test_media_flags_raise_rank():
    base = _caps(intelligence_score=15).get_effective_capability_rank()
    richer = _caps(intelligence_score=15, supports_pdf=True, supports_audio=True, supports_video=True)
    assert richer.get_effective_capability_rank() == base + 3


def test_media_flags_cannot_lift_rank_past_clamp():
    # Known limitation: the rank is clamped to 100, so a model already saturated by its
    # other features gains nothing from media flags (19 * 5 + 3 flags alone is only 98).
    flagship = {
        "intelligence_score": 19,
        "context_window": 1_048_576,
        "max_output_tokens": 65_536,
        "supports_extended_thinking": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_images": True,
    }
    assert _caps(**flagship).get_effective_capability_rank() == 100
    with_media = _caps(**flagship, supports_pdf=True, supports_audio=True, supports_video=True)
    assert with_media.get_effective_capability_rank() == 100


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
