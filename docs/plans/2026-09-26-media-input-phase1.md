# Media Input Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** PDF, audio and video files passed through `--files` / `absolute_file_paths` / `relevant_files` are sent to Gemini models as native media, and every other model fails fast with a message naming models that can take them.

**Architecture:** Per-model capability flags (`supports_pdf/audio/video`) on `ModelCapabilities`; a small `utils/media.py` that classifies explicit file paths (same path security as text files, extension *and* magic bytes, symlink-aware), caps file size, estimates media tokens and words every media message; a provider-level `MEDIA_KINDS` declaration so no provider can silently drop media; capability-aware auto-mode selection; and a Gemini encoder (inline base64, Files API upload above the inline cap). Design: `docs/plans/2026-09-26-media-input-design.md`. Later phases add Claude/OpenAI, xAI, OpenRouter, continuation re-attach and caching.

**Tech Stack:** Python 3.12, pydantic, pytest, `google-genai` 1.46 (installed; do not upgrade), the MCP server in `server.py`, the click CLI in `src/zen_cli/main.py`.

---

## Ground rules for the engineer

- **Work in the worktree:** `/Users/wrk/WorkDev/MCP-Dev/zen-media-input` on branch `feat/media-input`. Never edit `/Users/wrk/WorkDev/MCP-Dev/zen-cli` — that checkout backs the user's live zen MCP server.
- **Python:** always `.zen_venv/bin/python` in the worktree. Its package versions are pinned to match the live venv; a fresh `pip install` pulls breaking major versions (`mcp` 2.x crashes `server.py`), so do not reinstall.
- **Baseline:** 955 passed, 3 failed. The 3 failures are pre-existing and unrelated: `tests/test_alias_target_restrictions.py::…gemini…` (three tests). Any other failure is yours.
- **Test command:** `.zen_venv/bin/python -m pytest tests/ -q -m "not integration" -p no:cacheprovider`. Do not rely on `./code_quality_checks.sh` for the test count — it runs pytest with `-x` and stops at the pre-existing failure.
- **Lint before each commit:** `ruff check . --fix && black . && isort .` — these three run from `PATH` (`~/.local/bin`). They are **not** installed in `.zen_venv`: never call `.zen_venv/bin/ruff`, `.zen_venv/bin/black` or `.zen_venv/bin/isort`, and do not install `requirements-dev.txt` into the venv. `ruff` targets py39 with the `UP` rules, so in files with `from __future__ import annotations` write `X | None`, never `Optional[X]`.
- **Gemini key:** `GEMINI_API_KEY` is exported by the user's shell. Never `source` any `.env` file (the live checkout's `zen-cli/.env` does not contain the Gemini key). Every step that calls Gemini starts with the guard `: "${GEMINI_API_KEY:?export GEMINI_API_KEY first}"`, which stops with that message if the key is missing instead of letting tests skip silently.
- **Commit trailer:** every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **No silent drops:** if you find a code path where media could be ignored without an error, that is a bug in this plan — stop and fix it, do not work around it.
- **Test model:** tests from Task 10 on use `gemini-3.8-flash` as the model that takes pdf, audio and video. If Task 6's probe did not verify a kind for it, use a model the probe did verify in those tests.
- **Pre-existing behaviour, unchanged here:** tools call `provider.generate_content` synchronously from their `async execute` (there is no `asyncio.to_thread` or `run_in_executor` anywhere in `tools/` or `providers/`), and provider retries use `time.sleep`. The Gemini Files API upload and poll (Task 15) therefore block the event loop exactly as a slow `generate_content` already does. Do not add a threading model in this phase.
- **Conversation rule for phase 1 (MCP continuations):** `server.py` re-sends the thread's first-turn files (`initial_context`) on every follow-up that omits the file list. That carry-forward stays (phase 5 builds on it) and is made visible: a carried-over file that fails the media check says it came from the first turn (Task 10/11), and when earlier turns attached media that the current request does not, the prompt says so in a `=== MEDIA NOT ATTACHED ===` note added by the tool once its media list is final (Tasks 11 and 13) — never by `build_conversation_history`, which runs before the `initial_context` merge. Media from later turns is not re-attached until phase 5.

---

### Task 1: Media test fixtures

**Files:**
- Create: `tests/fixtures/media/zebra.pdf`, `tests/fixtures/media/pelican.wav`, `tests/fixtures/media/otter.mp4`
- Create: `scripts/generate_media_fixtures.py`

These three files were generated and verified against live models on 2026-09-26. Each carries one unambiguous marker.

| File | Size | Marker |
|---|---|---|
| `zebra.pdf` | 587 B | text `ZEBRA-42` |
| `pelican.wav` | ~67 KB | speech "The code word is pelican seven." |
| `otter.mp4` | ~8 KB | 3 s of a frame showing `OTTER-9`, no audio |

**Step 1: Write the generator script** (macOS only; it documents provenance, the committed files are what tests use)

```python
#!/usr/bin/env python3
"""Regenerate the media probe fixtures in tests/fixtures/media/.

macOS only: uses `say`, `afconvert`, `sips` and `ffmpeg` (brew install ffmpeg).
Each fixture carries one marker that a model must repeat to prove it read the media:
  zebra.pdf   -> "ZEBRA-42"
  pelican.wav -> spoken "The code word is pelican seven."
  otter.mp4   -> frame text "OTTER-9"
"""

import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "media"


def _one_page_pdf(text: str, width: int, height: int, font_size: int, navy_background: bool) -> bytes:
    """Return a minimal valid single-page PDF showing `text` in Helvetica-Bold."""
    fill = b"0 0 0.5 rg 0 0 %d %d re f 1 1 1 rg " % (width, height) if navy_background else b""
    stream = fill + b"BT /F1 %d Tf 40 %d Td (%s) Tj ET" % (font_size, height // 2 - font_size // 3, text.encode())
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>" % (width, height),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "zebra.pdf").write_bytes(_one_page_pdf("ZEBRA-42", 300, 144, 24, navy_background=False))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        aiff = tmp_path / "pelican.aiff"
        subprocess.run(["say", "-o", str(aiff), "The code word is pelican seven."], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(aiff), str(OUT / "pelican.wav")], check=True)

        frame_pdf = tmp_path / "frame.pdf"
        frame_png = tmp_path / "frame.png"
        frame_pdf.write_bytes(_one_page_pdf("OTTER-9", 640, 360, 96, navy_background=True))
        subprocess.run(["sips", "-s", "format", "png", str(frame_pdf), "--out", str(frame_png)], check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", str(frame_png), "-t", "3", "-r", "24",
             "-vf", "scale=640:360", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(OUT / "otter.mp4")],
            check=True,
        )
    for name in ("zebra.pdf", "pelican.wav", "otter.mp4"):
        print(f"{name}: {(OUT / name).stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Generate and check**

Run: `.zen_venv/bin/python scripts/generate_media_fixtures.py`
Expected: three lines with sizes close to the table above. Open `otter.mp4` / `zebra.pdf` in Preview and play `pelican.wav` once to confirm the markers.

**Step 3: Commit**

```bash
git add scripts/generate_media_fixtures.py tests/fixtures/media/
git commit -m "test(media): add PDF/audio/video probe fixtures and generator"
```

---

### Task 2: `utils/media.py` — classification

**Files:**
- Create: `utils/media.py`
- Test: `tests/test_media_utils.py`

What this task settles:
- **Path security.** A media path goes through `utils.file_utils.resolve_and_validate_path` — the same CWE-22 checks text files get (absolute path, not under a `utils/security_config.py` dangerous directory, not the home-directory root). A path that fails is never media; it falls through to `read_file_content`'s normal access error.
- **Symlinks.** A media extension on either the given path or its resolved target counts (`latest -> recording.mp4` and the Hugging Face layout `clip.mp4 -> blob`); the magic bytes must still match. Symlink loops (`RuntimeError`) are not media.
- **Signatures.** ID3v2 tags (10-byte header + syncsafe size, +10 with the footer flag) are skipped for mp3/aac/flac by seeking past them — cover art makes tags far bigger than any fixed read. `%PDF-` may appear anywhere in the first 1024 bytes. MPEG transport streams are **excluded**: `.ts` is TypeScript in `utils/file_types.py`, and TS data saved as `.mpg` fails the program-stream signature, so it gets the binary placeholder.
- **Text encodings.** `looks_binary` never flags a known text extension (`utils/file_types.TEXT_EXTENSIONS`) or a file with a UTF-32/UTF-16 byte-order mark (UTF-32 checked first: its LE BOM `FF FE 00 00` starts with UTF-16's `FF FE`); `bom_encoding` gives Task 4 the codec to decode such files as text.

**Step 1: Write the failing tests**

```python
"""Tests for utils.media classification helpers."""

import os
from pathlib import Path

import pytest

import utils.security_config
from utils.media import (
    MediaAttachment,
    MediaKind,
    bom_encoding,
    classify_media,
    looks_binary,
    media_kinds_from_arguments,
    media_type_for,
    required_kinds,
)

FIXTURES = Path(__file__).parent / "fixtures" / "media"
PDF = str(FIXTURES / "zebra.pdf")
WAV = str(FIXTURES / "pelican.wav")
MP4 = str(FIXTURES / "otter.mp4")

ADTS_FRAME = b"\xff\xf1\x50\x80\x02\x1f\xfc" + b"\x00" * 9
TS_PACKET = b"\x47\x40\x00\x10" + b"\xff" * 184


def _id3_tag(body_size: int, footer: bool = False) -> bytes:
    """An ID3v2.4 tag whose body is ``body_size`` bytes, with an optional 10-byte footer."""
    syncsafe = bytes((body_size >> shift) & 0x7F for shift in (21, 14, 7, 0))
    flags = b"\x10" if footer else b"\x00"
    tag = b"ID3\x04\x00" + flags + syncsafe + b"\x00" * body_size
    return tag + (b"3DI\x04\x00" + flags + syncsafe if footer else b"")


def test_media_type_for_fixtures():
    assert media_type_for(PDF) == (MediaKind.PDF, "application/pdf")
    assert media_type_for(WAV) == (MediaKind.AUDIO, "audio/wav")
    assert media_type_for(MP4) == (MediaKind.VIDEO, "video/mp4")


def test_media_type_for_rejects_wrong_magic(tmp_path):
    fake = tmp_path / "notes.pdf"
    fake.write_text("just text pretending to be a pdf")
    assert media_type_for(str(fake)) is None


def test_media_type_for_ignores_missing_and_text(tmp_path):
    code = tmp_path / "app.py"
    code.write_text("print('hi')\n")
    assert media_type_for(str(code)) is None
    assert media_type_for(str(tmp_path / "missing.mp4")) is None
    assert media_type_for(str(tmp_path)) is None  # directories are never media


def test_media_type_for_requires_absolute_path():
    assert media_type_for(os.path.relpath(MP4)) is None


def test_media_under_dangerous_path_is_not_media(tmp_path, monkeypatch):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(Path(MP4).read_bytes())
    monkeypatch.setattr(utils.security_config, "DANGEROUS_SYSTEM_PATHS", {str(tmp_path)})
    assert media_type_for(str(clip)) is None
    text_paths, media = classify_media([str(clip)])
    assert text_paths == [str(clip)] and media == []  # falls through to read_file_content's access error


def test_symlink_without_media_suffix_to_media_file(tmp_path):
    target = tmp_path / "recording.mp4"
    target.write_bytes(Path(MP4).read_bytes())
    link = tmp_path / "latest"
    link.symlink_to(target)
    assert media_type_for(str(link)) == (MediaKind.VIDEO, "video/mp4")


def test_media_suffix_symlink_to_blob(tmp_path):
    blob = tmp_path / "blob"
    blob.write_bytes(Path(MP4).read_bytes())
    link = tmp_path / "clip.mp4"
    link.symlink_to(blob)
    assert media_type_for(str(link)) == (MediaKind.VIDEO, "video/mp4")
    _, media = classify_media([str(link)])
    assert media[0].path == str(link) and media[0].size_bytes == blob.stat().st_size


def test_symlink_loop_is_not_media(tmp_path):
    loop = tmp_path / "loop.mp4"
    loop.symlink_to(loop)
    assert media_type_for(str(loop)) is None


@pytest.mark.parametrize("footer", [False, True])
def test_id3_tagged_aac_is_audio(tmp_path, footer):
    aac = tmp_path / "segment.aac"
    aac.write_bytes(_id3_tag(4096, footer=footer) + ADTS_FRAME)  # tag larger than the 1 KB first read
    assert media_type_for(str(aac)) == (MediaKind.AUDIO, "audio/aac")


def test_id3_tagged_flac_is_audio(tmp_path):
    flac = tmp_path / "song.flac"
    flac.write_bytes(_id3_tag(2048) + b"fLaC" + b"\x00" * 34)
    assert media_type_for(str(flac)) == (MediaKind.AUDIO, "audio/flac")


def test_id3_tagged_mp3_is_audio(tmp_path):
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(_id3_tag(3000) + b"\xff\xfb\x90\x00" + b"\x00" * 12)
    assert media_type_for(str(mp3)) == (MediaKind.AUDIO, "audio/mpeg")


def test_pdf_with_leading_bytes_is_pdf(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"\xef\xbb\xbf\r\n" + Path(PDF).read_bytes())
    assert media_type_for(str(pdf)) == (MediaKind.PDF, "application/pdf")


def test_pdf_marker_beyond_first_kilobyte_is_not_pdf(tmp_path):
    pdf = tmp_path / "junk.pdf"
    pdf.write_bytes(b" " * 2048 + Path(PDF).read_bytes())
    assert media_type_for(str(pdf)) is None


@pytest.mark.parametrize("name", ["capture.mpg", "capture.ts"])
def test_mpeg_transport_stream_is_not_media(tmp_path, name):
    # MPEG-TS is excluded: .ts is TypeScript in utils/file_types.py, and TS saved as .mpg fails the
    # MPEG program-stream signature.
    ts = tmp_path / name
    ts.write_bytes(TS_PACKET * 3)
    assert media_type_for(str(ts)) is None


def test_classify_media_splits_paths(tmp_path):
    code = tmp_path / "app.py"
    code.write_text("print('hi')\n")
    text_paths, media = classify_media([str(code), PDF, MP4, str(tmp_path)])
    assert text_paths == [str(code), str(tmp_path)]
    assert [m.kind for m in media] == [MediaKind.PDF, MediaKind.VIDEO]
    assert media[0].name == "zebra.pdf"
    assert media[0].size_bytes == Path(PDF).stat().st_size


def test_classify_media_handles_none_and_dedupes():
    assert classify_media(None) == ([], [])
    _, media = classify_media([PDF, PDF])
    assert len(media) == 1


def test_required_kinds_and_describe():
    _, media = classify_media([PDF, WAV, MP4])
    assert required_kinds(media) == frozenset({MediaKind.PDF, MediaKind.AUDIO, MediaKind.VIDEO})
    assert required_kinds([]) == frozenset()
    assert media[1].describe().startswith("audio pelican.wav, ")


def test_looks_binary(tmp_path):
    blob = tmp_path / "data.bin"
    blob.write_bytes(b"\x00\x01\x02binary")
    text = tmp_path / "readme.txt"
    text.write_text("plain text")
    assert looks_binary(str(blob)) is True
    assert looks_binary(str(text)) is False


def test_known_text_extension_is_never_sniffed(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_bytes(b"a\x00b")
    assert looks_binary(str(notes)) is False


@pytest.mark.parametrize(
    "encoding,expected",
    [("utf-16-le", "utf-16"), ("utf-16-be", "utf-16"), ("utf-32-le", "utf-32"), ("utf-32-be", "utf-32")],
)
def test_bom_encodings(tmp_path, encoding, expected):
    strings = tmp_path / "Localizable.strings"  # not a known text extension, so it would be sniffed
    bom = "\ufeff".encode(encoding)
    strings.write_bytes(bom + '"hello" = "Hallo";\n'.encode(encoding))
    assert bom_encoding(str(strings)) == expected
    assert looks_binary(str(strings)) is False


def test_no_bom(tmp_path):
    plain = tmp_path / "plain.strings"
    plain.write_text("hello")
    assert bom_encoding(str(plain)) is None


@pytest.mark.parametrize("key", ["absolute_file_paths", "relevant_files", "files"])
def test_media_kinds_from_arguments(key):
    assert media_kinds_from_arguments({key: [MP4]}) == frozenset({MediaKind.VIDEO})
    assert media_kinds_from_arguments({key: None}) == frozenset()
    assert media_kinds_from_arguments({}) == frozenset()


def test_media_kinds_from_arguments_expands_home(tmp_path, monkeypatch):
    (tmp_path / "clip.mp4").write_bytes(Path(MP4).read_bytes())
    monkeypatch.setenv("HOME", str(tmp_path))
    assert media_kinds_from_arguments({"absolute_file_paths": ["~/clip.mp4"]}) == frozenset({MediaKind.VIDEO})


def test_media_attachment_is_hashable():
    _, media = classify_media([PDF])
    assert isinstance(media[0], MediaAttachment)
    assert len({media[0], media[0]}) == 1
```

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_utils.py -q -p no:cacheprovider`
Expected: collection error, `ModuleNotFoundError: No module named 'utils.media'`.

**Step 3: Write the implementation**

`utils/media.py` (keep `from __future__ import annotations` and the `X | None` annotations: the repo's ruff config targets py39 with `UP` rules and rejects `Optional[...]` here):

```python
"""Native media attachments (PDF, audio, video) for model requests.

Media files are never read as text. They are detected from explicit file paths by
extension *and* magic bytes, carried alongside the prompt, and encoded by providers
that declare support for them (``ModelProvider.MEDIA_KINDS``).
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, BinaryIO

from .file_types import TEXT_EXTENSIONS


class MediaKind(str, Enum):
    PDF = "pdf"
    AUDIO = "audio"
    VIDEO = "video"


class MediaNotSupportedError(ValueError):
    """Raised when media cannot be sent to the selected model or provider."""


# Extension -> (kind, MIME type). Keep in sync with provider MIME support.
# MPEG transport streams are deliberately NOT media: ".ts" is TypeScript in utils/file_types.py, and TS
# packets (sync byte 0x47) saved as .mpg/.mpeg fail the MPEG program-stream signature below.
MEDIA_TYPES: dict[str, tuple[MediaKind, str]] = {
    ".pdf": (MediaKind.PDF, "application/pdf"),
    ".wav": (MediaKind.AUDIO, "audio/wav"),
    ".mp3": (MediaKind.AUDIO, "audio/mpeg"),
    ".m4a": (MediaKind.AUDIO, "audio/mp4"),
    ".aac": (MediaKind.AUDIO, "audio/aac"),
    ".ogg": (MediaKind.AUDIO, "audio/ogg"),
    ".flac": (MediaKind.AUDIO, "audio/flac"),
    ".mp4": (MediaKind.VIDEO, "video/mp4"),
    ".mov": (MediaKind.VIDEO, "video/quicktime"),
    ".webm": (MediaKind.VIDEO, "video/webm"),
    ".mpeg": (MediaKind.VIDEO, "video/mpeg"),
    ".mpg": (MediaKind.VIDEO, "video/mpeg"),
}

# Argument keys that carry file paths, across simple tools, workflow tools and the CLI.
FILE_ARGUMENT_KEYS = ("absolute_file_paths", "relevant_files", "files")

# How far into a file to look for "%PDF-" (some writers put a BOM, whitespace or junk first).
PDF_HEADER_SEARCH_BYTES = 1024
# Formats that may start with an ID3v2 tag before the first audio frame.
ID3_TAGGED_EXTENSIONS = (".mp3", ".aac", ".flac")


def _read_signature(handle: BinaryIO, extension: str) -> bytes:
    """Bytes to check a signature against: skips a leading ID3v2 tag, keeps 1 KB for the PDF search."""
    head = handle.read(PDF_HEADER_SEARCH_BYTES)
    if extension in ID3_TAGGED_EXTENSIONS and head[:3] == b"ID3" and len(head) >= 10:
        # ID3v2 header: "ID3", version (2 bytes), flags (1 byte), size as 4 syncsafe bytes (7 bits each).
        tag_size = 0
        for byte in head[6:10]:
            tag_size = (tag_size << 7) | (byte & 0x7F)
        footer = 10 if head[5] & 0x10 else 0
        # A tag with cover art is far larger than any fixed read, so seek past it instead.
        handle.seek(10 + tag_size + footer)
        head = handle.read(16)
    return head


def _magic_matches(extension: str, head: bytes) -> bool:
    """Cheap signature check so a mislabelled text file is never sent as media."""
    if extension == ".pdf":
        return b"%PDF-" in head[:PDF_HEADER_SEARCH_BYTES]
    if extension == ".wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if extension == ".mp3":
        return len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0
    if extension in (".mp4", ".mov", ".m4a"):
        return head[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free")
    if extension == ".aac":
        return len(head) > 1 and head[0] == 0xFF and (head[1] & 0xF6) == 0xF0
    if extension == ".ogg":
        return head.startswith(b"OggS")
    if extension == ".flac":
        return head.startswith(b"fLaC")
    if extension == ".webm":
        return head.startswith(b"\x1a\x45\xdf\xa3")
    if extension in (".mpeg", ".mpg"):
        return head[:4] in (b"\x00\x00\x01\xba", b"\x00\x00\x01\xb3")
    return False


def media_type_for(path: str) -> tuple[MediaKind, str] | None:
    """Return (kind, mime) if ``path`` is an existing, correctly signed media file.

    The path must pass the same security validation as text files (absolute, not under a
    dangerous system directory). A media extension on either the given path or its symlink
    target counts, so ``latest -> recording.mp4`` and ``clip.mp4 -> blob`` are both media;
    the magic bytes must match that extension either way.
    """
    from .file_utils import resolve_and_validate_path  # file_utils imports this module

    try:
        resolved = resolve_and_validate_path(path)
    except (ValueError, PermissionError, RuntimeError, OSError):  # RuntimeError: symlink loop
        return None
    candidates = [s for s in dict.fromkeys((Path(path).suffix.lower(), resolved.suffix.lower())) if s in MEDIA_TYPES]
    if not candidates:
        return None
    try:
        if not resolved.is_file():
            return None
        for extension in candidates:
            with resolved.open("rb") as handle:
                if _magic_matches(extension, _read_signature(handle, extension)):
                    return MEDIA_TYPES[extension]
    except OSError:
        return None
    return None


@dataclass(frozen=True)
class MediaAttachment:
    path: str
    kind: MediaKind
    mime_type: str
    size_bytes: int

    @property
    def name(self) -> str:
        return Path(self.path).name

    def describe(self) -> str:
        return f"{self.kind.value} {self.name}, {self.size_bytes / (1024 * 1024):.1f} MB"


def classify_media(paths: Iterable[str] | None) -> tuple[list[str], list[MediaAttachment]]:
    """Split explicit paths into (text_paths, media_attachments). Order preserved, media deduped."""
    text_paths: list[str] = []
    media: list[MediaAttachment] = []
    seen: set[str] = set()
    for path in paths or []:
        detected = media_type_for(path)
        if detected is None:
            text_paths.append(path)
            continue
        if path in seen:
            continue
        seen.add(path)
        kind, mime = detected
        media.append(MediaAttachment(path=path, kind=kind, mime_type=mime, size_bytes=os.path.getsize(path)))
    return text_paths, media


def required_kinds(media: Iterable[MediaAttachment]) -> frozenset[MediaKind]:
    return frozenset(attachment.kind for attachment in media)


def bom_encoding(path: str) -> str | None:
    """Codec for a file that starts with a UTF-32 or UTF-16 byte-order mark, else None.

    UTF-32 is checked first: the UTF-32-LE BOM (FF FE 00 00) starts with the UTF-16-LE BOM (FF FE).
    The "utf-32"/"utf-16" codecs read the BOM to pick the byte order and drop it from the text.
    """
    try:
        with open(path, "rb") as handle:
            head = handle.read(4)
    except OSError:
        return None
    if head in (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"):
        return "utf-32"
    if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    return None


def looks_binary(path: str, sample_size: int = 8192) -> bool:
    """True if the file is not text we can embed: a NUL byte in its first bytes.

    Never true for a known text extension (utils/file_types.TEXT_EXTENSIONS) or a file that
    starts with a UTF-16/UTF-32 byte-order mark: those are decoded as text.
    """
    if Path(path).suffix.lower() in TEXT_EXTENSIONS or bom_encoding(path) is not None:
        return False
    try:
        with open(path, "rb") as handle:
            return b"\x00" in handle.read(sample_size)
    except OSError:
        return False


def media_kinds_from_paths(paths: Iterable[str]) -> frozenset[MediaKind]:
    """Media kinds among ``paths`` (``~`` is expanded, as the chat tool does before reading)."""
    return required_kinds(classify_media([os.path.expanduser(str(path)) for path in paths])[1])


def media_kinds_from_arguments(arguments: dict[str, Any]) -> frozenset[MediaKind]:
    """Media kinds referenced by raw tool arguments (used before a request model exists)."""
    paths: list[str] = []
    for key in FILE_ARGUMENT_KEYS:
        value = arguments.get(key)
        if isinstance(value, (list, tuple)):
            paths.extend(str(item) for item in value)
    return media_kinds_from_paths(paths)


def format_kinds(kinds: Iterable[MediaKind]) -> str:
    return "/".join(sorted(kind.value for kind in kinds))
```

`resolve_and_validate_path` is imported inside `media_type_for` because `utils/file_utils.py` imports this module in Task 4.

**Step 4: Run tests**

Run: `.zen_venv/bin/python -m pytest tests/test_media_utils.py -q -p no:cacheprovider`
Expected: all pass (the symlink tests need a filesystem with symlinks — macOS and Linux both qualify).

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add utils/media.py tests/test_media_utils.py
git commit -m "feat(media): add media classification helpers" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Media size limit, token estimate and prompt announcement

**Files:**
- Modify: `utils/media.py` (add `import math`; append one section)
- Test: `tests/test_media_limits.py`

- **Size limit.** `MEDIA_MAX_BYTES` is the Gemini Files API per-file limit, 2 GB. `check_media_sizes` fails fast naming each file and the limit; Tasks 7, 10 and 14 call it before anything is read, inlined or uploaded. Tests use sparse files (`truncate`), so no real 2 GB file is written.
- **Token estimate.** Media tokens are reserved from the text-file budget before text files are embedded (Tasks 10 and 13), so text plus media stays inside the model's context. Figures come from the Gemini media docs: video frames are 258 tokens each at 1 frame/s (66 at low media resolution) plus 32 tokens/s of audio, so 300 tokens/s covers the high-resolution case; audio is 32 tokens/s; about 258 tokens per PDF page is the older documented figure and is not yet confirmed for current models. Durations are read exactly where the header makes it cheap (WAV `data`/byte rate; MP4/MOV/M4A `moov`→`mvhd`, wherever `moov` sits). Otherwise the estimate assumes a low bitrate (video 64 kB/s, audio 8 kB/s) or a small PDF page (4 kB), so it errs high: text files get less room, never more. The estimate never rejects a request — the provider API stays the hard limit and its over-limit error reaches the user. Task 17's live test checks the estimate is not below real usage for the fixtures.
- **Prompt announcement.** `media_prompt_section` writes the `--- MEDIA FILE: … attached to this request …` lines from the attachment list itself, so the prompt and what is attached cannot disagree (Tasks 10 and 13 use it instead of letting `read_files` describe media).

**Step 1: Write the failing tests**

```python
"""Tests for the media size limit, token estimate and prompt announcement in utils.media."""

from pathlib import Path

import pytest

from utils.media import (
    MEDIA_MAX_BYTES,
    MediaNotSupportedError,
    check_media_sizes,
    classify_media,
    estimate_media_tokens,
    media_prompt_section,
)

FIXTURES = Path(__file__).parent / "fixtures" / "media"
PDF = str(FIXTURES / "zebra.pdf")
WAV = str(FIXTURES / "pelican.wav")
MP4 = str(FIXTURES / "otter.mp4")


def _box(box_type: bytes, payload: bytes) -> bytes:
    return (8 + len(payload)).to_bytes(4, "big") + box_type + payload


def _sparse_mp4(path: Path, size: int) -> Path:
    """An 'ftyp' header followed by a hole: passes the signature check without writing real data."""
    with path.open("wb") as handle:
        handle.write(_box(b"ftyp", b"isom\x00\x00\x02\x00isom"))
        handle.truncate(size)
    return path


def test_check_media_sizes_accepts_fixtures():
    check_media_sizes(classify_media([PDF, WAV, MP4])[1])


def test_check_media_sizes_rejects_oversized_file(tmp_path):
    huge = _sparse_mp4(tmp_path / "huge.mp4", MEDIA_MAX_BYTES + 1)
    media = classify_media([str(huge)])[1]
    with pytest.raises(MediaNotSupportedError, match=r"huge\.mp4 \(2\.00 GB\)") as exc:
        check_media_sizes(media)
    assert "limited to 2 GB each" in str(exc.value)


def test_estimate_reads_exact_durations():
    _, (pdf, wav, mp4) = classify_media([PDF, WAV, MP4])
    assert estimate_media_tokens([mp4]) == 3 * 300  # mvhd: 3 s, stored after mdat
    assert estimate_media_tokens([wav]) == 2 * 32  # 1.96 s of 16 kHz mono, rounded up
    assert estimate_media_tokens([pdf]) == 258  # one page
    assert estimate_media_tokens([pdf, wav, mp4]) == 258 + 64 + 900
    assert estimate_media_tokens([]) == 0


def test_estimate_reads_version_1_movie_header(tmp_path):
    mvhd = _box(b"mvhd", b"\x01\x00\x00\x00" + b"\x00" * 16 + (1000).to_bytes(4, "big") + (90_000).to_bytes(8, "big"))
    clip = tmp_path / "long.mov"
    clip.write_bytes(_box(b"ftyp", b"qt  \x00\x00\x02\x00qt  ") + _box(b"mdat", b"\x00" * 64) + _box(b"moov", mvhd))
    assert estimate_media_tokens(classify_media([str(clip)])[1]) == 90 * 300


def test_estimate_falls_back_to_size_without_a_header(tmp_path):
    clip = _sparse_mp4(tmp_path / "raw.mp4", 2 * 1024 * 1024)  # no moov box
    assert estimate_media_tokens(classify_media([str(clip)])[1]) == 300 * 33  # 2 MiB at 64 kB/s = 32.8 s


def test_media_prompt_section_lists_every_attachment():
    section = media_prompt_section(classify_media([PDF, MP4])[1])
    assert section.count("--- MEDIA FILE:") == 2
    assert "attached to this request as native video input" in section
```

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_limits.py -q -p no:cacheprovider`
Expected: collection error, `ImportError: cannot import name 'MEDIA_MAX_BYTES' from 'utils.media'`.

**Step 3: Implement**

In `utils/media.py`, add `import math` above `import os`, then append at the end of the file:

```python
# ---------------------------------------------------------------------------
# Size limit, token estimate and prompt announcement
# ---------------------------------------------------------------------------

# Largest single media file zen sends: the Gemini Files API per-file limit (2 GB).
MEDIA_MAX_BYTES = 2 * 1024**3

# Input-token planning figures from the Gemini media docs (video and audio checked 2026-09-27): a
# video frame is 258 tokens at 1 frame/s (66 at low media resolution) plus 32 tokens/s of audio, so
# 300/s covers the high-resolution case; audio is 32 tokens/s. ~258 tokens per PDF page is the older
# documented figure; tests/test_media_live.py checks all three against real usage.
VIDEO_TOKENS_PER_SECOND = 300
AUDIO_TOKENS_PER_SECOND = 32
PDF_TOKENS_PER_PAGE = 258
# Used when the duration or page count is not cheaply readable: a low bitrate / small page, so the
# estimate errs high and text files get less room, never more.
FALLBACK_BYTES_PER_SECOND = {MediaKind.VIDEO: 64_000, MediaKind.AUDIO: 8_000}
FALLBACK_BYTES_PER_PDF_PAGE = 4_000


def check_media_sizes(media: Iterable[MediaAttachment]) -> None:
    """Fail fast, naming each file, if any attachment is larger than MEDIA_MAX_BYTES."""
    too_large = [attachment for attachment in media if attachment.size_bytes > MEDIA_MAX_BYTES]
    if too_large:
        names = ", ".join(f"{a.name} ({a.size_bytes / 1024**3:.2f} GB)" for a in too_large)
        raise MediaNotSupportedError(
            f"Media files are limited to {MEDIA_MAX_BYTES // 1024**3} GB each "
            f"(the Gemini Files API per-file limit): {names}."
        )


def _wav_duration_s(handle: BinaryIO) -> float | None:
    """Duration from a RIFF/WAVE header: data chunk size / byte rate."""
    if handle.read(12)[8:12] != b"WAVE":
        return None
    byte_rate = 0
    while True:
        chunk = handle.read(8)
        if len(chunk) < 8:
            return None
        chunk_id, chunk_size = chunk[:4], int.from_bytes(chunk[4:8], "little")
        body_size = chunk_size + (chunk_size & 1)  # RIFF chunks are word-aligned
        if chunk_id == b"fmt ":
            byte_rate = int.from_bytes(handle.read(body_size)[8:12], "little")
        elif chunk_id == b"data":
            return chunk_size / byte_rate if byte_rate else None
        else:
            handle.seek(body_size, 1)


def _bmff_duration_s(handle: BinaryIO, file_size: int) -> float | None:
    """Duration from the movie header ('moov' -> 'mvhd') of an MP4/MOV/M4A file, wherever moov sits."""
    offset, limit = 0, file_size
    while offset + 8 <= limit:
        handle.seek(offset)
        header = handle.read(16)
        size, box, header_size = int.from_bytes(header[:4], "big"), header[4:8], 8
        if size == 1:  # 64-bit box size follows the type
            size, header_size = int.from_bytes(header[8:16], "big"), 16
        elif size == 0:  # box runs to the end of its parent
            size = limit - offset
        if size < header_size:
            return None
        if box == b"moov":
            offset, limit = offset + header_size, offset + size  # descend into the movie box
            continue
        if box == b"mvhd":
            handle.seek(offset + header_size)
            body = handle.read(32)
            if body[:1] == b"\x01":  # version 1: 64-bit creation/modification times and duration
                timescale, duration = int.from_bytes(body[20:24], "big"), int.from_bytes(body[24:32], "big")
            else:
                timescale, duration = int.from_bytes(body[12:16], "big"), int.from_bytes(body[16:20], "big")
            return duration / timescale if timescale else None
        offset += size
    return None


def _duration_s(attachment: MediaAttachment) -> float | None:
    """Exact duration where the container header makes it cheap (WAV, MP4/MOV/M4A), else None."""
    try:
        with open(attachment.path, "rb") as handle:
            if attachment.mime_type == "audio/wav":
                return _wav_duration_s(handle)
            if attachment.mime_type in ("video/mp4", "video/quicktime", "audio/mp4"):
                return _bmff_duration_s(handle, attachment.size_bytes)
    except OSError:
        return None
    return None


def estimate_media_tokens(media: Iterable[MediaAttachment]) -> int:
    """Input tokens the attachments are expected to cost, erring high.

    Callers reserve this from the text-file budget before embedding text files. It never rejects a
    request: the provider API stays the hard limit and its over-limit error reaches the user.
    """
    total = 0
    for attachment in media:
        if attachment.kind is MediaKind.PDF:
            pages = max(1, math.ceil(attachment.size_bytes / FALLBACK_BYTES_PER_PDF_PAGE))
            total += PDF_TOKENS_PER_PAGE * pages
            continue
        seconds = _duration_s(attachment)
        if seconds is None:
            seconds = attachment.size_bytes / FALLBACK_BYTES_PER_SECOND[attachment.kind]
        rate = VIDEO_TOKENS_PER_SECOND if attachment.kind is MediaKind.VIDEO else AUDIO_TOKENS_PER_SECOND
        total += rate * max(1, math.ceil(seconds))
    return total


def media_prompt_section(media: Iterable[MediaAttachment]) -> str:
    """Prompt text announcing attachments, built from the attachment list so the two cannot disagree."""
    return "".join(
        f"\n--- MEDIA FILE: {a.path} ({a.kind.value}, {a.mime_type}, {a.size_bytes / (1024 * 1024):.1f} MB) ---\n"
        f"Not embedded as text: attached to this request as native {a.kind.value} input.\n"
        "--- END FILE ---\n"
        for a in media
    )
```

**Step 4: Run tests**

Run: `.zen_venv/bin/python -m pytest tests/test_media_limits.py tests/test_media_utils.py -q -p no:cacheprovider`
Expected: all pass.

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add utils/media.py tests/test_media_limits.py
git commit -m "feat(media): add size limit, token estimate and prompt announcement" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Never read media or binaries as text

**Files:**
- Modify: `utils/file_utils.py` — `read_file_content`: insert right after the `if not path.is_file():` block (line 461) and **before** the size check; change the decode at line 487
- Modify: `utils/conversation_memory.py` — `get_conversation_file_list` (the `for file_path in turn.files:` loop, line 494)
- Modify: `tools/shared/base_tool.py` — `handle_prompt_file` fallback (the `if not content.startswith("\n--- ERROR"):` line, line 940)
- Test: `tests/test_media_file_reading.py`

Today `read_file_content` decodes any file up to 1,000,000 bytes as UTF-8 with replacement characters, so a small video becomes garbage text; larger files get a `FILE TOO LARGE` marker. Either way the model sees none of the media. The media and binary checks therefore go before the size check.

`media_type_for` is called with the path **as given** (`file_path`), not the resolved `path`, so `read_file_content` and `classify_media` agree on symlinks. `read_files` still hands `read_file_content` the resolved path (`expand_paths` resolves), which is why Tasks 10 and 13 split media out before calling `read_files`; this placeholder is the safety net for media reached any other way (for example a symlink with a text name inside a directory), so it does not claim the file is attached.

**Step 1: Write the failing tests**

```python
"""Media and binary files must never be embedded as text; BOM-marked text must stay readable."""

from pathlib import Path

import utils.security_config
from tools.chat import ChatTool
from utils.conversation_memory import ConversationTurn, ThreadContext, get_conversation_file_list
from utils.file_utils import read_file_content

FIXTURES = Path(__file__).parent / "fixtures" / "media"
MP4 = str(FIXTURES / "otter.mp4")


def test_media_file_gets_placeholder_not_garbage():
    content, tokens = read_file_content(MP4)
    assert "--- MEDIA FILE:" in content
    assert "video/mp4" in content
    assert "\ufffd" not in content  # no replacement characters from a UTF-8 decode
    assert tokens < 200


def test_pdf_placeholder_names_kind():
    content, _ = read_file_content(str(FIXTURES / "zebra.pdf"))
    assert "(pdf, application/pdf" in content


def test_media_name_on_symlink_counts(tmp_path):
    blob = tmp_path / "blob"
    blob.write_bytes(Path(MP4).read_bytes())
    link = tmp_path / "clip.mp4"
    link.symlink_to(blob)
    content, _ = read_file_content(str(link))
    assert content.startswith(f"\n--- MEDIA FILE: {link} (video, video/mp4")


def test_media_under_dangerous_path_gets_access_error(tmp_path, monkeypatch):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(Path(MP4).read_bytes())
    monkeypatch.setattr(utils.security_config, "DANGEROUS_SYSTEM_PATHS", {str(tmp_path)})
    content, _ = read_file_content(str(clip))
    assert content.startswith(f"\n--- ERROR ACCESSING FILE: {clip} ---")


def test_unknown_binary_is_rejected(tmp_path):
    blob = tmp_path / "firmware.bin"
    blob.write_bytes(b"\x7fELF\x00\x00\x00binary")
    content, _ = read_file_content(str(blob))
    assert "--- BINARY FILE:" in content
    assert "not a supported media type" in content


def test_mpeg_transport_stream_is_binary_not_media(tmp_path):
    capture = tmp_path / "capture.mpg"
    capture.write_bytes((b"\x47\x40\x00\x10" + b"\xff" * 184) * 3)
    content, _ = read_file_content(str(capture))
    assert content.startswith(f"\n--- BINARY FILE: {capture} ---")


def test_text_files_unchanged(tmp_path):
    code = tmp_path / "app.py"
    code.write_text("print('hi')\n")
    content, _ = read_file_content(str(code))
    assert "print('hi')" in content


def test_text_extension_with_nul_is_still_text(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_bytes(b"before\x00after\n")
    content, _ = read_file_content(str(notes))
    assert "--- BEGIN FILE:" in content and "after" in content


def test_utf16_file_is_decoded_as_text(tmp_path):
    report = tmp_path / "Localizable.strings"  # unknown extension, full of NUL bytes as UTF-16
    report.write_bytes('"greeting" = "Hallo Welt";\n'.encode("utf-16"))  # "utf-16" writes a BOM
    content, _ = read_file_content(str(report))
    assert "--- BEGIN FILE:" in content
    assert '"greeting" = "Hallo Welt";' in content
    assert "\x00" not in content and "\ufeff" not in content


def test_utf32_file_is_decoded_as_text(tmp_path):
    export = tmp_path / "export.dat"
    export.write_bytes("zeta\n".encode("utf-32"))
    content, _ = read_file_content(str(export))
    assert "--- BEGIN FILE:" in content and "zeta" in content


def test_utf16_prompt_txt_stays_readable(tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_bytes("Summarise the attached recording.\n".encode("utf-16"))  # PowerShell 5.1 '>' output
    prompt_content, remaining = ChatTool().handle_prompt_file([str(prompt), MP4])
    assert prompt_content.strip() == "Summarise the attached recording."
    assert remaining == [MP4]


def test_prompt_txt_placeholder_is_not_used_as_prompt(tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.symlink_to(MP4)  # a media target behind a text name
    prompt_content, _ = ChatTool().handle_prompt_file([str(prompt)])
    assert prompt_content is None


def test_conversation_file_list_skips_media(tmp_path):
    code = tmp_path / "app.py"
    code.write_text("x = 1\n")
    context = ThreadContext(
        thread_id="t1",
        created_at="2026-09-26T00:00:00Z",
        last_updated_at="2026-09-26T00:00:00Z",
        tool_name="chat",
        turns=[
            ConversationTurn(
                role="user",
                content="look",
                timestamp="2026-09-26T00:00:00Z",
                files=[str(code), MP4],
            )
        ],
        initial_context={},
    )
    assert get_conversation_file_list(context) == [str(code)]
```

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_file_reading.py -q -p no:cacheprovider`
Expected: 10 failed, 3 passed (`test_media_under_dangerous_path_gets_access_error`, `test_text_files_unchanged` and `test_text_extension_with_nul_is_still_text` already hold).

**Step 3: Implement**

In `utils/file_utils.py`, add to the imports, directly under the `from .file_types import …` line:

```python
from .media import bom_encoding, looks_binary, media_type_for
```

Insert after the `if not path.is_file():` block (before `# Check file size to prevent memory exhaustion`):

```python
        # Media is sent natively by providers that support it (utils/media.py); never embed it as text.
        # Check the path as given: a media name on a symlink counts even when the target has none.
        media = media_type_for(file_path)
        if media is not None:
            kind, mime = media
            size_mb = path.stat().st_size / (1024 * 1024)
            content = (
                f"\n--- MEDIA FILE: {file_path} ({kind.value}, {mime}, {size_mb:.1f} MB) ---\n"
                f"Not embedded as text. It is attached as native {kind.value} input only when its path is "
                "passed directly in the request's file list.\n"
                "--- END FILE ---\n"
            )
            return content, estimate_tokens(content)

        if looks_binary(str(path)):
            content = (
                f"\n--- BINARY FILE: {file_path} ---\n"
                "Not embedded: binary content that is not a supported media type (pdf, audio, video).\n"
                "--- END FILE ---\n"
            )
            return content, estimate_tokens(content)
```

Replace the decode line

```python
        with open(path, encoding="utf-8", errors="replace") as f:
```

with

```python
        with open(path, encoding=bom_encoding(str(path)) or "utf-8", errors="replace") as f:
```

In `utils/conversation_memory.py`, add `from utils.media import media_type_for` under `from utils.env import get_env`, and in `get_conversation_file_list` make the loop skip media first:

```python
            for file_path in turn.files:
                # Media is never embedded as text in history; it reaches a model only as an attachment.
                # Phase 1: first-turn media is re-sent via initial_context when a follow-up omits its file
                # list (server.py reconstruct_thread_context); later-turn media is re-attached in phase 5.
                if media_type_for(file_path) is not None:
                    continue
```

(the existing `if file_path not in seen_files:` block follows unchanged).

In `tools/shared/base_tool.py` `handle_prompt_file`, stop a placeholder from becoming the prompt — replace

```python
                        if not content.startswith("\n--- ERROR"):
```

with

```python
                        if not content.startswith(("\n--- ERROR", "\n--- MEDIA FILE:", "\n--- BINARY FILE:")):
```

**Step 4: Run tests**

Run: `.zen_venv/bin/python -m pytest tests/test_media_file_reading.py tests/test_file_protection.py tests/test_conversation_memory.py -q -p no:cacheprovider`
Expected: all pass. Then the full suite: baseline + new tests pass, same 3 pre-existing failures.

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add utils/file_utils.py utils/conversation_memory.py tools/shared/base_tool.py tests/test_media_file_reading.py
git commit -m "fix(files): stop decoding media and binary files as text" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Capability flags on `ModelCapabilities`

**Files:**
- Modify: `providers/shared/model_capabilities.py` (fields after `supports_images`; rank bonus after the `supports_images` bonus)
- Test: `tests/test_media_capabilities.py`

**Step 1: Write the failing tests**

```python
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
```

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_capabilities.py -q -p no:cacheprovider`
Expected: `TypeError: ... unexpected keyword argument 'supports_pdf'`.

**Step 3: Implement**

Fields, directly under `supports_images: bool = False`:

```python
    supports_pdf: bool = False
    supports_audio: bool = False
    supports_video: bool = False
```

Method, after `get_effective_temperature`:

```python
    def supported_media_kinds(self) -> frozenset:
        """Media kinds (utils.media.MediaKind) this model accepts as native input."""
        from utils.media import MediaKind

        flags = {
            MediaKind.PDF: self.supports_pdf,
            MediaKind.AUDIO: self.supports_audio,
            MediaKind.VIDEO: self.supports_video,
        }
        return frozenset(kind for kind, enabled in flags.items() if enabled)
```

Rank bonus, after `if self.supports_images: score += 1`:

```python
        score += len(self.supported_media_kinds())
```

The catalog loader (`providers/registries/base.py`) maps JSON keys onto dataclass fields, so `"supports_pdf": true` in any `conf/*_models.json` now loads without further changes.

**Step 4: Run tests**

Run: `.zen_venv/bin/python -m pytest tests/test_media_capabilities.py -q -p no:cacheprovider` then the full suite.
Expected: pass; baseline unchanged (no catalog sets the flags yet).

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add providers/shared/model_capabilities.py tests/test_media_capabilities.py
git commit -m "feat(models): add supports_pdf/audio/video capability flags" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Probe Gemini models live and set catalog flags

**Files:**
- Create: `scripts/probe_media_support.py`
- Create: `tests/media_probe_matrix.py`
- Modify: `conf/gemini_models.json`
- Test: `tests/test_media_catalog_guard.py`

Rule from the design: a flag is set only after a live probe passes. This task probes with the raw `google-genai` SDK, independent of zen's (not yet written) encoder, so the flags are decided by what the API actually does.

**Step 1: Write the probe script**

```python
#!/usr/bin/env python3
"""Probe which Gemini models read PDF/audio/video natively, using the fixtures in tests/fixtures/media.

Usage: GEMINI_API_KEY=... .zen_venv/bin/python scripts/probe_media_support.py [model ...]
Defaults to every model in conf/gemini_models.json. Prints a JSON matrix of verified kinds.
Cost: one short generateContent call per (model, kind) — a few cents in total.
"""

import json
import os
import re
import sys
from pathlib import Path

from google import genai

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "media"
PROBES = {
    "pdf": ("zebra.pdf", "application/pdf", "What code is written in this PDF? Reply with only the code."),
    "audio": ("pelican.wav", "audio/wav", "What code word and number are spoken? Reply with only them."),
    "video": ("otter.mp4", "video/mp4", "What text is shown in this video? Reply with only that text."),
}


def passed(kind: str, text: str) -> bool:
    normalized = re.sub(r"\s+", "", (text or "").upper())
    if kind == "pdf":
        return "ZEBRA-42" in normalized
    if kind == "audio":
        return "PELICAN" in normalized and ("7" in normalized or "SEVEN" in normalized)
    return "OTTER-9" in normalized


def main(models: list[str]) -> int:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    if not models:
        catalog = json.loads((ROOT / "conf" / "gemini_models.json").read_text())
        models = [entry["model_name"] for entry in catalog["models"]]
    results: dict[str, list[str]] = {}
    for model in models:
        verified = []
        for kind, (filename, mime, question) in PROBES.items():
            data = (FIXTURES / filename).read_bytes()
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[{"parts": [{"inline_data": {"mime_type": mime, "data": data}}, {"text": question}]}],
                )
                ok = passed(kind, response.text)
                print(f"{model:32} {kind:6} {'PASS' if ok else 'FAIL'}  {response.text!r:.60}", file=sys.stderr)
            except Exception as exc:  # report and keep probing the rest
                ok = False
                print(f"{model:32} {kind:6} ERROR {exc}", file=sys.stderr)
            if ok:
                verified.append(kind)
        results[model] = verified
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

**Step 2: Run it**

The key is exported by the user's shell (see ground rules); do not source any `.env` file and do not copy the key into the worktree.

```bash
: "${GEMINI_API_KEY:?export GEMINI_API_KEY first}"
.zen_venv/bin/python scripts/probe_media_support.py > /tmp/gemini-media-probe.json
```

Expected: per-model PASS/FAIL lines on stderr; JSON on stdout. A transient 503 is an ERROR line — rerun that model alone before concluding it fails.

**Step 3: Record the matrix**

`tests/media_probe_matrix.py` — fill `PROBED` from the JSON (only kinds that PASSED):

```python
"""Media kinds verified per (provider, model) by a live probe.

Source of truth for the catalog guard test: a catalog may only set supports_pdf/audio/video
for kinds listed here. Update this file and the catalog together, citing the probe run.

gemini: scripts/probe_media_support.py, run 2026-09-26.
"""

PROBED: dict[tuple[str, str], frozenset[str]] = {
    # ("google", "gemini-3.8-flash"): frozenset({"pdf", "audio", "video"}),
}
```

**Step 4: Write the guard test (fails until the catalog matches)**

```python
"""Every media flag in a catalog must be backed by a recorded live probe."""

import json
from pathlib import Path

from tests.media_probe_matrix import PROBED

CONF = Path(__file__).resolve().parent.parent / "conf"
FLAGS = {"supports_pdf": "pdf", "supports_audio": "audio", "supports_video": "video"}
PROVIDER_FOR_FILE = {
    "gemini_models.json": "google",
    "anthropic_models.json": "anthropic",
    "openai_models.json": "openai",
    "xai_models.json": "xai",
    "openrouter_models.json": "openrouter",
}


def test_media_flags_are_probed():
    unverified = []
    for filename, provider in PROVIDER_FOR_FILE.items():
        for entry in json.loads((CONF / filename).read_text())["models"]:
            claimed = {kind for flag, kind in FLAGS.items() if entry.get(flag)}
            verified = PROBED.get((provider, entry["model_name"]), frozenset())
            if claimed - verified:
                unverified.append(f"{provider}/{entry['model_name']}: {sorted(claimed - verified)}")
    assert not unverified, "Media flags without a live probe: " + "; ".join(unverified)


def test_probed_models_are_flagged():
    """The reverse: a passing probe that the catalog forgot to flag is also a mismatch."""
    for (provider, model), kinds in PROBED.items():
        filename = next(name for name, prov in PROVIDER_FOR_FILE.items() if prov == provider)
        entry = next(e for e in json.loads((CONF / filename).read_text())["models"] if e["model_name"] == model)
        claimed = {kind for flag, kind in FLAGS.items() if entry.get(flag)}
        assert claimed == set(kinds), f"{provider}/{model}: catalog {sorted(claimed)} vs probe {sorted(kinds)}"
```

**Step 5: Set the flags in `conf/gemini_models.json`**

For each model with at least one verified kind, add the matching `"supports_pdf": true`, `"supports_audio": true`, `"supports_video": true` lines next to `"supports_images"`. Do not flag anything that did not PASS.

**Step 6: Run tests**

Run: `.zen_venv/bin/python -m pytest tests/test_media_catalog_guard.py -q -p no:cacheprovider`, then the full suite.
Expected: guard passes. If a rank-order test in `tests/` changes because flagged models gained rank, check that the new order is correct (Gemini models moved up relative to peers) before updating the assertion; note it in the commit message.

**Step 7: Commit**

```bash
ruff check . --fix && black . && isort .
git add scripts/probe_media_support.py tests/media_probe_matrix.py tests/test_media_catalog_guard.py conf/gemini_models.json
git commit -m "feat(models): flag Gemini media input from live probe results" \
  -m "Probe results (model -> verified kinds):" -m "$(cat /tmp/gemini-media-probe.json)" \
  -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Provider media contract — no silent drops

**Files:**
- Modify: `providers/base.py` (`ModelProvider` class attribute and a new method)
- Test: `tests/test_media_provider_contract.py`

Every `generate_content` accepts `**kwargs`, so `media=[...]` sent to a provider that ignores it would vanish. `MEDIA_KINDS` declares what a provider can encode; `ensure_media_encodable` enforces it (and the 2 GB size limit) and is called at every call site before `generate_content`.

**Step 1: Write the failing tests**

```python
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
```

Gemini is in the rejecting list on purpose: it gains its encoder (and `MEDIA_KINDS`) in Task 15, which moves it out of this list.

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_provider_contract.py -q -p no:cacheprovider`
Expected: `AttributeError: ... has no attribute 'ensure_media_encodable'` (and `MEDIA_KINDS` for the oversize test).

**Step 3: Implement in `providers/base.py`**

Change the typing import to `from typing import TYPE_CHECKING, Any, Callable, ClassVar, Optional`. Directly under `MODEL_CAPABILITIES: dict[str, Any] = {}` add:

```python

    # Media kinds (utils.media.MediaKind) this provider can encode into a request.
    # Empty means the provider refuses media rather than silently dropping it.
    MEDIA_KINDS: ClassVar[frozenset] = frozenset()
```

and directly after `__init__`:

```python
    def ensure_media_encodable(self, media) -> None:
        """Raise MediaNotSupportedError unless this provider can encode every attachment.

        Called at every call site right before generate_content: each generate_content accepts
        **kwargs, so media passed to a provider without an encoder would otherwise vanish.
        """
        if not media:
            return
        from utils.media import MediaNotSupportedError, check_media_sizes, format_kinds

        check_media_sizes(media)
        unsupported = [attachment for attachment in media if attachment.kind not in self.MEDIA_KINDS]
        if unsupported:
            kinds = format_kinds({attachment.kind for attachment in unsupported})
            names = ", ".join(attachment.name for attachment in unsupported)
            raise MediaNotSupportedError(
                f"{self.get_provider_type().value} provider cannot send {kinds} input yet ({names})."
            )
```

**Step 4: Run tests**, then the full suite. Expected: pass.

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add providers/base.py tests/test_media_provider_contract.py
git commit -m "feat(providers): refuse media a provider cannot encode" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Stop two existing tests leaking state into later tests

**Files:**
- Modify: `tests/test_listmodels_restrictions.py` (`tearDown`, lines 84-89)
- Modify: `tests/test_listmodels.py` (`test_execute_with_custom_api`, ~line 149)

Two pre-existing tests leak state that breaks the registry-based media tests from Task 9 on, but only in a full-suite run (they pass alone):

- `TestListModelsRestrictions.tearDown` pops `GEMINI_API_KEY` (and the OpenRouter keys) after `@patch.dict` has already restored them, so every later test runs without a Gemini key.
- `test_execute_with_custom_api` calls `configure_providers()` under a patched env and leaves the `CUSTOM` provider factory registered; later registry lookups then raise `ValueError: Custom API URL must be provided`.

Fix the tests, not production code (do not swallow the `CUSTOM` error).

**Step 1: Write the failing regression tests**

In `tests/test_listmodels_restrictions.py`, add to `TestListModelsRestrictions` right after `tearDown`:

```python
    def test_teardown_keeps_environment_it_did_not_set(self):
        """Regression: tearDown used to pop GEMINI_API_KEY even when it existed before the test."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "pre-existing-key"}):
            self.tearDown()
            self.assertEqual(os.environ.get("GEMINI_API_KEY"), "pre-existing-key")
```

In `tests/test_listmodels.py`, add to `TestListModelsTool` right after `test_execute_with_custom_api`:

```python
    @pytest.mark.asyncio
    async def test_custom_api_listing_leaves_no_custom_provider(self, tool):
        """Regression: the CUSTOM factory registered above used to leak into every later test."""
        await self.test_execute_with_custom_api(tool)
        assert ProviderType.CUSTOM not in ModelProviderRegistry.get_available_providers()
```

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_listmodels.py tests/test_listmodels_restrictions.py -q -p no:cacheprovider`
Expected: exactly the two new tests fail.

**Step 3: Fix the two tests**

`tests/test_listmodels_restrictions.py` — the whole `tearDown` becomes:

```python
    def tearDown(self):
        """Clean up after tests."""
        ModelProviderRegistry.clear_cache()
        # No env cleanup here: @patch.dict restores the environment when each test returns. Popping keys
        # afterwards deleted GEMINI_API_KEY that existed before the test and broke later tests.
```

`tests/test_listmodels.py` — the body of `test_execute_with_custom_api` becomes:

```python
        env_vars = {"CUSTOM_API_URL": "http://localhost:11434", "DEFAULT_MODEL": "auto"}

        with patch.dict(os.environ, env_vars, clear=True):
            try:
                _reset_and_configure_providers()
                result = await tool.execute({})

                response = json.loads(result[0].text)
                content = response["content"]

                # Check Custom API shows as configured
                assert "Custom/Local API ✅" in content
                assert "http://localhost:11434" in content
                assert "Local models via Ollama" in content
            finally:
                # configure_providers() registered a CUSTOM factory that outlives the patched env;
                # later registry lookups would then fail with "Custom API URL must be provided".
                ModelProviderRegistry.unregister_provider(ProviderType.CUSTOM)
```

**Step 4: Run tests**

Run the two files again (all pass), then the full suite.
Expected: only the 3 known `test_alias_target_restrictions` failures.

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add tests/test_listmodels.py tests/test_listmodels_restrictions.py
git commit -m "test: stop listmodels tests leaking GEMINI_API_KEY removal and the CUSTOM provider" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Capability-aware model selection and availability hints

**Files:**
- Modify: `utils/media.py` (append the hints and error-message section)
- Modify: `providers/registry.py` — `get_preferred_fallback_model` (line 386) and two new classmethods placed just above it
- Test: `tests/test_media_routing.py`, `tests/test_media_hints.py`

- `find_media_capable_models` returns **canonical** names: `get_available_models()` lists every alias too, so it dedupes on `get_capabilities(name).model_name` and ranks those.
- `get_preferred_fallback_model` filters each provider's allowed models by the required media. It raises `MediaNotSupportedError` only **in place of the final hardcoded `return "gemini-3.8-flash"`** — after `if first_available_model: return first_available_model`. The first available model is already filtered, so it is capable; raising before it would reject capable models from providers that state no preference (OpenRouter, Custom, DIAL, Azure).
- `providers_hint` treats a provider as configured when `ModelProviderRegistry.get_provider(...)` returns an instance (registered with a usable key) — not when its env var is merely non-empty (`server.py` treats the placeholder key as unset). It suggests configuring a key only for providers that are not configured; for configured ones it names the real blocker (no encoder yet, the `*_ALLOWED_MODELS` allow-list, or no single model taking the whole mix). The env var name is always in the text.

**Step 1: Write the failing tests**

`tests/test_media_routing.py`:

```python
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
```

`tests/test_media_hints.py`:

```python
"""Messages for media no available model can take: which key to configure, or why a configured provider cannot."""

from pathlib import Path
from unittest.mock import patch

import pytest

import utils.model_restrictions
from providers.gemini import GeminiModelProvider
from providers.registry import ModelProviderRegistry
from utils.media import MediaKind, classify_media, format_media_error, providers_hint

MP4 = str(Path(__file__).parent / "fixtures" / "media" / "otter.mp4")
VIDEO = frozenset({MediaKind.VIDEO})


@pytest.fixture
def fresh_restrictions(monkeypatch):
    """Let a test change *_ALLOWED_MODELS: the restriction service caches the env on first use."""
    monkeypatch.setattr(utils.model_restrictions, "_restriction_service", None)


def test_hint_names_key_when_provider_is_not_configured(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    ModelProviderRegistry.clear_cache()
    try:
        assert providers_hint(VIDEO) == "configure GEMINI_API_KEY"
    finally:
        ModelProviderRegistry.clear_cache()


def test_hint_when_configured_provider_has_no_encoder():
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset()):
        hint = providers_hint(VIDEO)
    assert hint.startswith("GEMINI_API_KEY is configured") and "cannot send video input yet" in hint


def test_hint_blames_allow_list_when_restricted(monkeypatch, fresh_restrictions):
    monkeypatch.setenv("GOOGLE_ALLOWED_MODELS", "gemini-2.5-flash")
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        hint = providers_hint(VIDEO)
    assert not hint.startswith("configure")
    assert "GEMINI_API_KEY is configured, but GOOGLE_ALLOWED_MODELS excludes" in hint


def test_hint_for_configured_unrestricted_provider(fresh_restrictions):
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        hint = providers_hint(frozenset(MediaKind))
    assert hint == "GEMINI_API_KEY is configured, but none of its models takes audio/pdf/video input in one request"


def test_format_media_error_lists_capable_models():
    media = classify_media([MP4])[1]
    message = format_media_error("o3", VIDEO, media, ["gemini-3.8-flash"])
    assert message == (
        "Model 'o3' cannot take video input (otter.mp4). "
        "Models available with your current keys that can: gemini-3.8-flash."
    )


def test_format_media_error_without_capable_models_gives_hint():
    media = classify_media([MP4])[1]
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset()):
        message = format_media_error("o3", VIDEO, media, [])
    assert "No available model supports it: GEMINI_API_KEY is configured" in message
```

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_routing.py tests/test_media_hints.py -q -p no:cacheprovider`
Expected: collection error for `tests/test_media_hints.py` (`ImportError: cannot import name 'format_media_error'`) and `TypeError: ... unexpected keyword argument 'required_media'` in `tests/test_media_routing.py`.

**Step 3: Implement**

Append to the end of `utils/media.py`:

```python
# ---------------------------------------------------------------------------
# Availability hints and error messages
# ---------------------------------------------------------------------------

# Providers whose models can take media once configured: (ProviderType value, key env var,
# allow-list env var, kinds its encoder can send). Later phases add entries.
MEDIA_PROVIDERS: tuple[tuple[str, str, str, frozenset[MediaKind]], ...] = (
    ("google", "GEMINI_API_KEY", "GOOGLE_ALLOWED_MODELS", frozenset(MediaKind)),
)


def providers_hint(kinds: frozenset[MediaKind]) -> str:
    """What would unlock ``kinds``: a key to configure, or why an already configured provider cannot serve it.

    A provider counts as configured when ModelProviderRegistry returns an instance for it (registered
    with a usable key), not when its env var is merely non-empty. The env var name is always named.
    """
    from providers.registry import ModelProviderRegistry
    from providers.shared import ProviderType
    from utils.model_restrictions import get_restriction_service

    label = format_kinds(kinds)
    missing_keys: list[str] = []
    reasons: list[str] = []
    for provider_value, key_env, allow_env, supported in MEDIA_PROVIDERS:
        if not kinds <= supported:
            continue
        provider_type = ProviderType(provider_value)
        provider = ModelProviderRegistry.get_provider(provider_type)
        if provider is None:
            missing_keys.append(key_env)
        elif not kinds <= frozenset(provider.MEDIA_KINDS):
            reasons.append(f"{key_env} is configured, but that provider cannot send {label} input yet")
        elif get_restriction_service().has_restrictions(provider_type):
            reasons.append(f"{key_env} is configured, but {allow_env} excludes every model that can take {label} input")
        else:
            reasons.append(f"{key_env} is configured, but none of its models takes {label} input in one request")
    if missing_keys:
        reasons.insert(0, "configure " + " or ".join(missing_keys))
    return "; ".join(reasons) if reasons else f"no supported provider can take {label} input in one request yet"


def format_media_error(
    model_name: str,
    missing: frozenset[MediaKind],
    media: list[MediaAttachment],
    capable_models: list[str],
) -> str:
    affected = ", ".join(a.name for a in media if a.kind in missing)
    message = f"Model '{model_name}' cannot take {format_kinds(missing)} input ({affected})."
    if capable_models:
        message += " Models available with your current keys that can: " + ", ".join(capable_models) + "."
    else:
        message += f" No available model supports it: {providers_hint(missing)}."
    return message
```

In `providers/registry.py`, directly above `get_preferred_fallback_model`:

```python
    @classmethod
    def _filter_models_for_media(cls, provider, model_names: list[str], required_media: frozenset) -> list[str]:
        """Keep models whose flags cover required_media on a provider that can encode it."""
        if not required_media:
            return model_names
        if not required_media <= frozenset(provider.MEDIA_KINDS):
            return []
        capable = []
        for name in model_names:
            try:
                if required_media <= provider.get_capabilities(name).supported_media_kinds():
                    capable.append(name)
            except (AttributeError, ValueError):
                continue
        return capable

    @classmethod
    def find_media_capable_models(cls, required_media: frozenset, limit: int = 5) -> list[str]:
        """Canonical names of available models (current keys and restrictions) that take required_media, best first.

        get_available_models() lists aliases too; every alias resolves to the same capabilities, so
        dedupe on the canonical ``model_name`` or one model would be listed under several names.
        """
        ranks: dict[str, int] = {}
        for model_name, provider_type in cls.get_available_models(respect_restrictions=True).items():
            provider = cls.get_provider(provider_type)
            if not provider or not cls._filter_models_for_media(provider, [model_name], required_media):
                continue
            capabilities = provider.get_capabilities(model_name)
            ranks.setdefault(capabilities.model_name, capabilities.get_effective_capability_rank())
        ranked = sorted(ranks.items(), key=lambda item: (-item[1], item[0]))
        return [name for name, _ in ranked[:limit]]
```

Change the signature of `get_preferred_fallback_model` to

```python
    @classmethod
    def get_preferred_fallback_model(
        cls, tool_category: Optional["ToolModelCategory"] = None, required_media: frozenset = frozenset()
    ) -> str:
```

filter right after `allowed_models` is computed (line 410):

```python
                allowed_models = cls._get_allowed_models_for_provider(provider, provider_type)
                allowed_models = cls._filter_models_for_media(provider, allowed_models, required_media)
```

and insert the refusal **after** the `if first_available_model: … return first_available_model` block, immediately before `# Ultimate fallback if no providers have models`:

```python
        # Media that no available model can take: refuse rather than return a model that would drop it
        if required_media:
            from utils.media import MediaNotSupportedError, format_kinds, providers_hint

            raise MediaNotSupportedError(
                f"No available model can take {format_kinds(required_media)} input: {providers_hint(required_media)}."
            )
```

Leave `return "gemini-3.8-flash"` in place for media-free calls.

**Step 4: Run tests**, then the full suite. Expected: pass; existing auto-mode tests unchanged; only the 3 known failures.

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add utils/media.py providers/registry.py tests/test_media_routing.py tests/test_media_hints.py
git commit -m "feat(registry): filter auto-mode candidates by required media" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Shared tool helpers — validation, prompt announcement, token reserve

**Files:**
- Modify: `tools/shared/base_tool.py` — four new methods placed just above `_validate_image_limits` (line 1470), and `_prepare_file_content_for_prompt` (around line 1080 and line 1166)
- Test: `tests/test_media_tool_helpers.py`

- `_validate_media_support` refuses oversize files and any kind the model's flags **and** its provider's encoder do not both cover. When a refused file was carried over from the thread's first turn (see the conversation rule in the ground rules), the message says so and how to avoid it.
- `_prepare_file_content_for_prompt` (used by simple tools, the workflow step embedding, consensus and debug's expert context) splits media out with `classify_media` before `read_files` — `read_files` resolves symlinks, so for `clip.mp4 -> blob` it would otherwise describe `blob` as an unsupported binary — announces it with `media_prompt_section`, and subtracts `estimate_media_tokens` from the text budget before its 1,000-token floor.
- `_unattached_thread_media_note` builds the `=== MEDIA NOT ATTACHED ===` note from the thread's turns.

**Step 1: Write the failing tests**

```python
"""BaseTool media helpers: validation, prompt announcement, token reserve, unattached-media note."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from providers.shared import ModelCapabilities, ProviderType
from tools.chat import ChatTool
from tools.shared.exceptions import ToolExecutionError
from utils.conversation_memory import add_turn, create_thread
from utils.media import MEDIA_MAX_BYTES, MediaKind

FIXTURES = Path(__file__).parent / "fixtures" / "media"
MP4 = str(FIXTURES / "otter.mp4")


def _context(model_name, media_flags, provider_kinds):
    caps = ModelCapabilities(
        provider=ProviderType.GOOGLE, model_name=model_name, friendly_name=model_name, **media_flags
    )
    provider = SimpleNamespace(MEDIA_KINDS=frozenset(provider_kinds))
    return SimpleNamespace(model_name=model_name, capabilities=caps, provider=provider)


def _error(exc_info) -> dict:
    return json.loads(str(exc_info.value))


def test_validate_media_support_passes_when_capable():
    tool = ChatTool()
    media = tool._media_from_paths([MP4])
    tool._validate_media_support(media, _context("m", {"supports_video": True}, {MediaKind.VIDEO}))


def test_validate_media_support_names_capable_models():
    tool = ChatTool()
    media = tool._media_from_paths([MP4])
    with patch("providers.registry.ModelProviderRegistry.find_media_capable_models", return_value=["gemini-3.8-flash"]):
        with pytest.raises(ToolExecutionError) as exc:
            tool._validate_media_support(media, _context("o3", {}, set()))
    payload = _error(exc)
    assert "cannot take video input (otter.mp4)" in payload["content"]
    assert "gemini-3.8-flash" in payload["content"]
    assert payload["metadata"]["capable_models"] == ["gemini-3.8-flash"]


def test_validate_media_support_checks_provider_encoder_too():
    tool = ChatTool()
    media = tool._media_from_paths([MP4])
    with patch("providers.registry.ModelProviderRegistry.find_media_capable_models", return_value=[]):
        with pytest.raises(ToolExecutionError):
            # Flags say yes, but the provider has no encoder yet -> still refused.
            tool._validate_media_support(media, _context("m", {"supports_video": True}, set()))


def test_validate_media_support_rejects_oversized_file(tmp_path):
    huge = tmp_path / "huge.mp4"
    with huge.open("wb") as handle:
        handle.write(b"\x00\x00\x00\x10ftypisom\x00\x00\x02\x00")
        handle.truncate(MEDIA_MAX_BYTES + 1)  # sparse: nothing real is written
    tool = ChatTool()
    with pytest.raises(ToolExecutionError) as exc:
        tool._validate_media_support(
            tool._media_from_paths([str(huge)]), _context("m", {"supports_video": True}, {MediaKind.VIDEO})
        )
    assert "huge.mp4 (2.00 GB)" in _error(exc)["content"]
    assert "limited to 2 GB each" in _error(exc)["content"]


def test_validate_media_support_explains_first_turn_carry_over():
    tool = ChatTool()
    media = tool._media_from_paths([MP4])
    with patch("providers.registry.ModelProviderRegistry.find_media_capable_models", return_value=["gemini-3.8-flash"]):
        with pytest.raises(ToolExecutionError) as exc:
            tool._validate_media_support(media, _context("o3", {}, set()), carried_over=[MP4])
    content = _error(exc)["content"]
    assert "otter.mp4 came from the first turn of this conversation" in content
    assert "start a new conversation (no continuation_id)" in content


def test_paths_from_initial_context():
    tool = ChatTool()
    arguments = {"absolute_file_paths": [MP4], "_initial_context_keys": ["absolute_file_paths"]}
    assert tool._paths_from_initial_context(arguments, "absolute_file_paths") == [MP4]
    assert tool._paths_from_initial_context({"absolute_file_paths": [MP4]}, "absolute_file_paths") == []


def test_prompt_announces_media_and_embeds_text(tmp_path):
    code = tmp_path / "app.py"
    code.write_text("print('hi')\n")
    content, processed = ChatTool()._prepare_file_content_for_prompt([str(code), MP4], None, remaining_budget=50_000)
    assert "print('hi')" in content
    assert f"--- MEDIA FILE: {MP4} (video, video/mp4" in content
    assert "attached to this request as native video input" in content
    assert MP4 in processed


def test_prompt_announces_media_name_symlink_not_binary(tmp_path):
    blob = tmp_path / "blob"
    blob.write_bytes(Path(MP4).read_bytes())
    link = tmp_path / "clip.mp4"
    link.symlink_to(blob)
    content, _ = ChatTool()._prepare_file_content_for_prompt([str(link)], None, remaining_budget=50_000)
    assert f"--- MEDIA FILE: {link} (video" in content
    assert "BINARY FILE" not in content  # read_files would have resolved the link to "blob"


def test_media_tokens_are_reserved_from_text_budget(tmp_path):
    code = tmp_path / "big.py"
    code.write_text("x = 1  # padding padding padding\n" * 250)  # roughly 2,000 tokens
    budget = {"remaining_budget": 10_000, "reserve_tokens": 1_000}
    content, _ = ChatTool()._prepare_file_content_for_prompt([str(code), MP4], None, **budget)
    assert "SKIPPED FILES" not in content  # otter.mp4 is estimated at 900 tokens
    with patch("utils.media.estimate_media_tokens", return_value=8_500):
        content, _ = ChatTool()._prepare_file_content_for_prompt([str(code), MP4], None, **budget)
    assert "SKIPPED FILES" in content and "--- MEDIA FILE:" in content


def test_unattached_thread_media_note():
    thread_id = create_thread("chat", {"prompt": "look"})
    add_turn(thread_id, "user", "look at this", files=[MP4])
    tool = ChatTool()
    note = tool._unattached_thread_media_note(thread_id, [])
    assert "=== MEDIA NOT ATTACHED ===" in note and "otter.mp4" in note
    assert tool._unattached_thread_media_note(thread_id, tool._media_from_paths([MP4])) == ""
    assert tool._unattached_thread_media_note(None, []) == ""
```

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_tool_helpers.py -q -p no:cacheprovider`
Expected: `AttributeError: 'ChatTool' object has no attribute '_media_from_paths'` (and the prompt tests fail on the missing announcement).

**Step 3: Implement in `tools/shared/base_tool.py`**

Above `_validate_image_limits`:

```python
    def _media_from_paths(self, paths) -> list:
        """Media attachments (utils.media.MediaAttachment) among explicit file paths."""
        from utils.media import classify_media

        return classify_media(paths)[1]

    def _paths_from_initial_context(self, arguments: dict, key: str) -> list[str]:
        """Paths the server copied into this call from the thread's first turn (reconstruct_thread_context)."""
        if key not in (arguments.get("_initial_context_keys") or ()):
            return []
        return list(arguments.get(key) or [])

    def _validate_media_support(self, media: list, model_context: Any, carried_over=()) -> None:
        """Fail fast unless every attachment is within size limits and the model's flags AND its
        provider's encoder cover it. ``carried_over``: paths re-sent from the thread's first turn."""
        if not media:
            return
        from providers.registry import ModelProviderRegistry
        from tools.models import ToolOutput
        from tools.shared.exceptions import ToolExecutionError
        from utils.media import MediaNotSupportedError, check_media_sizes, format_media_error, required_kinds

        metadata = {"tool_name": self.get_name(), "model": model_context.model_name}
        try:
            check_media_sizes(media)
        except MediaNotSupportedError as exc:
            output = ToolOutput(status="error", content=str(exc), content_type="text", metadata=metadata)
            raise ToolExecutionError(output.model_dump_json()) from exc

        required = required_kinds(media)
        supported = model_context.capabilities.supported_media_kinds() & frozenset(model_context.provider.MEDIA_KINDS)
        missing = required - supported
        if not missing:
            return
        capable = ModelProviderRegistry.find_media_capable_models(required)
        content = format_media_error(model_context.model_name, missing, media, capable)
        carried = [a.name for a in media if a.kind in missing and a.path in set(carried_over)]
        if carried:
            content += (
                f" {', '.join(carried)} came from the first turn of this conversation: its files are re-sent on "
                "every follow-up that omits the file list. Pass the file list explicitly without the media, or "
                "start a new conversation (no continuation_id)."
            )
        metadata.update({"missing_media": sorted(kind.value for kind in missing), "capable_models": capable})
        output = ToolOutput(status="error", content=content, content_type="text", metadata=metadata)
        raise ToolExecutionError(output.model_dump_json())

    def _unattached_thread_media_note(self, continuation_id: Optional[str], media: list) -> str:
        """Prompt note naming media that earlier turns of this thread attached but this request does not."""
        if not continuation_id:
            return ""
        thread = get_thread(continuation_id)
        if not thread:
            return ""
        from utils.media import classify_media

        attached = {attachment.path for attachment in media}
        earlier = classify_media([path for turn in thread.turns for path in (turn.files or [])])[1]
        missing = [attachment for attachment in earlier if attachment.path not in attached]
        if not missing:
            return ""
        listed = "; ".join(attachment.describe() for attachment in missing)
        return (
            "\n\n=== MEDIA NOT ATTACHED ===\n"
            f"Earlier turns of this conversation attached: {listed}. They are NOT attached to this request, "
            "so do not describe their contents from memory; ask for the file to be sent again if you need it.\n"
            "=== END MEDIA NOT ATTACHED ==="
        )
```

(`get_thread`, `Any` and `Optional` are already imported at the top of `base_tool.py`; `ToolExecutionError` is not, hence the local import.)

In `_prepare_file_content_for_prompt`, immediately before

```python
        # Ensure we have a reasonable minimum budget
        effective_max_tokens = max(1000, effective_max_tokens)
```

insert

```python
        # Native media (utils/media.py) is attached to the request by the caller, never read as text.
        # Split it out with the same classification the caller uses, so the prompt announces exactly
        # what is attached, and reserve its estimated tokens before sizing the text-file budget.
        from utils.media import classify_media, estimate_media_tokens, media_prompt_section

        request_files, media = classify_media(request_files)
        effective_max_tokens -= estimate_media_tokens(media)

```

and immediately before `result = "".join(content_parts) if content_parts else ""` insert

```python
        if media:
            content_parts.append(media_prompt_section(media))
            actually_processed_files.extend(attachment.path for attachment in media)

```

**Step 4: Run tests**

Run: `.zen_venv/bin/python -m pytest tests/test_media_tool_helpers.py -q -p no:cacheprovider`, then the full suite.
Expected: pass; only the 3 known failures.

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add tools/shared/base_tool.py tests/test_media_tool_helpers.py
git commit -m "feat(tools): shared media validation, announcement and token reserve" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Simple tools (`chat` and friends) and conversation carry-over

**Files:**
- Modify: `tools/simple/base.py` — `execute()`: after `images = self.get_request_images(request)` (line 316), before `if images:` (line 378), and both `provider.generate_content(` calls (lines 432, 489)
- Modify: `server.py` — `reconstruct_thread_context`, the `initial_context` merge (line 1262)
- Test: `tests/test_media_simple_tool.py`

This task makes the phase-1 conversation rule (ground rules) real and tests it over MCP in both directions: a follow-up on a model that cannot take the carried-over video fails and says where the video came from; a follow-up on the same model gets the video again; a follow-up that sends other files gets the `MEDIA NOT ATTACHED` note.

**Step 1: Write the failing tests**

```python
"""Simple tools (chat and friends) validate native media, pass it to the provider, and track it across turns."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.shared import ModelResponse, ProviderType
from tools.chat import ChatTool
from tools.shared.exceptions import ToolExecutionError
from utils.media import MediaKind
from utils.model_context import ModelContext

FIXTURES = Path(__file__).parent / "fixtures" / "media"
MP4 = str(FIXTURES / "otter.mp4")


def _gemini_reply(text="OTTER-9"):
    return ModelResponse(content=text, usage={}, model_name="gemini-3.8-flash", provider=ProviderType.GOOGLE)


@pytest.fixture
def gemini_encodes_media():
    # The Gemini encoder arrives in Task 15; until then pretend it exists.
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        yield


@pytest.mark.asyncio
async def test_chat_sends_media_to_provider(tmp_path, gemini_encodes_media):
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await ChatTool().execute(
            {
                "prompt": "What text is shown?",
                "absolute_file_paths": [MP4],
                "working_directory_absolute_path": str(tmp_path),
                "model": "gemini-3.8-flash",
                "_model_context": ModelContext("gemini-3.8-flash"),
                "_resolved_model_name": "gemini-3.8-flash",
            }
        )
    media = generate.call_args.kwargs["media"]
    assert [m.name for m in media] == ["otter.mp4"]
    assert "--- MEDIA FILE:" in generate.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_chat_without_media_passes_none(tmp_path):
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply("hi")) as generate:
        await ChatTool().execute(
            {
                "prompt": "hello",
                "working_directory_absolute_path": str(tmp_path),
                "model": "gemini-3.8-flash",
                "_model_context": ModelContext("gemini-3.8-flash"),
                "_resolved_model_name": "gemini-3.8-flash",
            }
        )
    assert generate.call_args.kwargs.get("media") is None


@pytest.mark.asyncio
async def test_incapable_model_fails_before_any_api_call(tmp_path):
    with patch.object(OpenAIModelProvider, "generate_content") as generate:
        with pytest.raises(ToolExecutionError) as exc:
            await ChatTool().execute(
                {
                    "prompt": "What is shown?",
                    "absolute_file_paths": [MP4],
                    "working_directory_absolute_path": str(tmp_path),
                    "model": "o3",
                    "_model_context": ModelContext("o3"),
                    "_resolved_model_name": "o3",
                }
            )
    generate.assert_not_called()
    assert "cannot take video input (otter.mp4)" in json.loads(str(exc.value))["content"]


async def _first_turn(server, tmp_path) -> str:
    """MCP turn 1: chat on Gemini with the video attached. Returns the continuation_id."""
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()):
        result = await server.handle_call_tool(
            "chat",
            {
                "prompt": "What text is shown?",
                "model": "gemini-3.8-flash",
                "absolute_file_paths": [MP4],
                "working_directory_absolute_path": str(tmp_path),
            },
        )
    return json.loads(result[0].text)["continuation_offer"]["continuation_id"]


@pytest.mark.asyncio
async def test_follow_up_on_incapable_model_names_first_turn_media(tmp_path, gemini_encodes_media):
    import server

    thread_id = await _first_turn(server, tmp_path)
    with patch.object(OpenAIModelProvider, "generate_content") as generate:
        with pytest.raises(ToolExecutionError) as exc:
            await server.handle_call_tool(
                "chat",
                {
                    "prompt": "Now summarise it",
                    "model": "o3",
                    "continuation_id": thread_id,
                    "working_directory_absolute_path": str(tmp_path),
                },
            )
    generate.assert_not_called()
    content = json.loads(str(exc.value))["content"]
    assert "cannot take video input (otter.mp4)" in content
    assert "otter.mp4 came from the first turn of this conversation" in content


@pytest.mark.asyncio
async def test_follow_up_on_same_model_re_attaches_first_turn_media(tmp_path, gemini_encodes_media):
    import server

    thread_id = await _first_turn(server, tmp_path)
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await server.handle_call_tool(
            "chat",
            {
                "prompt": "Describe the colours",
                "model": "gemini-3.8-flash",
                "continuation_id": thread_id,
                "working_directory_absolute_path": str(tmp_path),
            },
        )
    assert [m.name for m in generate.call_args.kwargs["media"]] == ["otter.mp4"]
    assert "MEDIA NOT ATTACHED" not in generate.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_follow_up_with_other_files_says_media_is_not_attached(tmp_path, gemini_encodes_media):
    import server

    code = tmp_path / "app.py"
    code.write_text("print('hi')\n")
    thread_id = await _first_turn(server, tmp_path)
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await server.handle_call_tool(
            "chat",
            {
                "prompt": "Review this code instead",
                "model": "gemini-3.8-flash",
                "continuation_id": thread_id,
                "absolute_file_paths": [str(code)],
                "working_directory_absolute_path": str(tmp_path),
            },
        )
    assert generate.call_args.kwargs.get("media") is None
    prompt = generate.call_args.kwargs["prompt"]
    assert "=== MEDIA NOT ATTACHED ===" in prompt and "video otter.mp4" in prompt
```

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_simple_tool.py -q -p no:cacheprovider`
Expected: `test_chat_without_media_passes_none` passes; the other five fail (`KeyError: 'media'`, `DID NOT RAISE`).

**Step 3: Implement**

`tools/simple/base.py` `execute()`, right after `images = self.get_request_images(request)`:

```python

            # Native media (PDF/audio/video) among the request files: validated before any prompt work
            media = self._media_from_paths(self.get_request_files(request))
            self._validate_media_support(
                media, self._model_context, self._paths_from_initial_context(arguments, "absolute_file_paths")
            )
```

Right before `if images:` (the line after `)  # Validate images if any were provided`), at the same indentation as `if images:`:

```python

            # The media list is final: tell the model about earlier-turn media that is not attached this time
            prompt += self._unattached_thread_media_note(continuation_id, media)

```

Before the first `model_response = provider.generate_content(` add `provider.ensure_media_encodable(media)`, and add `media=media or None,` after `images=images if images else None,` in **both** `generate_content(...)` calls (the main call and the retry call).

`server.py` `reconstruct_thread_context` — replace the merge block

```python
    if context.initial_context:
        logger.debug(f"[CONVERSATION_DEBUG] Merging initial context with {len(context.initial_context)} parameters")
        for key, value in context.initial_context.items():
            if key not in enhanced_arguments and key not in ["temperature", "thinking_mode", "model"]:
                enhanced_arguments[key] = value
                logger.debug(f"[CONVERSATION_DEBUG] Merged initial context param: {key}")
```

with

```python
    if context.initial_context:
        logger.debug(f"[CONVERSATION_DEBUG] Merging initial context with {len(context.initial_context)} parameters")
        merged_keys = []
        for key, value in context.initial_context.items():
            if key not in enhanced_arguments and key not in ["temperature", "thinking_mode", "model"]:
                enhanced_arguments[key] = value
                merged_keys.append(key)
                logger.debug(f"[CONVERSATION_DEBUG] Merged initial context param: {key}")
        # Lets tools say so when media the user did not attach this turn was carried over from the first turn
        enhanced_arguments["_initial_context_keys"] = merged_keys
```

Request models ignore unknown keys, like the existing `_model_context` and `_remaining_tokens`.

**Step 4: Run tests**

Run: `.zen_venv/bin/python -m pytest tests/test_media_simple_tool.py -q -p no:cacheprovider`, then the full suite.
Expected: pass. Existing chat tests still pass because media-free calls send `media=None`, which every provider's `**kwargs` ignores.

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add tools/simple/base.py server.py tests/test_media_simple_tool.py
git commit -m "feat(tools): validate and pass native media in simple tools" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Auto mode and the MCP boundary

**Files:**
- Modify: `server.py` — the auto-mode block (line 812) and the file-size check (line 856)
- Modify: `tools/shared/base_tool.py` — `_resolve_model_context` CLI auto branch (line 1414)
- Test: `tests/test_media_auto_mode.py`

Three changes:
- **Auto mode routes on media.** The server and the CLI fallback pass `required_media` to `get_preferred_fallback_model`. When no model can take it, the server returns a tool error with the Task 9 hint.
- **Multi-step workflows.** Workflow turns store no model to reuse, and the final expert call attaches media from every earlier step (`consolidated_findings.relevant_files`) even when the final step narrows `relevant_files`. So for a `WorkflowTool` with a `continuation_id`, the auto block also counts media in that tool's earlier turns (`get_thread(...).turns[*].files`). This cannot be left to `_call_expert_analysis`: `server.py` overwrites `arguments["model"]`, so the tool cannot tell that auto was requested. Simple tools attach only this call's media (the first-turn carry-over is already in `arguments`), so they skip this.
- **MCP size check counts text only.** `check_total_file_size` estimated media at bytes/3.5 tokens, so any media file over about 0.9 MB was rejected as `code_too_large` on Gemini (about 75 KB on o3) before the tool ran — an incapable model reported "too large" instead of "cannot take video", and the encoder and Files API path were unreachable. Only non-media, non-binary paths are checked now, and the check is skipped when none remain. `estimate_file_tokens` is unchanged (conversation memory shares it); do not add a per-media token estimate here, or small-context models would still say "too large" first.

**Step 1: Write the failing tests**

```python
"""Auto mode routes media to capable models; the MCP size check never pre-empts the media check."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.registry import ModelProviderRegistry
from tools.chat import ChatTool
from tools.codereview import CodeReviewTool
from tools.shared.exceptions import ToolExecutionError
from utils.conversation_memory import add_turn, create_thread
from utils.media import MediaKind

MP4 = str(Path(__file__).parent / "fixtures" / "media" / "otter.mp4")


def _sparse_video(tmp_path, size=2 * 1024 * 1024) -> str:
    """A ~2 MB mp4: an 'ftyp' header and a hole. Far over o3's text budget if it were counted as text."""
    clip = tmp_path / "screen.mp4"
    with clip.open("wb") as handle:
        handle.write(b"\x00\x00\x00\x10ftypisom\x00\x00\x02\x00")
        handle.truncate(size)
    return str(clip)


def test_resolve_model_context_passes_required_media():
    tool = ChatTool()
    request = tool.get_request_model()(
        prompt="hi", absolute_file_paths=[MP4], working_directory_absolute_path="/tmp", model="auto"
    )
    with patch.object(ModelProviderRegistry, "get_preferred_fallback_model", return_value="gemini-3.8-flash") as pick:
        tool._resolve_model_context({"absolute_file_paths": [MP4], "model": "auto"}, request)
    assert pick.call_args.kwargs["required_media"] == frozenset({MediaKind.VIDEO})


@pytest.mark.asyncio
async def test_server_auto_mode_passes_required_media(tmp_path):
    import server

    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)),
        patch.object(
            ModelProviderRegistry,
            "get_preferred_fallback_model",
            wraps=ModelProviderRegistry.get_preferred_fallback_model,
        ) as pick,
        patch.object(ChatTool, "execute", return_value=[]),
    ):
        await server.handle_call_tool(
            "chat",
            {
                "prompt": "hi",
                "model": "auto",
                "absolute_file_paths": [MP4],
                "working_directory_absolute_path": str(tmp_path),
            },
        )
    assert pick.call_args_list[0].kwargs["required_media"] == frozenset({MediaKind.VIDEO})


@pytest.mark.asyncio
async def test_server_auto_mode_without_capable_model_is_a_tool_error(tmp_path):
    import server

    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset()):
        with pytest.raises(ToolExecutionError) as exc:
            await server.handle_call_tool(
                "chat",
                {
                    "prompt": "hi",
                    "model": "auto",
                    "absolute_file_paths": [MP4],
                    "working_directory_absolute_path": str(tmp_path),
                },
            )
    payload = json.loads(str(exc.value))
    assert payload["metadata"]["requested_model"] == "auto"  # refused while resolving auto, not by a picked model
    assert payload["content"].startswith("No available model can take video input: GEMINI_API_KEY")


@pytest.mark.asyncio
async def test_server_auto_mode_counts_media_from_earlier_workflow_steps(tmp_path):
    import server

    code = tmp_path / "app.py"
    code.write_text("print('hi')\n")
    thread_id = create_thread("codereview", {"step": "Review the recording", "relevant_files": [MP4]})
    add_turn(thread_id, "assistant", "step 1 recorded", files=[MP4], tool_name="codereview")
    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)),
        patch.object(
            ModelProviderRegistry,
            "get_preferred_fallback_model",
            wraps=ModelProviderRegistry.get_preferred_fallback_model,
        ) as pick,
        patch.object(CodeReviewTool, "execute", return_value=[]),
    ):
        await server.handle_call_tool(
            "codereview",
            {
                "step": "Final step",
                "step_number": 2,
                "total_steps": 2,
                "next_step_required": False,
                "findings": "done",
                "relevant_files": [str(code)],  # the final step narrowed the list: no media in this call
                "model": "auto",
                "continuation_id": thread_id,
            },
        )
    media_calls = [c for c in pick.call_args_list if c.kwargs.get("required_media")]
    assert media_calls and media_calls[-1].kwargs["required_media"] == frozenset({MediaKind.VIDEO})


@pytest.mark.asyncio
async def test_large_media_is_not_counted_as_text_at_mcp_boundary(tmp_path):
    import server

    clip = _sparse_video(tmp_path)
    with patch.object(ChatTool, "execute", return_value=[]) as execute:
        await server.handle_call_tool(
            "chat",
            {
                "prompt": "What happens in this recording?",
                "model": "gemini-3.8-flash",
                "absolute_file_paths": [clip],
                "working_directory_absolute_path": str(tmp_path),
            },
        )
    execute.assert_called_once()  # before the fix: code_too_large (2 MB counted as ~600K text tokens)


@pytest.mark.asyncio
async def test_large_media_on_incapable_model_gets_media_error_not_too_large(tmp_path):
    import server

    clip = _sparse_video(tmp_path)
    with patch.object(OpenAIModelProvider, "generate_content") as generate:
        with pytest.raises(ToolExecutionError) as exc:
            await server.handle_call_tool(
                "chat",
                {
                    "prompt": "What happens in this recording?",
                    "model": "o3",
                    "absolute_file_paths": [clip],
                    "working_directory_absolute_path": str(tmp_path),
                },
            )
    generate.assert_not_called()
    payload = json.loads(str(exc.value))
    assert payload["status"] == "error"
    assert "cannot take video input (screen.mp4)" in payload["content"]
```

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_auto_mode.py -q -p no:cacheprovider`
Expected: all six fail (`KeyError: 'required_media'`, `code_too_large`, content not starting with "No available model").

**Step 3: Implement**

`server.py` — the auto-mode block becomes (keep the `logger.info`, `model_name = resolved_model` and `arguments["model"] = model_name` lines that follow):

```python
        # Handle auto mode at MCP boundary - resolve to specific model
        if model_name.lower() == "auto":
            from tools.workflow.base import WorkflowTool
            from utils.media import MediaNotSupportedError, media_kinds_from_arguments, media_kinds_from_paths

            # Get tool category to determine appropriate model
            tool_category = tool.get_model_category()
            # Route on the media this call attaches. A workflow's final expert call also attaches media
            # from this tool's earlier steps (consolidated relevant_files), and workflow turns store no
            # model to reuse, so include those steps' media too.
            required_media = media_kinds_from_arguments(arguments)
            continuation_id = arguments.get("continuation_id")
            if continuation_id and isinstance(tool, WorkflowTool):
                from utils.conversation_memory import get_thread

                thread = get_thread(continuation_id)
                earlier_files = [
                    path
                    for turn in (thread.turns if thread else [])
                    if turn.tool_name == name
                    for path in (turn.files or [])
                ]
                required_media |= media_kinds_from_paths(earlier_files)
            try:
                resolved_model = ModelProviderRegistry.get_preferred_fallback_model(
                    tool_category, required_media=required_media
                )
            except MediaNotSupportedError as exc:
                error_output = ToolOutput(
                    status="error",
                    content=str(exc),
                    content_type="text",
                    metadata={"tool_name": name, "requested_model": "auto"},
                )
                raise ToolExecutionError(error_output.model_dump_json()) from exc
            logger.info(f"Auto mode resolved to {resolved_model} for {name} (category: {tool_category.value})")
```

`server.py` — the early file-size validation becomes:

```python
        argument_files = arguments.get("absolute_file_paths")
        if argument_files:
            # Only embeddable text counts: native media is checked by the tool against the model's media
            # support (an incapable model must get that error, not "too large"), and binaries are never embedded.
            from utils.media import classify_media, looks_binary

            text_files = [path for path in classify_media(argument_files)[0] if not looks_binary(path)]
            if text_files:
                logger.debug(f"Checking file sizes for {len(text_files)} text files with model {model_name}")
                file_size_check = check_total_file_size(text_files, model_name)
                if file_size_check:
                    logger.warning(f"File size check failed for {name} with model {model_name}")
                    raise ToolExecutionError(ToolOutput(**file_size_check).model_dump_json())
```

`tools/shared/base_tool.py` `_resolve_model_context`, CLI auto branch:

```python
            if model_name.lower() == "auto":
                tool_category = self.get_model_category()
                from providers.registry import ModelProviderRegistry
                from utils.media import media_kinds_from_arguments

                model_name = ModelProviderRegistry.get_preferred_fallback_model(
                    tool_category, required_media=media_kinds_from_arguments(arguments)
                )
```

How the CLI surfaces `MediaNotSupportedError` from here: simple tools catch it in their generic handler and raise `ToolExecutionError("Error in chat: No available model can take …")`, which keeps the hint. Workflow tools do **not** today — `execute_workflow` catches `ValueError` and defers, and the deferred resolution ends in "Model 'auto' is not available". Task 13 adds the explicit handler.

**Step 4: Run tests**, then the full suite. Expected: pass; only the 3 known failures.

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add server.py tools/shared/base_tool.py tests/test_media_auto_mode.py
git commit -m "feat(auto-mode): route media requests to capable models" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Workflow tools (debug, analyze, codereview, …)

**Files:**
- Modify: `tools/workflow/workflow_mixin.py`
  - imports (line 33)
  - `execute_workflow`: the early `_resolve_model_context` try/except (lines 655-667)
  - `_call_expert_analysis` (line 1437): validate, note, `generate_content` (line 1493), exception handling (line 1533)
  - `_force_embed_files_for_expert_analysis` (line 375)
- Test: `tests/test_media_workflow.py`

Where validation lives:
- **In `execute_workflow`, on every step**, right after the early `_resolve_model_context` succeeds (guarded by `if self._model_context is not None`), so a user learns at step 1 of 3 that the model cannot read the recording. Not in `_embed_workflow_files`: that method runs only on the final step and its `except Exception` swallows `ToolExecutionError` (a `RuntimeError`). Tools that never call a model with files (`requires_expert_analysis()` is false: docgen, tracer, planner) skip it.
- **Again before the expert call**, on the consolidated media of all steps, because the model can differ between steps.
- **Auto mode with no capable model:** `except MediaNotSupportedError` → `ToolExecutionError` sits **before** `except ValueError` in `execute_workflow`; otherwise the error is deferred and the CLI prints "Model 'auto' is not available …" with no key hint.

`_force_embed_files_for_expert_analysis` splits media out, announces it with `media_prompt_section` and reserves its tokens, like Task 10 does for `_prepare_file_content_for_prompt`.

**Step 1: Write the failing tests**

```python
"""Workflow tools validate media on every step and send it with the expert analysis call."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.shared import ModelResponse, ProviderType
from tools.analyze import AnalyzeTool
from tools.codereview import CodeReviewTool
from tools.shared.exceptions import ToolExecutionError
from utils.media import MediaKind
from utils.model_context import ModelContext

MP4 = str(Path(__file__).parent / "fixtures" / "media" / "otter.mp4")


def _args(model, context, next_step_required=False, step_number=1, total_steps=1):
    return {
        "step": "Analyze the recording",
        "step_number": step_number,
        "total_steps": total_steps,
        "next_step_required": next_step_required,
        "findings": "Recording shows a banner.",
        "relevant_files": [MP4],
        "model": model,
        "_model_context": context,
        "_resolved_model_name": model,
    }


def _gemini_reply():
    return ModelResponse(
        content='{"status": "analysis_complete"}', usage={}, model_name="gemini-3.8-flash", provider=ProviderType.GOOGLE
    )


@pytest.fixture
def gemini_encodes_media():
    # The Gemini encoder arrives in Task 15; until then pretend it exists.
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        yield


@pytest.mark.asyncio
async def test_expert_analysis_receives_media(gemini_encodes_media):
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await AnalyzeTool().execute(_args("gemini-3.8-flash", ModelContext("gemini-3.8-flash")))
    assert [m.name for m in generate.call_args.kwargs["media"]] == ["otter.mp4"]
    assert "attached to this request as native video input" in generate.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_workflow_rejects_incapable_model_before_expert_call():
    with patch("providers.registry.ModelProviderRegistry.find_media_capable_models", return_value=["gemini-3.8-flash"]):
        with pytest.raises(ToolExecutionError, match="cannot take video"):
            await AnalyzeTool().execute(_args("o3", ModelContext("o3")))


@pytest.mark.asyncio
async def test_intermediate_step_rejects_incapable_model():
    # Step 1 of 3 embeds no files and calls no model, but must still refuse media the model cannot read.
    with patch.object(OpenAIModelProvider, "generate_content") as generate:
        with pytest.raises(ToolExecutionError, match="cannot take video"):
            await AnalyzeTool().execute(_args("o3", ModelContext("o3"), next_step_required=True, total_steps=3))
    generate.assert_not_called()


@pytest.mark.asyncio
async def test_cli_auto_mode_without_capable_provider_reports_media_hint():
    # CLI mode: no _model_context, model "auto", and no provider that can encode video.
    arguments = {
        "step": "Review the screen recording",
        "step_number": 1,
        "total_steps": 1,
        "next_step_required": False,
        "findings": "Initial review request from CLI",
        "relevant_files": [MP4],
        "files_checked": [MP4],
        "review_type": "full",
        "model": "auto",
    }
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset()):
        with pytest.raises(ToolExecutionError) as exc:
            await CodeReviewTool().execute(arguments)
    content = json.loads(str(exc.value))["content"]
    assert "No available model can take video input" in content and "GEMINI_API_KEY" in content
    assert "Model 'auto' is not available" not in content


@pytest.mark.asyncio
async def test_two_step_mcp_workflow_in_auto_mode_keeps_step_one_media(tmp_path, gemini_encodes_media):
    import server

    code = tmp_path / "app.py"
    code.write_text("print('hi')\n")
    step = {"total_steps": 2, "findings": "Banner text visible", "model": "auto"}
    first = await server.handle_call_tool(
        "analyze",
        {
            **step,
            "step": "Analyze the recording",
            "step_number": 1,
            "next_step_required": True,
            "relevant_files": [MP4, str(code)],
        },
    )
    thread_id = json.loads(first[0].text)["continuation_id"]
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await server.handle_call_tool(
            "analyze",
            {
                **step,
                "step": "Final step",
                "step_number": 2,
                "next_step_required": False,
                "relevant_files": [str(code)],
                "continuation_id": thread_id,
            },
        )
    assert [m.name for m in generate.call_args.kwargs["media"]] == ["otter.mp4"]
```

If `AnalyzeTool` requires extra step fields in your checkout (for example `analysis_type`), copy them from `tests/test_analyze*.py`.

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_workflow.py -q -p no:cacheprovider`
Expected: all five fail.

**Step 3: Implement in `tools/workflow/workflow_mixin.py`**

Imports: add `from utils.media import MediaNotSupportedError` under `from utils.conversation_memory import add_turn, create_thread`.

`execute_workflow` — insert a new handler between the early `try:` body and `except ValueError as e:`:

```python
            except MediaNotSupportedError as exc:
                # Auto mode found no model for the attached media: report that now instead of deferring
                # (a deferred resolution falls back to "auto" and fails with a misleading provider error).
                from tools.models import ToolOutput

                output = ToolOutput(status="error", content=str(exc), content_type="text")
                raise ToolExecutionError(output.model_dump_json()) from exc
```

and immediately before `# Handle continuation` (after the `except ValueError` block that sets `self._model_context = None`):

```python
            # Validate this step's media as soon as the model is known, on every step (files are only
            # embedded on the final step). Tools that never call a model with files skip this.
            if self._model_context is not None and self.requires_expert_analysis():
                self._validate_media_support(
                    self._media_from_paths(self.get_request_relevant_files(request)),
                    self._model_context,
                    self._paths_from_initial_context(arguments, "relevant_files"),
                )

```

The existing outer `except ToolExecutionError: raise` in `execute_workflow` carries both errors to the caller. Do not add any media check to `_embed_workflow_files`.

`_call_expert_analysis` — right after `provider = self._model_context.provider`:

```python

            # Native media from every step (consolidated relevant_files). Validate again here: the
            # model can differ from the one that checked earlier steps.
            media = self._media_from_paths(sorted(self.consolidated_findings.relevant_files))
            self._validate_media_support(
                media, self._model_context, self._paths_from_initial_context(arguments, "relevant_files")
            )
            provider.ensure_media_encodable(media)
```

right after the `if self.should_include_files_in_expert_prompt(): …` block (before `# Get system prompt for this tool with localization support`):

```python

            # The media list is final: name earlier-turn media (e.g. from another tool) not attached here
            expert_context += self._unattached_thread_media_note(self.get_request_continuation_id(request), media)
```

add `media=media or None,` after the `images=…` argument of its `provider.generate_content(...)` call, and re-raise validation errors before the generic handler at the end of the method:

```python
        except ToolExecutionError:
            raise  # media validation: the user must see why, not a vague "expert analysis failed"
        except Exception as e:
            logger.error(f"Error calling expert analysis: {e}", exc_info=True)
            return {"error": str(e), "status": "analysis_error"}
```

`_force_embed_files_for_expert_analysis` — after `from utils.file_utils import expand_paths, read_files` add:

```python
        from utils.media import classify_media, estimate_media_tokens, media_prompt_section

        # Native media is attached to the expert call (_call_expert_analysis), never read as text. Announce
        # it from the same classification and reserve its estimated tokens from the text-file budget.
        files, media = classify_media(files)
```

after the `if current_model_context: … else: max_tokens = 100_000  # Fallback` block add:

```python
        max_tokens = max(2_000, max_tokens - estimate_media_tokens(media))  # keeps >= 1,000 tokens for text
```

after the `file_content = read_files(...)` call add `file_content += media_prompt_section(media)`, and change `processed_files = expand_paths(files)` to

```python
        processed_files = expand_paths(files) + [attachment.path for attachment in media]
```

**Step 4: Run tests**, then the full suite. Expected: pass; only the 3 known failures.

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add tools/workflow/workflow_mixin.py tests/test_media_workflow.py
git commit -m "feat(workflow): validate media on every step and send it to expert analysis" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Consensus pre-flight

**Files:**
- Modify: `tools/consensus.py` — module imports (line 31), step 1 setup (after `self.models_to_consult = request.models or []`, line 460), a new method above `_build_continuation_offer` (line 547), and `_consult_model` (`generate_content` at line 618)
- Test: `tests/test_media_consensus.py`

**Step 1: Write the failing tests**

```python
"""Consensus refuses media any listed model cannot read, before consulting anyone."""

from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.shared import ModelResponse, ProviderType
from tools.consensus import ConsensusTool
from tools.shared.exceptions import ToolExecutionError
from utils.media import MediaKind

PDF = str(Path(__file__).parent / "fixtures" / "media" / "zebra.pdf")


def _step1(models):
    return {
        "step": "Should we ship this spec?",
        "step_number": 1,
        "total_steps": len(models),
        "next_step_required": True,
        "findings": "Initial review of the attached spec.",
        "models": [{"model": m, "stance": "neutral"} for m in models],
        "relevant_files": [PDF],
    }


@pytest.mark.asyncio
async def test_consensus_preflight_names_incapable_models():
    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)),
        patch.object(GeminiModelProvider, "generate_content") as generate,
    ):
        with pytest.raises(ToolExecutionError) as exc:
            await ConsensusTool().execute(_step1(["gemini-3.8-flash", "o3"]))
    generate.assert_not_called()  # no model was consulted, not even the capable one
    assert "o3" in str(exc.value)
    assert "gemini-3.8-flash cannot" not in str(exc.value)


@pytest.mark.asyncio
async def test_consensus_sends_media_to_capable_model():
    reply = ModelResponse(content="Ship it.", usage={}, model_name="gemini-3.8-flash", provider=ProviderType.GOOGLE)
    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)),
        patch.object(GeminiModelProvider, "generate_content", return_value=reply) as generate,
    ):
        await ConsensusTool().execute(_step1(["gemini-3.8-flash"]))
    assert [m.name for m in generate.call_args.kwargs["media"]] == ["zebra.pdf"]
    assert "attached to this request as native pdf input" in generate.call_args.kwargs["prompt"]
```

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_consensus.py -q -p no:cacheprovider`
Expected: both fail (`DID NOT RAISE`, `KeyError: 'media'`).

**Step 3: Implement**

`tools/consensus.py` has no `ToolExecutionError` import, and `ConsensusTool.execute` resolves to `WorkflowTool.execute`, so a missing import would surface as a `NameError`. Add it at module level, under `from tools.shared.base_models import ConsolidatedFindings, WorkflowRequest`:

```python
from tools.shared.exceptions import ToolExecutionError
```

The pre-flight method, directly above `_build_continuation_offer`:

```python
    def _preflight_media(self, request) -> None:
        """Before consulting anyone, every listed model must be able to read the attached media."""
        media = self._media_from_paths(request.relevant_files or [])
        if not media:
            return
        from tools.models import ToolOutput
        from utils.media import MediaNotSupportedError, check_media_sizes, format_kinds, required_kinds
        from utils.model_context import ModelContext

        try:
            check_media_sizes(media)
        except MediaNotSupportedError as exc:
            output = ToolOutput(status="error", content=str(exc), content_type="text")
            raise ToolExecutionError(output.model_dump_json()) from exc

        required = required_kinds(media)
        incapable = []
        for model_config in self.models_to_consult:
            context = ModelContext(model_config["model"])
            supported = context.capabilities.supported_media_kinds() & frozenset(context.provider.MEDIA_KINDS)
            if required - supported:
                incapable.append(model_config["model"])
        if incapable:
            output = ToolOutput(
                status="error",
                content=(
                    f"These consensus models cannot take the attached {format_kinds(required)} input: "
                    f"{', '.join(incapable)}. Replace them or remove the media; no model was consulted."
                ),
                content_type="text",
            )
            raise ToolExecutionError(output.model_dump_json())
```

Call `self._preflight_media(request)` on the line right after `self.models_to_consult = request.models or []`.

In `_consult_model`, before `response = provider.generate_content(`:

```python
            # Native media for this step: this model's flags and provider encoder must cover it. A failure
            # becomes this model's "error" entry below; step 1 already refused incapable models up front.
            media = self._media_from_paths(request.relevant_files or [])
            self._validate_media_support(media, model_context)
            provider.ensure_media_encodable(media)
```

and pass `media=media or None,` after `images=…` in that call.

**Step 4: Run tests**, then the full suite (including `tests/test_consensus*.py`).

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add tools/consensus.py tests/test_media_consensus.py
git commit -m "feat(consensus): pre-flight media support for every model" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Gemini encoder (inline and Files API upload)

**Files:**
- Modify: `providers/gemini.py` — imports, class constants, `generate_content` (line 127), two new helpers
- Modify: `tests/test_media_provider_contract.py` — move Gemini out of the rejecting list
- Modify: `tests/test_media_routing.py` — the no-capable-model test
- Test: `tests/test_media_gemini.py`

Layout for media requests (design §4): system prompt in `system_instruction`, then media parts, then the prompt text, then any images. Media-free requests keep today's layout byte for byte.

Upload lifecycle (design decision): zen does not delete Files API uploads — Google deletes them after 48 hours. Each upload's Files API name is recorded in the response metadata (`media_attached[*]["file_name"]`, e.g. `files/abc`) so a user can delete it sooner (`client.files.delete(name=...)`). No deletion code in phase 1.

The upload poll (`time.sleep` up to `UPLOAD_TIMEOUT_S`) runs inside the synchronous `generate_content`, on the event loop like every existing provider call and retry sleep (see ground rules); that is pre-existing behaviour, not something this task changes.

**Step 1: Write the failing tests**

```python
"""Gemini encoder: inline media below the cap, Files API upload above it."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

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
    assert sent["config"].system_instruction == "SYS"
    assert [m["transport"] for m in response.metadata["media_attached"]] == ["inline", "inline"]


def test_media_free_layout_unchanged():
    provider = _provider()
    response = provider.generate_content("hello", "gemini-3.8-flash", system_prompt="SYS")
    sent = _sent(provider)
    assert sent["contents"][0]["parts"] == [{"text": "SYS\n\nhello"}]
    assert sent["config"].system_instruction is None
    assert response.metadata["media_attached"] == []


def test_large_media_is_uploaded_and_named_in_metadata(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(GeminiModelProvider, "INLINE_MEDIA_MAX_BYTES", 1024)  # force upload of the 67 KB wav
    uploaded = SimpleNamespace(
        name="files/abc", uri="https://gen.test/files/abc", mime_type="audio/wav", state=SimpleNamespace(name="ACTIVE")
    )
    provider._client.files.upload.return_value = uploaded
    response = provider.generate_content("Transcribe", "gemini-3.8-flash", media=classify_media([PDF, WAV])[1])
    parts = _sent(provider)["contents"][0]["parts"]
    assert {"file_data": {"file_uri": "https://gen.test/files/abc", "mime_type": "audio/wav"}} in parts
    assert any("inline_data" in p for p in parts)  # the 587-byte PDF still fits inline
    attached = {m["name"]: m for m in response.metadata["media_attached"]}
    assert attached["zebra.pdf"]["transport"] == "inline" and "file_name" not in attached["zebra.pdf"]
    # zen never deletes uploads (Google expires them after 48 h); the name lets a user delete one sooner.
    assert attached["pelican.wav"]["transport"] == "uploaded"
    assert attached["pelican.wav"]["file_name"] == "files/abc"


def test_upload_polls_until_active(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(GeminiModelProvider, "UPLOAD_POLL_INTERVAL_S", 0)
    processing = SimpleNamespace(
        name="files/x", uri="u", mime_type="video/mp4", state=SimpleNamespace(name="PROCESSING")
    )
    active = SimpleNamespace(name="files/x", uri="u", mime_type="video/mp4", state=SimpleNamespace(name="ACTIVE"))
    provider._client.files.upload.return_value = processing
    provider._client.files.get.side_effect = [processing, active]
    result = provider._upload_media(classify_media([MP4])[1][0])
    assert result is active


def test_upload_failure_raises():
    provider = _provider()
    provider._client.files.upload.return_value = SimpleNamespace(
        name="files/x", uri="u", mime_type="video/mp4", state=SimpleNamespace(name="FAILED")
    )
    with pytest.raises(RuntimeError, match="FAILED"):
        provider._upload_media(classify_media([MP4])[1][0])
```

`provider._client` is how the tests inject a fake SDK client: `GeminiModelProvider.client` is a property that lazily builds `genai.Client` into `self._client`.

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_gemini.py -q -p no:cacheprovider`
Expected: all six fail (`MEDIA_KINDS` is empty, `media_attached` is missing from the metadata, `_upload_media` does not exist).

**Step 3: Implement in `providers/gemini.py`**

Imports: add `import time` and `from pathlib import Path` after `import logging`, and `from utils.media import MediaKind` after `from utils.image_utils import validate_image`.

Class constants, directly above `# Model-specific thinking token limits` / `MAX_THINKING_TOKENS = {`:

```python
    MEDIA_KINDS = frozenset(MediaKind)
    # Gemini caps a request at 100 MB; base64 inflates by 4/3 and the prompt needs room,
    # so keep raw inline media under 70 MB and upload the rest to the Files API.
    INLINE_MEDIA_MAX_BYTES = 70 * 1024 * 1024
    UPLOAD_POLL_INTERVAL_S = 5
    UPLOAD_TIMEOUT_S = 600

```

Helpers, directly above `_process_image`:

```python
    def _upload_media(self, attachment):
        """Upload one attachment to the Gemini Files API and wait until it is ACTIVE.

        zen never deletes uploads: Google deletes them after 48 hours. The Files API name is recorded
        in the response metadata (media_attached[*]["file_name"]) so a user can delete one sooner.
        """
        uploaded = self.client.files.upload(
            file=attachment.path, config={"mime_type": attachment.mime_type, "display_name": attachment.name}
        )
        deadline = time.monotonic() + self.UPLOAD_TIMEOUT_S
        while uploaded.state is not None and uploaded.state.name == "PROCESSING":
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"Gemini Files API: {attachment.name} still PROCESSING after {self.UPLOAD_TIMEOUT_S}s"
                )
            time.sleep(self.UPLOAD_POLL_INTERVAL_S)
            uploaded = self.client.files.get(name=uploaded.name)
        if uploaded.state is not None and uploaded.state.name == "FAILED":
            raise RuntimeError(f"Gemini Files API upload of {attachment.name} ended in state FAILED")
        return uploaded

    def _build_media_parts(self, media) -> tuple[list[dict], list[dict]]:
        """Inline what fits under INLINE_MEDIA_MAX_BYTES (largest files upload first); keep input order."""
        inline_total = sum(attachment.size_bytes for attachment in media)
        to_upload = set()
        for attachment in sorted(media, key=lambda a: a.size_bytes, reverse=True):
            if inline_total <= self.INLINE_MEDIA_MAX_BYTES:
                break
            to_upload.add(attachment.path)
            inline_total -= attachment.size_bytes

        parts, attached = [], []
        for attachment in media:
            record = {"name": attachment.name, "kind": attachment.kind.value, "bytes": attachment.size_bytes}
            if attachment.path in to_upload:
                uploaded = self._upload_media(attachment)
                file_data = {"file_uri": uploaded.uri, "mime_type": uploaded.mime_type or attachment.mime_type}
                parts.append({"file_data": file_data})
                record.update(transport="uploaded", file_name=uploaded.name)
            else:
                data = base64.b64encode(Path(attachment.path).read_bytes()).decode()
                parts.append({"inline_data": {"mime_type": attachment.mime_type, "data": data}})
                record["transport"] = "inline"
            attached.append(record)
        return parts, attached

```

`generate_content`: add `media: Optional[list] = None,` after `images: Optional[list[str]] = None,`, then replace the block

```python
        # Add system and user prompts as text
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        else:
            full_prompt = prompt

        parts.append({"text": full_prompt})
```

with

```python
        # Media first, then the prompt text. With media the system prompt goes to system_instruction
        # (a stable prefix); media-free requests keep today's layout byte for byte.
        media_attached: list[dict] = []
        if media:
            self.ensure_media_encodable(media)
            media_parts, media_attached = self._build_media_parts(media)
            parts.extend(media_parts)
            parts.append({"text": prompt})
        else:
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            parts.append({"text": full_prompt})
```

Directly before `# Add max output tokens if specified`:

```python
        if media and system_prompt:
            generation_config.system_instruction = system_prompt

```

In the returned `ModelResponse.metadata`, add `"media_attached": media_attached,` after `"safety_feedback": safety_feedback_details,`.

Uploads happen while the parts are built, before `_attempt` is defined, so the retry loop never re-uploads.

`tests/test_media_provider_contract.py`: change the parametrize line to

```python
@pytest.mark.parametrize("provider_cls", [AnthropicProvider, OpenAIModelProvider, XAIModelProvider])
```

`tests/test_media_routing.py`: `test_auto_mode_with_media_and_no_encoder_raises` now fails because Gemini has an encoder. Replace it with a test that keeps its intent — no capable model → `MediaNotSupportedError` naming `GEMINI_API_KEY` — using an allow-list that leaves no Gemini model. `get_restriction_service()` caches the environment on first use, so the singleton must be reset or the new env var has no effect (monkeypatch restores it afterwards). Add `import utils.model_restrictions` to the imports (after `import pytest`, in its own first-party block) and replace the test with:

```python
def test_auto_mode_with_media_and_no_capable_model_raises(monkeypatch):
    # An allow-list that leaves no Gemini model -> nothing can serve video. The restriction service
    # caches the env on first use, so reset it; monkeypatch restores the original afterwards.
    monkeypatch.setenv("GOOGLE_ALLOWED_MODELS", "none-such")
    monkeypatch.setattr(utils.model_restrictions, "_restriction_service", None)
    with pytest.raises(MediaNotSupportedError, match="GEMINI_API_KEY is configured, but GOOGLE_ALLOWED_MODELS"):
        ModelProviderRegistry.get_preferred_fallback_model(
            ToolModelCategory.FAST_RESPONSE, required_media=frozenset({MediaKind.VIDEO})
        )
```

**Step 4: Run tests**

Run: `.zen_venv/bin/python -m pytest tests/test_media_gemini.py tests/test_media_provider_contract.py tests/test_media_routing.py -q -p no:cacheprovider`, then the full suite.
Expected: pass; only the 3 known failures. Tests that need "no provider can encode" (Tasks 9, 12 and 13) patch `GeminiModelProvider.MEDIA_KINDS` to `frozenset()` explicitly, so they keep passing.

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add providers/gemini.py tests/test_media_gemini.py tests/test_media_provider_contract.py tests/test_media_routing.py
git commit -m "feat(gemini): send PDF/audio/video natively, uploading above the inline cap" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: File-list descriptions mention media

**Files:**
- Modify: `tools/shared/base_models.py` (new `MEDIA_FILES_NOTE` constant above `WORKFLOW_FIELD_DESCRIPTIONS`)
- Modify: `tools/chat.py` (`CHAT_FIELD_DESCRIPTIONS["absolute_file_paths"]`)
- Modify: the tool-specific `relevant_files` descriptions of the workflow tools that call a model with files: `tools/analyze.py`, `tools/codereview.py`, `tools/consensus.py`, `tools/debug.py`, `tools/precommit.py`, `tools/refactor.py`, `tools/secaudit.py`, `tools/testgen.py`, and `tools/thinkdeep.py` (schema override)
- Test: `tests/test_media_field_descriptions.py`

The shared `WORKFLOW_FIELD_DESCRIPTIONS["relevant_files"]` is the wrong place: analyze, codereview, consensus, debug, precommit, refactor, secaudit and testgen override `relevant_files` with their own description (merged after the shared fields in `tools/workflow/schema_builders.py`), so the shared text reaches only thinkdeep, docgen and tracer — and docgen and tracer never send files to a model (`requires_model()` is false). So the note goes on each tool-specific description, plus a thinkdeep override, and not on docgen or tracer.

**Step 1: Write the failing test**

```python
"""File-list descriptions mention native media exactly for the tools that send files to a model."""

import pytest

from tools import (
    AnalyzeTool,
    ChatTool,
    CodeReviewTool,
    ConsensusTool,
    DebugIssueTool,
    DocgenTool,
    PrecommitTool,
    RefactorTool,
    SecauditTool,
    TestGenTool,
    ThinkDeepTool,
    TracerTool,
)
from tools.shared.base_models import MEDIA_FILES_NOTE

SENDS_FILES_TO_A_MODEL = [
    AnalyzeTool,
    CodeReviewTool,
    ConsensusTool,
    DebugIssueTool,
    PrecommitTool,
    RefactorTool,
    SecauditTool,
    TestGenTool,
    ThinkDeepTool,
]


def _description(tool, field):
    return tool.get_input_schema()["properties"][field]["description"]


@pytest.mark.parametrize("tool_cls", SENDS_FILES_TO_A_MODEL)
def test_workflow_tools_that_call_a_model_mention_media(tool_cls):
    assert _description(tool_cls(), "relevant_files").endswith(MEDIA_FILES_NOTE)


@pytest.mark.parametrize("tool_cls", [DocgenTool, TracerTool])
def test_tools_that_never_send_files_to_a_model_do_not(tool_cls):
    assert MEDIA_FILES_NOTE not in _description(tool_cls(), "relevant_files")


def test_chat_mentions_media():
    assert _description(ChatTool(), "absolute_file_paths").endswith(MEDIA_FILES_NOTE)
```

**Step 2: Run to verify it fails**

Run: `.zen_venv/bin/python -m pytest tests/test_media_field_descriptions.py -q -p no:cacheprovider`
Expected: collection error, `ImportError: cannot import name 'MEDIA_FILES_NOTE'`.

**Step 3: Implement**

`tools/shared/base_models.py`, directly above `# Workflow-specific field descriptions`:

```python
# Appended to the file-list descriptions of tools that send files to a model (chat, and the workflow
# tools with an expert or consensus model call); not to docgen/tracer, which never call a model with files.
MEDIA_FILES_NOTE = (
    " PDF, audio (wav/mp3/m4a/aac/ogg/flac) and video (mp4/mov/webm/mpeg) files are sent to the model as "
    "native media when it supports them; the request fails with a list of capable models otherwise."
)

```

For each of these tools, add `MEDIA_FILES_NOTE` to its existing `from tools.shared.base_models import …` line and add one line directly after the closing `}` of its descriptions dict (each dict is followed by the request class that reads it):

| File | Line to add after the dict |
|---|---|
| `tools/analyze.py` | `ANALYZE_WORKFLOW_FIELD_DESCRIPTIONS["relevant_files"] += MEDIA_FILES_NOTE` |
| `tools/codereview.py` | `CODEREVIEW_WORKFLOW_FIELD_DESCRIPTIONS["relevant_files"] += MEDIA_FILES_NOTE` |
| `tools/consensus.py` | `CONSENSUS_WORKFLOW_FIELD_DESCRIPTIONS["relevant_files"] += MEDIA_FILES_NOTE` |
| `tools/debug.py` | `DEBUG_INVESTIGATION_FIELD_DESCRIPTIONS["relevant_files"] += MEDIA_FILES_NOTE` |
| `tools/precommit.py` | `PRECOMMIT_WORKFLOW_FIELD_DESCRIPTIONS["relevant_files"] += MEDIA_FILES_NOTE` |
| `tools/refactor.py` | `REFACTOR_FIELD_DESCRIPTIONS["relevant_files"] += MEDIA_FILES_NOTE` |
| `tools/secaudit.py` | `SECAUDIT_WORKFLOW_FIELD_DESCRIPTIONS["relevant_files"] += MEDIA_FILES_NOTE` |
| `tools/testgen.py` | `TESTGEN_WORKFLOW_FIELD_DESCRIPTIONS["relevant_files"] += MEDIA_FILES_NOTE` |

`tools/thinkdeep.py`: change its import to `from tools.shared.base_models import MEDIA_FILES_NOTE, WORKFLOW_FIELD_DESCRIPTIONS, WorkflowRequest` and add as the first entry of `thinkdeep_field_overrides` in `get_input_schema`:

```python
            "relevant_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": WORKFLOW_FIELD_DESCRIPTIONS["relevant_files"] + MEDIA_FILES_NOTE,
            },
```

`tools/chat.py`: add `MEDIA_FILES_NOTE` to its `from tools.shared.base_models import …` line and make the entry

```python
    "absolute_file_paths": (
        "Full, absolute file paths to relevant code in order to share with external model" + MEDIA_FILES_NOTE
    ),
```

**Step 4: Run tests**

Run: `.zen_venv/bin/python -m pytest tests/test_media_field_descriptions.py -q -p no:cacheprovider`, then the full suite. If a schema snapshot test compares these strings, update it in the same commit.

**Step 5: Commit**

```bash
ruff check . --fix && black . && isort .
git add tools/shared/base_models.py tools/chat.py tools/analyze.py tools/codereview.py tools/consensus.py tools/debug.py tools/precommit.py tools/refactor.py tools/secaudit.py tools/testgen.py tools/thinkdeep.py tests/test_media_field_descriptions.py
git commit -m "docs(tools): describe native media on file-list fields" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Live probes through zen, CLI smoke test, final verification

**Files:**
- Create: `tests/test_media_live.py` (integration)
- Modify: `docs/plans/BACKLOG.md` (mark phase 1 done)

**Step 1: Live integration test through zen's own provider**

```python
"""Live media probes through zen's providers. Costs a few cents. Run with -m integration."""

import os
from pathlib import Path

import pytest

from providers.gemini import GeminiModelProvider
from tests.media_probe_matrix import PROBED
from utils.media import classify_media, estimate_media_tokens

FIXTURES = Path(__file__).parent / "fixtures" / "media"
CASES = {
    "pdf": ("zebra.pdf", "What code is written in this PDF? Reply with only the code.", ("ZEBRA-42",)),
    "audio": ("pelican.wav", "What code word and number are spoken? Reply with only them.", ("PELICAN",)),
    "video": ("otter.mp4", "What text is shown in this video? Reply with only that text.", ("OTTER-9",)),
}
GEMINI = [
    (model, kind) for (provider, model), kinds in PROBED.items() if provider == "google" for kind in sorted(kinds)
]
PROMPT_TOKEN_ALLOWANCE = 100  # the question and system prompt


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="needs GEMINI_API_KEY")
@pytest.mark.parametrize("model,kind", GEMINI)
def test_gemini_reads_media(model, kind):
    filename, question, markers = CASES[kind]
    media = classify_media([str(FIXTURES / filename)])[1]
    response = GeminiModelProvider(api_key=os.environ["GEMINI_API_KEY"]).generate_content(
        question, model, system_prompt="Answer tersely.", media=media
    )
    text = response.content.upper().replace(" ", "")
    assert all(marker in text for marker in markers), response.content
    # The estimate reserved from the text budget (utils/media.py) must not undercount real usage.
    input_tokens = response.usage.get("input_tokens")
    estimate = estimate_media_tokens(media)
    assert (
        input_tokens is None or input_tokens <= estimate + PROMPT_TOKEN_ALLOWANCE
    ), f"{model}/{kind}: {input_tokens} input tokens, media estimate {estimate} + {PROMPT_TOKEN_ALLOWANCE}"
```

Run:

```bash
: "${GEMINI_API_KEY:?export GEMINI_API_KEY first}"
.zen_venv/bin/python -m pytest tests/test_media_live.py -m integration -q -p no:cacheprovider
```

Expected: every (model, kind) passes and the summary says **0 skipped** — a skip means the key was not visible or `PROBED` is empty, which is not a pass. A marker failure here after Task 6's raw-SDK probe passed means zen's encoder is wrong, not the model. If only the token assertion fails, the estimate in `utils/media.py` undercounts for that kind: raise the matching constant (`PDF_TOKENS_PER_PAGE`, `AUDIO_TOKENS_PER_SECOND` or `VIDEO_TOKENS_PER_SECOND`) to at least the observed figure (the failure message prints both numbers), update the expected values in `tests/test_media_limits.py`, rerun, and say so in the commit message.

**Step 2: CLI smoke test**

```bash
: "${GEMINI_API_KEY:?export GEMINI_API_KEY first}"
.zen_venv/bin/zen chat "What text is shown in this video?" -f tests/fixtures/media/otter.mp4 --model flash --json
.zen_venv/bin/zen chat "What code is written here?" -f tests/fixtures/media/zebra.pdf --json   # auto mode
.zen_venv/bin/zen chat "What is shown?" -f tests/fixtures/media/otter.mp4 --model grok-4.7 --json; echo "exit=$?"
```

Expected: the first two answer with the marker (auto mode resolves to a Gemini model). The third fails fast: it prints plain text (not JSON, even with `--json`) starting `Error: {"status":"error","content":"Model 'grok-4.7' cannot take video input (otter.mp4). Models available with your current keys that can: gemini-…`, followed by `exit=1`. That no API call is made is covered by `test_incapable_model_fails_before_any_api_call` (Task 11), which asserts `generate_content` is never called; do not look for it in `logs/mcp_activity.log` — only `server.py` writes that log, and the CLI does not.

**Step 3: Backlog**

In `docs/plans/BACKLOG.md` under "Media input", set status to "Phase 1 (core + Gemini) implemented on `feat/media-input`; phases 2–5 pending".

**Step 4: Full verification**

```bash
ruff check . && black --check . && isort --check-only .
.zen_venv/bin/python -m pytest tests/ -q -m "not integration" -p no:cacheprovider
```

Expected: lint clean; all new tests pass; only the 3 pre-existing `test_alias_target_restrictions` failures remain.

**Step 5: Commit**

```bash
git add tests/test_media_live.py docs/plans/BACKLOG.md
git commit -m "test(media): live Gemini probes through zen; mark phase 1 done" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Done when

- `zen chat -f video.mp4` answers from the video on Gemini, in both auto mode and with `--model flash`, over the CLI and over MCP (files well above 1 MB included: the MCP size check counts text only).
- Any non-Gemini model given media fails before an API call, naming capable models; when no model can take it, the error names the key to configure or the configured provider's real blocker.
- No media or binary file is ever embedded as UTF-8 text, and UTF-16/UTF-32 text files stay readable.
- Media paths get the same path security as text files, files over 2 GB fail fast, and media tokens are reserved from the text budget.
- Every media flag in a catalog is backed by `tests/media_probe_matrix.py`, and the live suite passes for all of them with 0 skipped.
- Unit suite: baseline + new tests, only the 3 pre-existing failures.
