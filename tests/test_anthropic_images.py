"""Anthropic encoder: images (file paths or data URLs) become base64 image blocks with their real MIME type."""

import base64
import struct
import zlib
from types import SimpleNamespace
from unittest.mock import MagicMock

from providers.anthropic import AnthropicProvider

MODEL = "sonnet"


def _png_bytes() -> bytes:
    """A valid 1x1 RGB PNG."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\xff\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


def _provider():
    provider = AnthropicProvider(api_key="test-key")
    client = MagicMock()
    stream = MagicMock()
    stream.text_stream = ["ok"]
    stream.get_final_message.return_value = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=10, output_tokens=1), stop_reason="end_turn"
    )
    client.messages.stream.return_value.__enter__.return_value = stream
    provider._client = client  # never reach the real SDK client
    return provider


def _sent(provider):
    return provider._client.messages.stream.call_args.kwargs


def _image_block(data: bytes, media_type: str) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode()},
    }


def test_png_file_path_is_read_and_base64_encoded(tmp_path):
    png = tmp_path / "pixel.png"
    png.write_bytes(_png_bytes())
    provider = _provider()
    provider.generate_content("Describe", MODEL, images=[str(png)])
    content = _sent(provider)["messages"][0]["content"]
    assert content == [{"type": "text", "text": "Describe"}, _image_block(_png_bytes(), "image/png")]


def test_jpeg_data_url_keeps_its_mime_type():
    data_url = "data:image/jpeg;base64," + base64.b64encode(JPEG_BYTES).decode()
    provider = _provider()
    provider.generate_content("Describe", MODEL, images=[data_url])
    content = _sent(provider)["messages"][0]["content"]
    assert content == [{"type": "text", "text": "Describe"}, _image_block(JPEG_BYTES, "image/jpeg")]


def test_invalid_image_is_skipped_with_a_warning(tmp_path, caplog):
    provider = _provider()
    with caplog.at_level("WARNING", logger="providers.anthropic"):
        provider.generate_content("Describe", MODEL, images=[str(tmp_path / "missing.png")])
    assert _sent(provider)["messages"] == [{"role": "user", "content": [{"type": "text", "text": "Describe"}]}]
    assert "missing.png" in caplog.text


def test_text_only_request_is_unchanged():
    provider = _provider()
    provider.generate_content("hi", MODEL, system_prompt="SYS", max_output_tokens=100)
    assert _sent(provider) == {
        "model": "claude-sonnet-5-5",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        "max_tokens": 100,
        "system": "SYS",
    }
