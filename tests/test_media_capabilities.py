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
