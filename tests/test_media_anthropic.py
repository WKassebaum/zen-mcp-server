"""Anthropic encoder: PDFs as native base64 document blocks ahead of the prompt text."""

import base64
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from providers.anthropic import AnthropicProvider
from utils.media import MediaKind, MediaNotSupportedError, base64_size, classify_media

FIXTURES = Path(__file__).parent / "fixtures" / "media"
PDF, MP4 = (str(FIXTURES / n) for n in ("zebra.pdf", "otter.mp4"))
MODEL = "sonnet"


def _client(text="ZEBRA-42"):
    client = MagicMock()
    stream = MagicMock()
    stream.text_stream = [text]
    stream.get_final_message.return_value = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=1500, output_tokens=4), stop_reason="end_turn"
    )
    client.messages.stream.return_value.__enter__.return_value = stream
    return client


def _provider():
    provider = AnthropicProvider(api_key="test-key")
    provider._client = _client()  # never reach the real SDK client
    return provider


def _sent(provider):
    return provider._client.messages.stream.call_args.kwargs


def _document_block(path):
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}


def test_anthropic_declares_pdf_only():
    assert AnthropicProvider.MEDIA_KINDS == frozenset({MediaKind.PDF})


def test_pdf_is_sent_as_a_document_block_before_the_prompt():
    provider = _provider()
    provider.generate_content("What code?", MODEL, system_prompt="Be terse.", media=classify_media([PDF])[1])
    sent = _sent(provider)
    assert sent["messages"] == [
        {"role": "user", "content": [_document_block(PDF), {"type": "text", "text": "What code?"}]}
    ]
    assert sent["system"] == "Be terse."


def test_two_pdfs_keep_their_input_order(tmp_path):
    first, second = tmp_path / "b-first.pdf", tmp_path / "a-second.pdf"
    shutil.copy(PDF, first)
    second.write_bytes(Path(PDF).read_bytes().replace(b"ZEBRA", b"HORSE"))
    provider = _provider()
    response = provider.generate_content("Compare", MODEL, media=classify_media([str(first), str(second)])[1])
    content = _sent(provider)["messages"][0]["content"]
    assert content == [_document_block(first), _document_block(second), {"type": "text", "text": "Compare"}]
    assert [m["name"] for m in response.metadata["media_attached"]] == ["b-first.pdf", "a-second.pdf"]


def test_media_attached_metadata():
    response = _provider().generate_content("What code?", MODEL, media=classify_media([PDF])[1])
    assert response.metadata["media_attached"] == [
        {"name": "zebra.pdf", "kind": "pdf", "bytes": 587, "transport": "inline"}
    ]
    assert response.content == "ZEBRA-42"


def test_images_follow_the_prompt_text_in_a_media_request():
    provider = _provider()
    provider.generate_content("Compare", MODEL, images=["data:image/png;base64,aW1n"], media=classify_media([PDF])[1])
    content = _sent(provider)["messages"][0]["content"]
    assert [part["type"] for part in content] == ["document", "text", "image"]
    assert content[2]["source"]["data"] == "aW1n"


def test_media_free_request_is_unchanged():
    provider = _provider()
    response = provider.generate_content("hi", MODEL, system_prompt="SYS")
    sent = _sent(provider)
    assert sent["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
    assert sent["system"] == "SYS"
    assert set(sent) == {"model", "messages", "max_tokens", "system"}  # no temperature: Sonnet 5.5 is adaptive
    assert "media_attached" not in response.metadata


def test_empty_media_list_is_a_media_free_request():
    provider = _provider()
    response = provider.generate_content("hi", MODEL, media=[])
    assert _sent(provider)["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
    assert "media_attached" not in response.metadata


def test_video_is_refused_before_any_call():
    provider = _provider()
    with pytest.raises(MediaNotSupportedError, match="otter.mp4"):
        provider.generate_content("Describe", MODEL, media=classify_media([MP4])[1])
    provider._client.messages.stream.assert_not_called()


def test_request_over_the_cap_is_refused_before_any_call():
    provider = _provider()
    # The PDF alone fits under the cap; the PDF plus a 100-character prompt does not.
    with patch.object(AnthropicProvider, "MEDIA_REQUEST_MAX_BYTES", base64_size(587) + 10):
        with pytest.raises(MediaNotSupportedError, match="anthropic"):
            provider.generate_content("x" * 100, MODEL, media=classify_media([PDF])[1])
    provider._client.messages.stream.assert_not_called()


def test_system_prompt_counts_toward_the_cap():
    provider = _provider()
    with patch.object(AnthropicProvider, "MEDIA_REQUEST_MAX_BYTES", base64_size(587) + 10):
        with pytest.raises(MediaNotSupportedError):
            provider.generate_content("q", MODEL, system_prompt="s" * 100, media=classify_media([PDF])[1])
    provider._client.messages.stream.assert_not_called()


def test_bytes_are_read_from_the_validated_source_path(tmp_path):
    # ``path`` is the caller's string; only ``source_path`` was validated, so it is the one read.
    real = tmp_path / "real.pdf"
    shutil.copy(PDF, real)
    (attachment,) = classify_media([str(real)])[1]
    moved = SimpleNamespace(
        path=str(tmp_path / "missing.pdf"),
        name="missing.pdf",
        kind=attachment.kind,
        mime_type=attachment.mime_type,
        size_bytes=attachment.size_bytes,
        source_path=attachment.source_path,
    )
    provider = _provider()
    provider.generate_content("q", MODEL, media=[moved])
    assert _sent(provider)["messages"][0]["content"][0] == _document_block(real)
