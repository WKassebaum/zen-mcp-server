"""Gemini Files API uploads are cached by content and reused for 47 hours instead of uploading again."""

import hashlib
import json
import logging
import os
import shutil
import stat
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from providers.gemini import GeminiModelProvider
from tools.chat import ChatTool
from utils import media_upload_cache
from utils.media import classify_media
from utils.model_context import ModelContext

FIXTURES = Path(__file__).parent / "fixtures" / "media"
WAV = str(FIXTURES / "pelican.wav")
API_KEY = "test-key"
FINGERPRINT = hashlib.sha256(API_KEY.encode()).hexdigest()[:12]
URI = "https://gen.test/files/w"


@pytest.fixture
def cache_file(tmp_path, monkeypatch):
    path = tmp_path / "zen" / "media_uploads.json"
    monkeypatch.setenv("ZEN_MEDIA_UPLOAD_CACHE", str(path))
    return path


@pytest.fixture
def upload_everything(monkeypatch):
    monkeypatch.setattr(GeminiModelProvider, "INLINE_MEDIA_MAX_BYTES", 1024)  # the 67 KB WAV must be uploaded


def _file(name="files/w", state="ACTIVE", uri=URI, mime_type="audio/wav"):
    return SimpleNamespace(name=name, uri=uri, mime_type=mime_type, state=SimpleNamespace(name=state), error=None)


def _client():
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(
        text="ok", candidates=[MagicMock(finish_reason=None)], usage_metadata=None
    )
    client.files.upload.return_value = _file()
    client.files.get.return_value = _file()
    return client


def _provider(api_key=API_KEY):
    provider = GeminiModelProvider(api_key=api_key)
    provider._client = _client()
    return provider


def _wav_key():
    return hashlib.sha256(Path(WAV).read_bytes()).hexdigest() + ":audio/wav"


def _entries(path):
    return json.loads(path.read_text())["entries"]


EXPIRED = 47 * 3600 + 1  # seconds since upload


def _seed(age=0, fingerprint=FINGERPRINT):
    """Cache an upload of the WAV made ``age`` seconds ago."""
    media_upload_cache.store(
        _wav_key(),
        fingerprint,
        file_name="files/old",
        file_uri="https://gen.test/files/old",
        mime_type="audio/wav",
        size_bytes=1,
        now=time.time() - age,
    )


def _send(provider, paths=(WAV,)):
    response = provider.generate_content("Transcribe", "gemini-3.8-flash", media=classify_media(list(paths))[1])
    parts = provider._client.models.generate_content.call_args.kwargs["contents"][0]["parts"]
    return response.metadata["media_attached"], parts


# --- the cache module ---------------------------------------------------------------------------------------------


def test_key_is_the_streamed_content_hash_and_mime_type(monkeypatch):
    monkeypatch.setattr(media_upload_cache, "_CHUNK_BYTES", 1000)  # several chunks for the 67 KB file
    assert media_upload_cache.content_key(WAV, "audio/wav") == _wav_key()


def test_api_key_fingerprint_is_12_hex_characters():
    assert media_upload_cache.api_key_fingerprint(API_KEY) == FINGERPRINT


def test_default_location_is_under_zen(monkeypatch):
    monkeypatch.delenv("ZEN_MEDIA_UPLOAD_CACHE")
    assert media_upload_cache.cache_path() == Path.home() / ".zen" / "media_uploads.json"


def test_written_file_is_private_and_holds_no_api_key(cache_file):
    _seed()
    assert stat.S_IMODE(os.stat(cache_file).st_mode) == 0o600
    assert API_KEY not in cache_file.read_text()
    entry = _entries(cache_file)[_wav_key()]
    assert entry["key_fingerprint"] == FINGERPRINT


def test_atomic_write_leaves_no_temp_file(cache_file):
    _seed()
    media_upload_cache.evict(_wav_key())
    assert sorted(p.name for p in cache_file.parent.iterdir()) == ["media_uploads.json"]


def test_failed_write_leaves_no_temp_file_and_does_not_raise(cache_file, monkeypatch, caplog):
    def refuse(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(media_upload_cache.os, "replace", refuse)
    with caplog.at_level(logging.WARNING, logger="utils.media_upload_cache"):
        _seed()
    assert list(cache_file.parent.iterdir()) == []
    assert "disk full" in caplog.text


def test_expired_entries_are_evicted_on_read(cache_file):
    _seed(age=EXPIRED)
    assert media_upload_cache.lookup(_wav_key(), FINGERPRINT) is None
    assert _entries(cache_file) == {}


def test_corrupt_file_reads_as_empty_with_a_warning(cache_file, caplog):
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text("{not json")
    with caplog.at_level(logging.WARNING, logger="utils.media_upload_cache"):
        assert media_upload_cache.lookup(_wav_key(), FINGERPRINT) is None
    assert "corrupt" in caplog.text


# --- the Gemini provider ------------------------------------------------------------------------------------------


def test_miss_uploads_and_writes_an_entry(cache_file, upload_everything):
    provider = _provider()
    before = time.time()
    attached, parts = _send(provider)
    assert provider._client.files.upload.call_count == 1
    provider._client.files.get.assert_not_called()  # nothing cached: no lookup call either
    assert attached[0]["transport"] == "uploaded" and attached[0]["file_name"] == "files/w"
    entry = _entries(cache_file)[_wav_key()]
    assert entry["file_name"] == "files/w"
    assert entry["file_uri"] == URI
    assert entry["mime_type"] == "audio/wav"
    assert entry["size_bytes"] == os.path.getsize(WAV)
    assert entry["key_fingerprint"] == FINGERPRINT
    # Google deletes uploads after 48 h; zen stops reusing one an hour earlier.
    assert before + 47 * 3600 - 1 <= entry["expires_at"] <= time.time() + 47 * 3600 + 1


def test_hit_reuses_the_upload(cache_file, upload_everything):
    _seed()
    provider = _provider()
    provider._client.files.get.return_value = _file("files/old", uri="https://gen.test/files/old")
    attached, parts = _send(provider)
    provider._client.files.upload.assert_not_called()
    assert provider._client.files.get.call_args.kwargs == {"name": "files/old"}
    assert parts[0] == {"file_data": {"file_uri": "https://gen.test/files/old", "mime_type": "audio/wav"}}
    assert attached[0]["transport"] == "cached" and attached[0]["file_name"] == "files/old"


def test_expired_entry_is_not_looked_up_and_is_replaced(cache_file, upload_everything):
    _seed(age=EXPIRED)
    provider = _provider()
    attached, _ = _send(provider)
    provider._client.files.get.assert_not_called()
    assert provider._client.files.upload.call_count == 1
    assert attached[0]["transport"] == "uploaded"
    assert _entries(cache_file)[_wav_key()]["file_name"] == "files/w"


@pytest.mark.parametrize(
    "remote",
    [
        RuntimeError("404 NOT_FOUND"),
        RuntimeError("403 PERMISSION_DENIED"),
        _file("files/old", state="FAILED", uri="https://gen.test/files/old"),
        _file("files/old", state="PROCESSING", uri="https://gen.test/files/old"),
        _file("files/old", uri="https://gen.test/files/other"),
    ],
    ids=["404", "permission", "failed", "processing", "other-uri"],
)
def test_unusable_cached_upload_is_evicted_and_uploaded_once(cache_file, upload_everything, remote):
    _seed()
    provider = _provider()
    if isinstance(remote, Exception):
        provider._client.files.get.side_effect = remote
    else:
        provider._client.files.get.return_value = remote
    attached, parts = _send(provider)
    assert provider._client.files.upload.call_count == 1
    assert attached[0]["transport"] == "uploaded" and attached[0]["file_name"] == "files/w"
    assert parts[0]["file_data"]["file_uri"] == URI
    assert _entries(cache_file)[_wav_key()]["file_name"] == "files/w"


def test_another_api_keys_entry_is_ignored(cache_file, upload_everything):
    _seed(fingerprint=media_upload_cache.api_key_fingerprint("someone-else"))
    provider = _provider()
    attached, _ = _send(provider)
    provider._client.files.get.assert_not_called()
    assert provider._client.files.upload.call_count == 1
    assert attached[0]["transport"] == "uploaded"


def test_corrupt_cache_file_still_uploads_and_is_rewritten(cache_file, upload_everything):
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text("[1, 2")
    provider = _provider()
    attached, _ = _send(provider)
    assert provider._client.files.upload.call_count == 1
    assert _entries(cache_file)[_wav_key()]["file_name"] == "files/w"


def test_two_attachments_with_the_same_content_upload_once(cache_file, upload_everything, tmp_path):
    first, second = tmp_path / "a.wav", tmp_path / "b.wav"
    shutil.copyfile(WAV, first)
    shutil.copyfile(WAV, second)
    provider = _provider()
    attached, parts = _send(provider, paths=(str(first), str(second)))
    assert provider._client.files.upload.call_count == 1
    assert [(m["name"], m["transport"], m["file_name"]) for m in attached] == [
        ("a.wav", "uploaded", "files/w"),
        ("b.wav", "cached", "files/w"),
    ]
    assert parts[0] == parts[1] == {"file_data": {"file_uri": URI, "mime_type": "audio/wav"}}


def test_a_second_call_reuses_the_first_calls_upload(cache_file, upload_everything):
    # A follow-up or the next consensus model sends the same file again: one upload in total.
    provider = _provider()
    _send(provider)
    attached, _ = _send(provider)
    assert provider._client.files.upload.call_count == 1
    assert attached[0]["transport"] == "cached"


@pytest.mark.asyncio
async def test_simple_tool_retry_uploads_once(cache_file, upload_everything, tmp_path):
    client = _client()
    empty = MagicMock(text="", candidates=[MagicMock(finish_reason=None, safety_ratings=[])], usage_metadata=None)
    ok = client.models.generate_content.return_value
    client.models.generate_content.side_effect = [empty, ok]  # empty STOP answer: the chat tool retries once
    with patch.object(GeminiModelProvider, "client", new_callable=PropertyMock, return_value=client):
        await ChatTool().execute(
            {
                "prompt": "Transcribe",
                "absolute_file_paths": [WAV],
                "working_directory_absolute_path": str(tmp_path),
                "model": "gemini-3.8-flash",
                "_model_context": ModelContext("gemini-3.8-flash"),
                "_resolved_model_name": "gemini-3.8-flash",
            }
        )
    assert client.models.generate_content.call_count == 2
    assert client.files.upload.call_count == 1
