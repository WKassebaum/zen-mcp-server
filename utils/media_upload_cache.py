"""Reuse Gemini Files API uploads of the same bytes instead of uploading them again.

Follow-ups, each consensus model and tool-level retries re-send the same media. Gemini keeps an upload for 48 hours
and it belongs to the API key's project (any model can use it), so one upload can serve all of them.

The cache is a JSON file, ``~/.zen/media_uploads.json`` by default or ``$ZEN_MEDIA_UPLOAD_CACHE``:

    {"version": 1, "entries": {"<sha256 of the bytes>:<mime type>": {
        "file_name": "files/...", "file_uri": "...", "mime_type": "...", "size_bytes": 123,
        "expires_at": <unix seconds>, "key_fingerprint": "<first 12 hex chars of sha256(api key)>"}}}

- The API key itself is never stored; an entry made with another key is ignored.
- Entries expire 47 hours after the upload, an hour before Google deletes it, and are dropped when read.
- Several zen processes share the file. Writes are atomic (a temp file in the same directory, then ``os.replace``) and
  the last writer wins, so a race costs at most one extra upload.
- A corrupt or unreadable file reads as empty, and a failed write is logged: the cache never fails a model call.
- zen never deletes uploads; Google's 48-hour expiry does.
"""

import contextlib
import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from utils.env import get_env

logger = logging.getLogger(__name__)

ENV_VAR = "ZEN_MEDIA_UPLOAD_CACHE"
REUSE_SECONDS = 47 * 3600
FORMAT_VERSION = 1
_CHUNK_BYTES = 1024 * 1024
_FINGERPRINT_CHARS = 12
_STRING_FIELDS = ("file_name", "file_uri", "mime_type", "key_fingerprint")

# Model calls run in worker threads (asyncio.to_thread), so two uploads in one process can finish together: serialize
# this process's read-modify-write cycles. Other processes are covered by the atomic replace (last writer wins).
_lock = threading.Lock()


def cache_path() -> Path:
    """The cache file: $ZEN_MEDIA_UPLOAD_CACHE, else ~/.zen/media_uploads.json."""
    override = get_env(ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".zen" / "media_uploads.json"


def content_key(path: str, mime_type: str) -> str:
    """``<sha256 of the file's bytes>:<mime type>``, reading the file in 1 MiB chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return f"{digest.hexdigest()}:{mime_type}"


def api_key_fingerprint(api_key: str) -> str:
    """The first 12 hex characters of the key's sha256: tells keys apart without storing the key."""
    return hashlib.sha256((api_key or "").encode("utf-8")).hexdigest()[:_FINGERPRINT_CHARS]


def lookup(key: str, fingerprint: str, *, now: float | None = None) -> dict[str, Any] | None:
    """The live entry for ``key`` made with this API key, or None. Expired entries are dropped from the file."""
    now = time.time() if now is None else now
    path = cache_path()
    with _lock:
        entries = _load(path)
        live = _unexpired(entries, now)
        if len(live) != len(entries):
            _save(path, live)
    entry = live.get(key)
    if entry is None or entry["key_fingerprint"] != fingerprint:
        return None
    return dict(entry)


def store(
    key: str,
    fingerprint: str,
    *,
    file_name: str,
    file_uri: str,
    mime_type: str,
    size_bytes: int,
    now: float | None = None,
) -> None:
    """Record an upload made now (or at ``now``); it is reused until 47 hours later."""
    now = time.time() if now is None else now
    entry = {
        "file_name": file_name,
        "file_uri": file_uri,
        "mime_type": mime_type,
        "size_bytes": int(size_bytes),
        "expires_at": int(now + REUSE_SECONDS),
        "key_fingerprint": fingerprint,
    }
    path = cache_path()
    with _lock:
        entries = _unexpired(_load(path), now)
        entries[key] = entry
        _save(path, entries)


def evict(key: str) -> None:
    """Forget ``key`` (its upload is gone or unusable)."""
    path = cache_path()
    with _lock:
        entries = _load(path)
        if entries.pop(key, None) is not None:
            _save(path, entries)


def _unexpired(entries: dict[str, dict[str, Any]], now: float) -> dict[str, dict[str, Any]]:
    return {key: entry for key, entry in entries.items() if entry["expires_at"] > now}


def _valid_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    if not all(isinstance(entry.get(field), str) for field in _STRING_FIELDS):
        return False
    size, expires = entry.get("size_bytes"), entry.get("expires_at")
    return (
        isinstance(size, int)
        and not isinstance(size, bool)
        and isinstance(expires, (int, float))
        and not isinstance(expires, bool)
    )


def _load(path: Path) -> dict[str, dict[str, Any]]:
    """The file's well-formed entries; a missing, unreadable or corrupt file is empty."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Media upload cache %s is unreadable (%s); treating it as empty", path, exc)
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        logger.warning("Media upload cache %s is corrupt (%s); treating it as empty", path, exc)
        return {}
    entries = data.get("entries") if isinstance(data, dict) and data.get("version") == FORMAT_VERSION else None
    if not isinstance(entries, dict):
        logger.warning("Media upload cache %s is corrupt (unexpected layout); treating it as empty", path)
        return {}
    return {key: dict(entry) for key, entry in entries.items() if isinstance(key, str) and _valid_entry(entry)}


def _save(path: Path, entries: dict[str, dict[str, Any]]) -> None:
    """Write atomically with mode 0600; on failure log and leave the old file (and no temp file) in place."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    except OSError as exc:
        logger.warning("Media upload cache %s not saved (%s); the next call uploads again", path, exc)
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"version": FORMAT_VERSION, "entries": entries}, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)  # mkstemp already creates 0600; keep it explicit, os.replace keeps this mode
        os.replace(temp_name, path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            os.unlink(temp_name)
        logger.warning("Media upload cache %s not saved (%s); the next call uploads again", path, exc)
