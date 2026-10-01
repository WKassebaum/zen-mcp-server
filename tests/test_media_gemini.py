"""Gemini encoder: inline media below the cap, Files API upload above it."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import providers.base
from providers.gemini import GeminiModelProvider
from utils.media import MediaKind, classify_media

FIXTURES = Path(__file__).parent / "fixtures" / "media"
PDF, WAV, MP4 = (str(FIXTURES / n) for n in ("zebra.pdf", "pelican.wav", "otter.mp4"))


def _provider():
    provider = GeminiModelProvider(api_key="test-key")
    fake_response = MagicMock(text="ok", candidates=[MagicMock(finish_reason=None)], usage_metadata=None)
    provider._client = MagicMock()
    provider._client.models.generate_content.return_value = fake_response
    return provider


def _sent(provider):
    return provider._client.models.generate_content.call_args.kwargs


def _file(name, state, mime_type="video/mp4", uri="u"):
    return SimpleNamespace(name=name, uri=uri, mime_type=mime_type, state=SimpleNamespace(name=state), error=None)


def test_gemini_declares_all_media_kinds():
    assert GeminiModelProvider.MEDIA_KINDS == frozenset(MediaKind)


def test_inline_media_layout():
    provider = _provider()
    media = classify_media([PDF, MP4])[1]
    response = provider.generate_content("What is shown?", "gemini-3.8-flash", system_prompt="SYS", media=media)
    sent = _sent(provider)
    parts = sent["contents"][0]["parts"]
    assert [p["inline_data"]["mime_type"] for p in parts[:2]] == ["application/pdf", "video/mp4"]
    assert parts[2] == {"text": "What is shown?"}  # system prompt is NOT concatenated into the text
    assert len(parts) == 3
    assert sent["config"].system_instruction == "SYS"
    assert [m["transport"] for m in response.metadata["media_attached"]] == ["inline", "inline"]
    assert [m["name"] for m in response.metadata["media_attached"]] == ["zebra.pdf", "otter.mp4"]


def test_media_free_layout_unchanged():
    provider = _provider()
    response = provider.generate_content("hello", "gemini-3.8-flash", system_prompt="SYS")
    sent = _sent(provider)
    assert sent["contents"][0]["parts"] == [{"text": "SYS\n\nhello"}]
    assert sent["config"].system_instruction is None
    assert response.metadata["media_attached"] == []


def test_images_follow_the_prompt_text_in_a_media_request(monkeypatch):
    provider = _provider()
    image_part = {"inline_data": {"mime_type": "image/png", "data": "aW1n"}}
    monkeypatch.setattr(provider, "_process_image", lambda path: image_part)
    provider.generate_content(
        "Compare", "gemini-3.8-flash", system_prompt="SYS", images=["shot.png"], media=classify_media([PDF])[1]
    )
    parts = _sent(provider)["contents"][0]["parts"]
    assert parts[0]["inline_data"]["mime_type"] == "application/pdf"
    assert parts[1:] == [{"text": "Compare"}, image_part]


def test_large_media_is_uploaded_and_named_in_metadata(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(GeminiModelProvider, "INLINE_MEDIA_MAX_BYTES", 1024)  # force upload of the 67 KB wav
    uploaded = _file("files/abc", "ACTIVE", mime_type="audio/wav", uri="https://gen.test/files/abc")
    provider._client.files.upload.return_value = uploaded
    response = provider.generate_content("Transcribe", "gemini-3.8-flash", media=classify_media([PDF, WAV])[1])
    parts = _sent(provider)["contents"][0]["parts"]
    # Input order is kept: the inline PDF first, then the uploaded WAV, then the prompt.
    assert parts[0]["inline_data"]["mime_type"] == "application/pdf"  # the 587-byte PDF still fits inline
    assert parts[1] == {"file_data": {"file_uri": "https://gen.test/files/abc", "mime_type": "audio/wav"}}
    assert parts[2] == {"text": "Transcribe"}
    upload_kwargs = provider._client.files.upload.call_args.kwargs
    assert upload_kwargs["file"] == classify_media([WAV])[1][0].source_path
    assert upload_kwargs["config"] == {"mime_type": "audio/wav", "display_name": "pelican.wav"}
    attached = {m["name"]: m for m in response.metadata["media_attached"]}
    assert attached["zebra.pdf"]["transport"] == "inline" and "file_name" not in attached["zebra.pdf"]
    # zen never deletes uploads (Google expires them after 48 h); the name lets a user delete one sooner.
    assert attached["pelican.wav"]["transport"] == "uploaded"
    assert attached["pelican.wav"]["file_name"] == "files/abc"
    provider._client.files.delete.assert_not_called()


def test_only_the_largest_files_are_uploaded(monkeypatch):
    provider = _provider()
    # PDF 587 B + MP4 ~7.9 KB fit together under 10 KB once the 67 KB WAV is uploaded.
    monkeypatch.setattr(GeminiModelProvider, "INLINE_MEDIA_MAX_BYTES", 10 * 1024)
    provider._client.files.upload.return_value = _file("files/w", "ACTIVE", mime_type="audio/wav")
    response = provider.generate_content("Go", "gemini-3.8-flash", media=classify_media([MP4, WAV, PDF])[1])
    assert provider._client.files.upload.call_count == 1
    transports = [(m["name"], m["transport"]) for m in response.metadata["media_attached"]]
    assert transports == [("otter.mp4", "inline"), ("pelican.wav", "uploaded"), ("zebra.pdf", "inline")]


def test_retry_does_not_upload_again(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(GeminiModelProvider, "INLINE_MEDIA_MAX_BYTES", 1024)
    monkeypatch.setattr(providers.base.time, "sleep", lambda seconds: None)
    provider._client.files.upload.return_value = _file("files/w", "ACTIVE", mime_type="audio/wav")
    ok = provider._client.models.generate_content.return_value
    provider._client.models.generate_content.side_effect = [RuntimeError("503 unavailable"), ok]
    provider.generate_content("Transcribe", "gemini-3.8-flash", media=classify_media([WAV])[1])
    assert provider._client.models.generate_content.call_count == 2
    assert provider._client.files.upload.call_count == 1


def test_provider_refuses_oversized_media_itself(monkeypatch):
    # generate_content runs the provider's own media check, so a direct caller cannot skip it.
    from utils.media import MediaNotSupportedError

    provider = _provider()
    monkeypatch.setattr("utils.media.MEDIA_MAX_BYTES", 100)
    with pytest.raises(MediaNotSupportedError, match="zebra.pdf"):
        provider.generate_content("Read", "gemini-3.8-flash", media=classify_media([PDF])[1])
    provider._client.models.generate_content.assert_not_called()


def test_upload_polls_until_active(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(GeminiModelProvider, "UPLOAD_POLL_INTERVAL_S", 0)
    processing = _file("files/x", "PROCESSING")
    active = _file("files/x", "ACTIVE")
    provider._client.files.upload.return_value = processing
    provider._client.files.get.side_effect = [processing, active]
    result = provider._upload_media(classify_media([MP4])[1][0])
    assert result is active
    assert provider._client.files.get.call_args.kwargs == {"name": "files/x"}


def test_upload_failure_raises():
    provider = _provider()
    provider._client.files.upload.return_value = _file("files/x", "FAILED")
    with pytest.raises(RuntimeError, match="FAILED"):
        provider._upload_media(classify_media([MP4])[1][0])


def test_upload_still_processing_after_the_timeout_raises(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(GeminiModelProvider, "UPLOAD_POLL_INTERVAL_S", 0)
    monkeypatch.setattr(GeminiModelProvider, "UPLOAD_TIMEOUT_S", -1)
    provider._client.files.upload.return_value = _file("files/x", "PROCESSING")
    with pytest.raises(RuntimeError, match="still PROCESSING"):
        provider._upload_media(classify_media([MP4])[1][0])


def test_upload_without_a_uri_raises():
    # A part with no file_uri would reach the API as a request with the media missing.
    provider = _provider()
    provider._client.files.upload.return_value = _file("files/x", "ACTIVE", uri=None)
    with pytest.raises(RuntimeError, match="no URI"):
        provider._upload_media(classify_media([MP4])[1][0])
