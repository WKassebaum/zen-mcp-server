"""Every provider refuses media it cannot encode, so media can never be dropped silently."""

from pathlib import Path
from unittest.mock import patch

import pytest

from providers.anthropic import AnthropicProvider
from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.xai import XAIModelProvider
from utils.media import MEDIA_MAX_BYTES, MediaKind, MediaNotSupportedError, classify_media

FIXTURES = Path(__file__).parent / "fixtures" / "media"
MP4 = str(FIXTURES / "otter.mp4")


def _media():
    return classify_media([MP4])[1]


@pytest.mark.parametrize(
    "provider_cls", [AnthropicProvider, OpenAIModelProvider, XAIModelProvider, GeminiModelProvider]
)
def test_providers_without_encoder_reject_media(provider_cls):
    provider = provider_cls(api_key="test-key")
    with pytest.raises(MediaNotSupportedError, match="otter.mp4"):
        provider.ensure_media_encodable(_media())


def test_media_given_as_a_one_shot_iterator_is_still_checked():
    # The size check must not consume the iterator and leave nothing for the kind check.
    with pytest.raises(MediaNotSupportedError, match="otter.mp4"):
        XAIModelProvider(api_key="test-key").ensure_media_encodable(iter(_media()))


def test_empty_media_is_always_fine():
    XAIModelProvider(api_key="test-key").ensure_media_encodable([])
    XAIModelProvider(api_key="test-key").ensure_media_encodable(None)


def test_oversized_media_is_refused_even_with_an_encoder(tmp_path):
    huge = tmp_path / "huge.mp4"
    with huge.open("wb") as handle:
        handle.write(b"\x00\x00\x00\x10ftypisom\x00\x00\x02\x00")
        handle.truncate(MEDIA_MAX_BYTES + 1)  # sparse: nothing real is written
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        with pytest.raises(MediaNotSupportedError, match="huge.mp4"):
            GeminiModelProvider(api_key="test-key").ensure_media_encodable(classify_media([str(huge)])[1])
