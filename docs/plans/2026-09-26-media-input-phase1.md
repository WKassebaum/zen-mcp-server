# Media Input Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** PDF, audio and video files passed through `--files` / `absolute_file_paths` / `relevant_files` are sent to Gemini models as native media, and every other model fails fast with a message naming models that can take them.

**Architecture:** Per-model capability flags (`supports_pdf/audio/video`) on `ModelCapabilities`, a small `utils/media.py` that classifies explicit file paths, a provider-level `MEDIA_KINDS` declaration so no provider can silently drop media, capability-aware auto-mode selection, and a Gemini encoder (inline base64, Files API upload above the inline cap). Design: `docs/plans/2026-09-26-media-input-design.md`. Later phases add Claude/OpenAI, xAI, OpenRouter, continuation re-attach and caching.

**Tech Stack:** Python 3.12, pydantic, pytest, `google-genai` 1.46 (installed; do not upgrade), the MCP server in `server.py`, the click CLI in `src/zen_cli/main.py`.

---

## Ground rules for the engineer

- **Work in the worktree:** `/Users/wrk/WorkDev/MCP-Dev/zen-media-input` on branch `feat/media-input`. Never edit `/Users/wrk/WorkDev/MCP-Dev/zen-cli` — that checkout backs the user's live zen MCP server.
- **Python:** always `.zen_venv/bin/python` in the worktree. Its package versions are pinned to match the live venv; a fresh `pip install` pulls breaking major versions (`mcp` 2.x crashes `server.py`), so do not reinstall.
- **Baseline:** 955 passed, 3 failed. The 3 failures are pre-existing and unrelated: `tests/test_alias_target_restrictions.py::…gemini…` (three tests). Any other failure is yours.
- **Test command:** `.zen_venv/bin/python -m pytest tests/ -q -m "not integration" -p no:cacheprovider`. Do not rely on `./code_quality_checks.sh` for the test count — it runs pytest with `-x` and stops at the pre-existing failure. Use it for lint only.
- **Lint before each commit:** `.zen_venv/bin/ruff check . --fix && .zen_venv/bin/black . && .zen_venv/bin/isort .`
- **Commit trailer:** every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **No silent drops:** if you find a code path where media could be ignored without an error, that is a bug in this plan — stop and fix it, do not work around it.

---

### Task 1: Media test fixtures

**Files:**
- Create: `tests/fixtures/media/zebra.pdf`, `tests/fixtures/media/pelican.wav`, `tests/fixtures/media/otter.mp4`
- Create: `scripts/generate_media_fixtures.py`

These three files were generated and verified against live models on 2026-09-26. Each carries one unambiguous marker.

| File | Size | Marker |
|---|---|---|
| `zebra.pdf` | 582 B | text `ZEBRA-42` |
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

**Step 1: Write the failing tests**

```python
"""Tests for utils.media classification helpers."""

from pathlib import Path

import pytest

from utils.media import (
    MediaAttachment,
    MediaKind,
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


@pytest.mark.parametrize("key", ["absolute_file_paths", "relevant_files", "files"])
def test_media_kinds_from_arguments(key):
    assert media_kinds_from_arguments({key: [MP4]}) == frozenset({MediaKind.VIDEO})
    assert media_kinds_from_arguments({key: None}) == frozenset()
    assert media_kinds_from_arguments({}) == frozenset()


def test_media_attachment_is_hashable():
    _, media = classify_media([PDF])
    assert isinstance(media[0], MediaAttachment)
    assert len({media[0], media[0]}) == 1
```

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_utils.py -q -p no:cacheprovider`
Expected: collection error, `ModuleNotFoundError: No module named 'utils.media'`.

**Step 3: Write the implementation**

```python
"""Native media attachments (PDF, audio, video) for model requests.

Media files are never read as text. They are detected from explicit file paths by
extension *and* magic bytes, carried alongside the prompt, and encoded by providers
that declare support for them (``ModelProvider.MEDIA_KINDS``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class MediaKind(str, Enum):
    PDF = "pdf"
    AUDIO = "audio"
    VIDEO = "video"


class MediaNotSupportedError(ValueError):
    """Raised when media cannot be sent to the selected model or provider."""


# Extension -> (kind, MIME type). Keep in sync with provider MIME support.
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

# Provider env vars that unlock each media kind; later phases add entries.
MEDIA_PROVIDER_KEYS: dict[str, frozenset[MediaKind]] = {
    "GEMINI_API_KEY": frozenset(MediaKind),
}


def _magic_matches(extension: str, head: bytes) -> bool:
    """Cheap signature check so a mislabelled text file is never sent as media."""
    if extension == ".pdf":
        return head.startswith(b"%PDF")
    if extension == ".wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if extension == ".mp3":
        return head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)
    if extension in (".mp4", ".mov", ".m4a"):
        return head[4:8] == b"ftyp" or head[4:8] in (b"moov", b"mdat", b"wide", b"free")
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


def media_type_for(path: str) -> Optional[tuple[MediaKind, str]]:
    """Return (kind, mime) if ``path`` is an existing, correctly signed media file."""
    try:
        p = Path(path)
        extension = p.suffix.lower()
        if extension not in MEDIA_TYPES or not p.is_file():
            return None
        with p.open("rb") as handle:
            head = handle.read(16)
    except OSError:
        return None
    return MEDIA_TYPES[extension] if _magic_matches(extension, head) else None


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


def classify_media(paths: Optional[Iterable[str]]) -> tuple[list[str], list[MediaAttachment]]:
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
        media.append(MediaAttachment(path=path, kind=kind, mime_type=mime, size_bytes=Path(path).stat().st_size))
    return text_paths, media


def required_kinds(media: Iterable[MediaAttachment]) -> frozenset[MediaKind]:
    return frozenset(attachment.kind for attachment in media)


def looks_binary(path: str, sample_size: int = 8192) -> bool:
    """True if the first bytes contain a NUL — the file is not text we can embed."""
    try:
        with open(path, "rb") as handle:
            return b"\x00" in handle.read(sample_size)
    except OSError:
        return False


def media_kinds_from_arguments(arguments: dict[str, Any]) -> frozenset[MediaKind]:
    """Media kinds referenced by raw tool arguments (used before a request model exists)."""
    paths: list[str] = []
    for key in FILE_ARGUMENT_KEYS:
        value = arguments.get(key)
        if isinstance(value, (list, tuple)):
            paths.extend(str(item) for item in value)
    return required_kinds(classify_media(paths)[1])


def format_kinds(kinds: Iterable[MediaKind]) -> str:
    return "/".join(sorted(kind.value for kind in kinds))


def providers_hint(kinds: frozenset[MediaKind]) -> str:
    """Which provider keys would unlock ``kinds``, e.g. 'GEMINI_API_KEY'."""
    keys = [key for key, supported in MEDIA_PROVIDER_KEYS.items() if kinds <= supported]
    return ", ".join(keys) if keys else "no configured provider type supports this combination yet"


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
        message += f" No available model supports it; configure one of: {providers_hint(missing)}."
    return message
```

**Step 4: Run tests**

Run: `.zen_venv/bin/python -m pytest tests/test_media_utils.py -q -p no:cacheprovider`
Expected: all pass.

**Step 5: Commit**

```bash
git add utils/media.py tests/test_media_utils.py
git commit -m "feat(media): add media classification helpers"
```

---

### Task 3: Never read media or binaries as text

**Files:**
- Modify: `utils/file_utils.py` — `read_file_content`, insert right after the `if not path.is_file():` block (currently ~line 461) and **before** the size check
- Modify: `utils/conversation_memory.py` — `get_conversation_file_list` (~line 494 loop)
- Test: `tests/test_media_file_reading.py`

Why before the size check: a 40 MB video currently hits "FILE TOO LARGE"; a 2 MB video is decoded as UTF-8 garbage. Both are wrong.

**Step 1: Write the failing tests**

```python
"""Media and binary files must never be embedded as text."""

from pathlib import Path

from utils.conversation_memory import ConversationTurn, ThreadContext, get_conversation_file_list
from utils.file_utils import read_file_content

FIXTURES = Path(__file__).parent / "fixtures" / "media"


def test_media_file_gets_placeholder_not_garbage():
    content, tokens = read_file_content(str(FIXTURES / "otter.mp4"))
    assert "--- MEDIA FILE:" in content
    assert "video/mp4" in content
    assert "�" not in content  # no replacement characters from a UTF-8 decode
    assert tokens < 200


def test_pdf_placeholder_names_kind():
    content, _ = read_file_content(str(FIXTURES / "zebra.pdf"))
    assert "(pdf, application/pdf" in content


def test_unknown_binary_is_rejected(tmp_path):
    blob = tmp_path / "firmware.bin"
    blob.write_bytes(b"\x7fELF\x00\x00\x00binary")
    content, _ = read_file_content(str(blob))
    assert "--- BINARY FILE:" in content
    assert "not a supported media type" in content


def test_text_files_unchanged(tmp_path):
    code = tmp_path / "app.py"
    code.write_text("print('hi')\n")
    content, _ = read_file_content(str(code))
    assert "print('hi')" in content


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
                files=[str(code), str(FIXTURES / "otter.mp4")],
            )
        ],
        initial_context={},
    )
    assert get_conversation_file_list(context) == [str(code)]
```

If `ThreadContext` / `ConversationTurn` require other fields, copy the constructor pattern from `tests/test_conversation_memory.py`.

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_file_reading.py -q -p no:cacheprovider`
Expected: the placeholder and binary tests fail (content contains decoded garbage); `test_text_files_unchanged` passes.

**Step 3: Implement**

In `utils/file_utils.py`, add to the imports: `from .media import looks_binary, media_type_for`. Then insert after the `is_file()` check:

```python
        # Media is sent natively by providers that support it (utils/media.py); never embed it as text.
        media = media_type_for(str(path))
        if media is not None:
            kind, mime = media
            size_mb = path.stat().st_size / (1024 * 1024)
            content = (
                f"\n--- MEDIA FILE: {file_path} ({kind.value}, {mime}, {size_mb:.1f} MB) ---\n"
                f"Not embedded as text: attached to this request as native {kind.value} input.\n"
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

The placeholder says "attached to this request" — Task 8 onward guarantees that is true or the request fails before sending.

In `utils/conversation_memory.py` `get_conversation_file_list`, inside the `for file_path in turn.files:` loop, skip media first:

```python
            for file_path in turn.files:
                # Phase 1: media is only attached on the turn that provided it; re-attach arrives in phase 5.
                if media_type_for(file_path) is not None:
                    continue
```

and add `from utils.media import media_type_for` to that module's imports.

**Step 4: Run tests**

Run: `.zen_venv/bin/python -m pytest tests/test_media_file_reading.py tests/test_file_protection.py tests/test_conversation_memory.py -q -p no:cacheprovider`
Expected: all pass. Then the full suite: 955 + new tests pass, same 3 pre-existing failures.

**Step 5: Commit**

```bash
git add utils/file_utils.py utils/conversation_memory.py tests/test_media_file_reading.py
git commit -m "fix(files): stop decoding media and binary files as text"
```

---

### Task 4: Capability flags on `ModelCapabilities`

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

        flags = {MediaKind.PDF: self.supports_pdf, MediaKind.AUDIO: self.supports_audio, MediaKind.VIDEO: self.supports_video}
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
git add providers/shared/model_capabilities.py tests/test_media_capabilities.py
git commit -m "feat(models): add supports_pdf/audio/video capability flags"
```

---

### Task 5: Probe Gemini models live and set catalog flags

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

Run (the key lives in the live checkout's `.env`; do not copy it into the worktree):
`set -a; source /Users/wrk/WorkDev/MCP-Dev/zen-cli/.env; set +a; .zen_venv/bin/python scripts/probe_media_support.py > /tmp/gemini-media-probe.json`
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
git add scripts/probe_media_support.py tests/media_probe_matrix.py tests/test_media_catalog_guard.py conf/gemini_models.json
git commit -m "feat(models): flag Gemini media input from live probe results"
```

Paste the probe summary (model → kinds) into the commit body.

---

### Task 6: Provider media contract — no silent drops

**Files:**
- Modify: `providers/base.py` (`ModelProvider` class attributes and a new method)
- Test: `tests/test_media_provider_contract.py`

Every `generate_content` accepts `**kwargs`, so `media=[...]` sent to a provider that ignores it would vanish. `MEDIA_KINDS` declares what a provider can encode; `ensure_media_encodable` enforces it and is called at every call site before `generate_content`.

**Step 1: Write the failing tests**

```python
from pathlib import Path

import pytest

from providers.anthropic import AnthropicProvider
from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.xai import XAIModelProvider
from utils.media import MediaNotSupportedError, classify_media

FIXTURES = Path(__file__).parent / "fixtures" / "media"


def _media():
    return classify_media([str(FIXTURES / "otter.mp4")])[1]


@pytest.mark.parametrize("provider_cls", [AnthropicProvider, OpenAIModelProvider, XAIModelProvider, GeminiModelProvider])
def test_providers_without_encoder_reject_media(provider_cls):
    provider = provider_cls(api_key="test-key")
    with pytest.raises(MediaNotSupportedError, match="otter.mp4"):
        provider.ensure_media_encodable(_media())


def test_empty_media_is_always_fine():
    XAIModelProvider(api_key="test-key").ensure_media_encodable([])
    XAIModelProvider(api_key="test-key").ensure_media_encodable(None)
```

Gemini is in the rejecting list on purpose: it gains its encoder (and `MEDIA_KINDS`) in Task 12. Task 12 moves it out of this list.

**Step 2: Run to verify they fail**

Run: `.zen_venv/bin/python -m pytest tests/test_media_provider_contract.py -q -p no:cacheprovider`
Expected: `AttributeError: ... has no attribute 'ensure_media_encodable'`.

**Step 3: Implement in `providers/base.py`**

Add `ClassVar` to the typing import, then on `ModelProvider`:

```python
    # Media kinds (utils.media.MediaKind) this provider can encode into a request.
    # Empty means the provider refuses media rather than silently dropping it.
    MEDIA_KINDS: ClassVar[frozenset] = frozenset()

    def ensure_media_encodable(self, media) -> None:
        """Raise MediaNotSupportedError if this provider cannot encode every attachment."""
        if not media:
            return
        from utils.media import MediaNotSupportedError, format_kinds

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
git add providers/base.py tests/test_media_provider_contract.py
git commit -m "feat(providers): refuse media a provider cannot encode"
```

---

### Task 7: Capability-aware model selection in the registry

**Files:**
- Modify: `providers/registry.py` — `get_preferred_fallback_model` (~line 386) and two new classmethods
- Test: `tests/test_media_routing.py`

**Step 1: Write the failing tests**

```python
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
    after = ModelProviderRegistry.get_preferred_fallback_model(ToolModelCategory.FAST_RESPONSE, required_media=frozenset())
    assert before == after


def test_auto_mode_with_video_picks_capable_model(gemini_encodes_media):
    model = ModelProviderRegistry.get_preferred_fallback_model(
        ToolModelCategory.FAST_RESPONSE, required_media=frozenset({MediaKind.VIDEO})
    )
    provider = ModelProviderRegistry.get_provider_for_model(model)
    assert MediaKind.VIDEO in provider.get_capabilities(model).supported_media_kinds()


def test_auto_mode_with_media_and_no_encoder_raises():
    # Gemini has flags from Task 5 but no encoder yet (MEDIA_KINDS empty) -> nothing can serve it.
    with pytest.raises(MediaNotSupportedError, match="GEMINI_API_KEY"):
        ModelProviderRegistry.get_preferred_fallback_model(
            ToolModelCategory.FAST_RESPONSE, required_media=frozenset({MediaKind.VIDEO})
        )


def test_find_media_capable_models(gemini_encodes_media):
    models = ModelProviderRegistry.find_media_capable_models(frozenset({MediaKind.PDF}), limit=3)
    assert 0 < len(models) <= 3
    assert all(m.startswith("gemini") for m in models)
```

**Step 2: Run to verify they fail**

Expected: `TypeError: ... unexpected keyword argument 'required_media'`.

**Step 3: Implement in `providers/registry.py`**

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
        """Available models (current keys and restrictions) that can take required_media, best first."""
        ranked: list[tuple[int, str]] = []
        for model_name, provider_type in cls.get_available_models(respect_restrictions=True).items():
            provider = cls.get_provider(provider_type)
            if not provider or not cls._filter_models_for_media(provider, [model_name], required_media):
                continue
            ranked.append((provider.get_capabilities(model_name).get_effective_capability_rank(), model_name))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [name for _, name in ranked[:limit]]
```

In `get_preferred_fallback_model`, change the signature to
`def get_preferred_fallback_model(cls, tool_category: Optional["ToolModelCategory"] = None, required_media: frozenset = frozenset()) -> str:`
and filter right after `allowed_models` is computed:

```python
                allowed_models = cls._get_allowed_models_for_provider(provider, provider_type)
                allowed_models = cls._filter_models_for_media(provider, allowed_models, required_media)
```

Before the "No models available from any provider" ultimate fallback, refuse instead of returning a model that cannot take the media:

```python
        if required_media:
            from utils.media import MediaNotSupportedError, format_kinds, providers_hint

            raise MediaNotSupportedError(
                f"No available model can take {format_kinds(required_media)} input. "
                f"Configure one of: {providers_hint(required_media)}."
            )
```

Place that check before `if first_available_model:` too — a first-available model that lacks the media is not a valid answer.

**Step 4: Run tests**, then the full suite. Expected: pass; existing auto-mode tests unchanged.

**Step 5: Commit**

```bash
git add providers/registry.py tests/test_media_routing.py
git commit -m "feat(registry): filter auto-mode candidates by required media"
```

---

### Task 8: Tool-level validation and the simple-tool path (`chat` and friends)

**Files:**
- Modify: `tools/shared/base_tool.py` — two new methods next to `_validate_image_limits`
- Modify: `tools/simple/base.py` — `execute()` after `images = self.get_request_images(request)` (~line 313), and both `provider.generate_content(` calls (~lines 432, 489)
- Test: `tests/test_media_simple_tool.py`

**Step 1: Write the failing tests**

```python
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.shared import ModelCapabilities, ModelResponse, ProviderType
from tools.chat import ChatTool
from tools.shared.exceptions import ToolExecutionError
from utils.media import MediaKind
from utils.model_context import ModelContext

FIXTURES = Path(__file__).parent / "fixtures" / "media"
MP4 = str(FIXTURES / "otter.mp4")


def _context(model_name, media_flags, provider_kinds):
    caps = ModelCapabilities(provider=ProviderType.GOOGLE, model_name=model_name, friendly_name=model_name, **media_flags)
    provider = SimpleNamespace(MEDIA_KINDS=frozenset(provider_kinds))
    return SimpleNamespace(model_name=model_name, capabilities=caps, provider=provider)


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
    payload = json.loads(str(exc.value))
    assert "cannot take video input (otter.mp4)" in payload["content"]
    assert "gemini-3.8-flash" in payload["content"]


def test_validate_media_support_checks_provider_encoder_too():
    tool = ChatTool()
    media = tool._media_from_paths([MP4])
    with patch("providers.registry.ModelProviderRegistry.find_media_capable_models", return_value=[]):
        with pytest.raises(ToolExecutionError):
            # Flags say yes, but the provider has no encoder yet -> still refused.
            tool._validate_media_support(media, _context("m", {"supports_video": True}, set()))


@pytest.mark.asyncio
async def test_chat_sends_media_to_provider(tmp_path):
    response = ModelResponse(content="OTTER-9", usage={}, model_name="gemini-3.8-flash", provider=ProviderType.GOOGLE)
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)), patch.object(
        GeminiModelProvider, "generate_content", return_value=response
    ) as generate:
        context = ModelContext("gemini-3.8-flash")
        await ChatTool().execute(
            {
                "prompt": "What text is shown?",
                "absolute_file_paths": [MP4],
                "working_directory_absolute_path": str(tmp_path),
                "model": "gemini-3.8-flash",
                "_model_context": context,
                "_resolved_model_name": "gemini-3.8-flash",
            }
        )
    media = generate.call_args.kwargs["media"]
    assert [m.name for m in media] == ["otter.mp4"]
    assert "--- MEDIA FILE:" in generate.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_chat_without_media_passes_none(tmp_path):
    response = ModelResponse(content="hi", usage={}, model_name="gemini-3.8-flash", provider=ProviderType.GOOGLE)
    with patch.object(GeminiModelProvider, "generate_content", return_value=response) as generate:
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
```

`test_chat_sends_media_to_provider` relies on Task 5 having flagged `gemini-3.8-flash` for video. If the probe did not verify video for it, use a model that it did verify.

**Step 2: Run to verify they fail**

Expected: `AttributeError: 'ChatTool' object has no attribute '_media_from_paths'`.

**Step 3: Implement**

In `tools/shared/base_tool.py`, next to `_validate_image_limits`:

```python
    def _media_from_paths(self, paths) -> list:
        """Media attachments (utils.media.MediaAttachment) among explicit file paths."""
        from utils.media import classify_media

        return classify_media(paths)[1]

    def _validate_media_support(self, media: list, model_context: Any) -> None:
        """Fail fast unless the model's flags AND its provider's encoder cover every attachment."""
        if not media:
            return
        from providers.registry import ModelProviderRegistry
        from tools.models import ToolOutput
        from utils.media import format_media_error, required_kinds

        required = required_kinds(media)
        supported = model_context.capabilities.supported_media_kinds() & frozenset(model_context.provider.MEDIA_KINDS)
        missing = required - supported
        if not missing:
            return
        capable = ModelProviderRegistry.find_media_capable_models(required)
        output = ToolOutput(
            status="error",
            content=format_media_error(model_context.model_name, missing, media, capable),
            content_type="text",
            metadata={
                "tool_name": self.get_name(),
                "model": model_context.model_name,
                "missing_media": sorted(kind.value for kind in missing),
                "capable_models": capable,
            },
        )
        raise ToolExecutionError(output.model_dump_json())
```

(`ToolExecutionError` is already imported in `base_tool.py`; if not, import it from `tools.shared.exceptions`.)

In `tools/simple/base.py` `execute()`, right after `images = self.get_request_images(request)`:

```python
            # Native media (PDF/audio/video) among the request files; validated before any prompt work
            media = self._media_from_paths(self.get_request_files(request))
            self._validate_media_support(media, self._model_context)
```

Before the first `provider.generate_content(` call add `provider.ensure_media_encodable(media)`, and add `media=media or None,` to **both** `generate_content(...)` calls (the main call and the retry call).

**Step 4: Run tests**

Run: `.zen_venv/bin/python -m pytest tests/test_media_simple_tool.py -q -p no:cacheprovider`, then the full suite.
Expected: pass. Existing chat tests still pass because media-free calls send `media=None`, which every provider's `**kwargs` ignores.

**Step 5: Commit**

```bash
git add tools/shared/base_tool.py tools/simple/base.py tests/test_media_simple_tool.py
git commit -m "feat(tools): validate and pass native media in simple tools"
```

---

### Task 9: Auto mode knows about media (MCP boundary and CLI)

**Files:**
- Modify: `server.py` — auto-mode block (~line 812)
- Modify: `tools/shared/base_tool.py` — `_resolve_model_context` CLI fallback (~line 1410)
- Test: `tests/test_media_auto_mode.py`

**Step 1: Write the failing tests**

```python
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.registry import ModelProviderRegistry
from tools.chat import ChatTool
from tools.models import ToolModelCategory
from utils.media import MediaKind

MP4 = str(Path(__file__).parent / "fixtures" / "media" / "otter.mp4")


def test_resolve_model_context_passes_required_media():
    tool = ChatTool()
    request = tool.get_request_model()(prompt="hi", absolute_file_paths=[MP4], working_directory_absolute_path="/tmp", model="auto")
    with patch.object(ModelProviderRegistry, "get_preferred_fallback_model", return_value="gemini-3.8-flash") as pick:
        tool._resolve_model_context({"absolute_file_paths": [MP4], "model": "auto"}, request)
    assert pick.call_args.kwargs["required_media"] == frozenset({MediaKind.VIDEO})


@pytest.mark.asyncio
async def test_server_auto_mode_passes_required_media(tmp_path):
    import server

    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)), patch.object(
        ModelProviderRegistry, "get_preferred_fallback_model", wraps=ModelProviderRegistry.get_preferred_fallback_model
    ) as pick, patch.object(ChatTool, "execute", return_value=[]):
        await server.handle_call_tool(
            "chat",
            {"prompt": "hi", "model": "auto", "absolute_file_paths": [MP4], "working_directory_absolute_path": str(tmp_path)},
        )
    assert pick.call_args_list[0].kwargs["required_media"] == frozenset({MediaKind.VIDEO})
```

If `handle_call_tool` has a different name or signature in `server.py`, use the function containing the `# Handle auto mode at MCP boundary` comment.

**Step 2: Run to verify they fail**

Expected: `KeyError: 'required_media'` (the kwarg is not passed yet).

**Step 3: Implement**

`server.py`, in the auto-mode block:

```python
        if model_name.lower() == "auto":
            from utils.media import MediaNotSupportedError, media_kinds_from_arguments

            tool_category = tool.get_model_category()
            required_media = media_kinds_from_arguments(arguments)
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
```

(keep the existing logging and `arguments["model"] = model_name` lines that follow).

`tools/shared/base_tool.py` `_resolve_model_context`, CLI auto branch:

```python
            if model_name.lower() == "auto":
                from providers.registry import ModelProviderRegistry
                from utils.media import media_kinds_from_arguments

                tool_category = self.get_model_category()
                model_name = ModelProviderRegistry.get_preferred_fallback_model(
                    tool_category, required_media=media_kinds_from_arguments(arguments)
                )
```

A `MediaNotSupportedError` here is a `ValueError`, which callers of `_resolve_model_context` already surface as a model-resolution error.

**Step 4: Run tests**, then the full suite. Expected: pass.

**Step 5: Commit**

```bash
git add server.py tools/shared/base_tool.py tests/test_media_auto_mode.py
git commit -m "feat(auto-mode): route media requests to capable models"
```

---

### Task 10: Workflow tools (debug, analyze, codereview, …)

**Files:**
- Modify: `tools/workflow/workflow_mixin.py`
  - the method that embeds step files (contains the log line `Embedded {len(processed_files)} relevant_files for final analysis`, ~line 544): validate early
  - `_call_expert_analysis` (~line 1437): validate and pass media to `generate_content` (~line 1493)
- Test: `tests/test_media_workflow.py`

Validate at the first step that carries media, so a user does not spend several steps before learning the model cannot read their recording. Validate again before the expert call because the model can change between steps.

**Step 1: Write the failing test**

```python
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.shared import ModelResponse, ProviderType
from tools.analyze import AnalyzeTool
from tools.shared.exceptions import ToolExecutionError
from utils.media import MediaKind
from utils.model_context import ModelContext

MP4 = str(Path(__file__).parent / "fixtures" / "media" / "otter.mp4")


def _args(model, context):
    return {
        "step": "Analyze the recording",
        "step_number": 1,
        "total_steps": 1,
        "next_step_required": False,
        "findings": "Recording shows a banner.",
        "relevant_files": [MP4],
        "model": model,
        "_model_context": context,
        "_resolved_model_name": model,
    }


@pytest.mark.asyncio
async def test_expert_analysis_receives_media():
    response = ModelResponse(content='{"status": "analysis_complete"}', usage={}, model_name="gemini-3.8-flash",
                             provider=ProviderType.GOOGLE)
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)), patch.object(
        GeminiModelProvider, "generate_content", return_value=response
    ) as generate:
        await AnalyzeTool().execute(_args("gemini-3.8-flash", ModelContext("gemini-3.8-flash")))
    assert [m.name for m in generate.call_args.kwargs["media"]] == ["otter.mp4"]


@pytest.mark.asyncio
async def test_workflow_rejects_incapable_model_before_expert_call():
    with patch("providers.registry.ModelProviderRegistry.find_media_capable_models", return_value=["gemini-3.8-flash"]):
        with pytest.raises(ToolExecutionError, match="cannot take video"):
            await AnalyzeTool().execute(_args("o3", ModelContext("o3")))
```

If `AnalyzeTool` requires extra step fields (e.g. `analysis_type`), copy them from `tests/test_analyze*.py`.

**Step 2: Run to verify they fail.**

**Step 3: Implement**

In the step-file embedding method, right after the model context is resolved (after the `self._current_model_name = model_name` assignments) and before `_prepare_file_content_for_prompt`:

```python
            self._validate_media_support(self._media_from_paths(request_files), self._model_context)
```

In `_call_expert_analysis`, before `model_response = provider.generate_content(`:

```python
            media = self._media_from_paths(sorted(self.consolidated_findings.relevant_files))
            self._validate_media_support(media, self._model_context)
            provider.ensure_media_encodable(media)
```

and add `media=media or None,` to that `generate_content(...)` call.

`_call_expert_analysis` may catch exceptions and convert them to an error payload; make sure a `ToolExecutionError` from validation propagates (re-raise it before any generic `except Exception`), otherwise the user gets a vague "expert analysis failed".

**Step 4: Run tests**, then the full suite.

**Step 5: Commit**

```bash
git add tools/workflow/workflow_mixin.py tests/test_media_workflow.py
git commit -m "feat(workflow): validate and send native media to expert analysis"
```

---

### Task 11: Consensus pre-flight

**Files:**
- Modify: `tools/consensus.py` — step 1 setup (after `self.models_to_consult = request.models or []`, ~line 460) and `_consult_model` (~line 574, `generate_content` at ~618)
- Test: `tests/test_media_consensus.py`

**Step 1: Write the failing tests**

```python
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
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
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        with pytest.raises(ToolExecutionError) as exc:
            await ConsensusTool().execute(_step1(["gemini-3.8-flash", "o3"]))
    assert "o3" in str(exc.value)
    assert "gemini-3.8-flash cannot" not in str(exc.value)
```

**Step 2: Run to verify it fails.**

**Step 3: Implement**

A pre-flight method on `ConsensusTool`:

```python
    def _preflight_media(self, request) -> None:
        """Before consulting anyone, every listed model must be able to read the attached media."""
        media = self._media_from_paths(request.relevant_files or [])
        if not media:
            return
        from tools.models import ToolOutput
        from utils.media import format_kinds, required_kinds
        from utils.model_context import ModelContext

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

Call `self._preflight_media(request)` right after `self.models_to_consult = request.models or []`.

In `_consult_model`, before `response = provider.generate_content(`:

```python
            media = self._media_from_paths(request.relevant_files or [])
            provider.ensure_media_encodable(media)
```

and pass `media=media or None` to that call.

**Step 4: Run tests**, then the full suite (including `tests/test_consensus*.py`).

**Step 5: Commit**

```bash
git add tools/consensus.py tests/test_media_consensus.py
git commit -m "feat(consensus): pre-flight media support for every model"
```

---

### Task 12: Gemini encoder (inline and Files API upload)

**Files:**
- Modify: `providers/gemini.py` — class constants, `generate_content` (~line 127), two new helpers
- Modify: `tests/test_media_provider_contract.py` — move Gemini out of the rejecting list
- Test: `tests/test_media_gemini.py`

Layout for media requests (design §4): system prompt in `system_instruction`, then media parts, then the prompt text, then any images. Media-free requests keep today's layout byte for byte.

**Step 1: Write the failing tests**

```python
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
    provider.generate_content("hello", "gemini-3.8-flash", system_prompt="SYS")
    sent = _sent(provider)
    assert sent["contents"][0]["parts"] == [{"text": "SYS\n\nhello"}]
    assert sent["config"].system_instruction is None


def test_large_media_is_uploaded(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(GeminiModelProvider, "INLINE_MEDIA_MAX_BYTES", 1024)  # force upload of the 67 KB wav
    uploaded = SimpleNamespace(name="files/abc", uri="https://gen.test/files/abc", mime_type="audio/wav",
                               state=SimpleNamespace(name="ACTIVE"))
    provider._client.files.upload.return_value = uploaded
    response = provider.generate_content("Transcribe", "gemini-3.8-flash", media=classify_media([PDF, WAV])[1])
    parts = _sent(provider)["contents"][0]["parts"]
    assert {"file_data": {"file_uri": "https://gen.test/files/abc", "mime_type": "audio/wav"}} in parts
    assert any("inline_data" in p for p in parts)  # the 582-byte PDF still fits inline
    assert {m["name"]: m["transport"] for m in response.metadata["media_attached"]} == {
        "zebra.pdf": "inline",
        "pelican.wav": "uploaded",
    }


def test_upload_polls_until_active(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(GeminiModelProvider, "UPLOAD_POLL_INTERVAL_S", 0)
    processing = SimpleNamespace(name="files/x", uri="u", mime_type="video/mp4", state=SimpleNamespace(name="PROCESSING"))
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

`provider._client` is how the tests inject a fake SDK client. Check how `GeminiModelProvider.client` is defined (a property that lazily builds `genai.Client`); if the backing attribute has a different name, use that name in `_provider()` instead of `_client`.

**Step 2: Run to verify they fail.**

**Step 3: Implement in `providers/gemini.py`**

Imports: `import time`, `from pathlib import Path`, `from utils.media import MediaKind`.

Class constants:

```python
    MEDIA_KINDS = frozenset(MediaKind)
    # Gemini caps a request at 100 MB; base64 inflates by 4/3 and the prompt needs room,
    # so keep raw inline media under 70 MB and upload the rest to the Files API.
    INLINE_MEDIA_MAX_BYTES = 70 * 1024 * 1024
    UPLOAD_POLL_INTERVAL_S = 5
    UPLOAD_TIMEOUT_S = 600
```

Helpers:

```python
    def _upload_media(self, attachment):
        """Upload one attachment to the Gemini Files API and wait until it is ACTIVE."""
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
            if attachment.path in to_upload:
                uploaded = self._upload_media(attachment)
                parts.append({"file_data": {"file_uri": uploaded.uri, "mime_type": uploaded.mime_type or attachment.mime_type}})
                transport = "uploaded"
            else:
                data = base64.b64encode(Path(attachment.path).read_bytes()).decode()
                parts.append({"inline_data": {"mime_type": attachment.mime_type, "data": data}})
                transport = "inline"
            attached.append(
                {"name": attachment.name, "kind": attachment.kind.value, "bytes": attachment.size_bytes, "transport": transport}
            )
        return parts, attached
```

`generate_content`: add `media: Optional[list] = None,` after `images`, then replace the "Add system and user prompts as text" block with:

```python
        media_attached: list[dict] = []
        if media:
            self.ensure_media_encodable(media)
            media_parts, media_attached = self._build_media_parts(media)
            parts.extend(media_parts)
            parts.append({"text": prompt})  # system prompt goes to system_instruction for a stable prefix
        else:
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            parts.append({"text": full_prompt})
```

After `generation_config` is created:

```python
        if media and system_prompt:
            generation_config.system_instruction = system_prompt
```

In the returned `ModelResponse.metadata`, add `"media_attached": media_attached,`.

Uploads happen before `_attempt` is defined, so the retry loop never re-uploads.

Finally, in `tests/test_media_provider_contract.py`, remove `GeminiModelProvider` from the parametrized rejecting list.

**Step 4: Run tests**

Run: `.zen_venv/bin/python -m pytest tests/test_media_gemini.py tests/test_media_provider_contract.py tests/test_media_routing.py -q -p no:cacheprovider`, then the full suite.
Expected: pass. `test_auto_mode_with_media_and_no_encoder_raises` in Task 7 now fails because Gemini has an encoder — change it to use a provider-type restriction that leaves no Gemini models (`GOOGLE_ALLOWED_MODELS=none-such`), keeping its intent: no capable model → `MediaNotSupportedError` naming `GEMINI_API_KEY`.

**Step 5: Commit**

```bash
git add providers/gemini.py tests/test_media_gemini.py tests/test_media_provider_contract.py tests/test_media_routing.py
git commit -m "feat(gemini): send PDF/audio/video natively, uploading above the inline cap"
```

---

### Task 13: Live probes through zen, docs, final verification

**Files:**
- Create: `tests/test_media_live.py` (integration)
- Modify: `tools/chat.py` (`CHAT_FIELD_DESCRIPTIONS["absolute_file_paths"]`), `tools/shared/base_models.py` (`WORKFLOW_FIELD_DESCRIPTIONS["relevant_files"]`)
- Modify: `docs/plans/BACKLOG.md` (mark phase 1 done)

**Step 1: Live integration test through zen's own provider**

```python
"""Live media probes through zen's providers. Costs a few cents. Run with -m integration."""

import os
from pathlib import Path

import pytest

from providers.gemini import GeminiModelProvider
from tests.media_probe_matrix import PROBED
from utils.media import classify_media

FIXTURES = Path(__file__).parent / "fixtures" / "media"
CASES = {
    "pdf": ("zebra.pdf", "What code is written in this PDF? Reply with only the code.", ("ZEBRA-42",)),
    "audio": ("pelican.wav", "What code word and number are spoken? Reply with only them.", ("PELICAN",)),
    "video": ("otter.mp4", "What text is shown in this video? Reply with only that text.", ("OTTER-9",)),
}
GEMINI = [(model, kind) for (provider, model), kinds in PROBED.items() if provider == "google" for kind in sorted(kinds)]


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
```

Run: `set -a; source /Users/wrk/WorkDev/MCP-Dev/zen-cli/.env; set +a; .zen_venv/bin/python -m pytest tests/test_media_live.py -m integration -q -p no:cacheprovider`
Expected: every (model, kind) passes. A failure here after Task 5's raw-SDK probe passed means zen's encoder is wrong, not the model.

**Step 2: CLI smoke test**

```bash
set -a; source /Users/wrk/WorkDev/MCP-Dev/zen-cli/.env; set +a
.zen_venv/bin/zen chat "What text is shown in this video?" -f tests/fixtures/media/otter.mp4 --model flash --json
.zen_venv/bin/zen chat "What code is written here?" -f tests/fixtures/media/zebra.pdf --json          # auto mode
.zen_venv/bin/zen chat "What is shown?" -f tests/fixtures/media/otter.mp4 --model grok-4.7 --json      # must fail fast
```

Expected: first two answer with the marker (auto mode resolves to a Gemini model); the third returns an error naming Gemini models, with no API call made (check `logs/mcp_activity.log`).

**Step 3: Field descriptions**

Append to the chat `absolute_file_paths` and workflow `relevant_files` descriptions:
`" PDF, audio (wav/mp3/m4a/aac/ogg/flac) and video (mp4/mov/webm/mpeg) files are sent to the model as native media when it supports them; the request fails with a list of capable models otherwise."`
If a schema snapshot test compares these strings, update it in the same commit.

**Step 4: Backlog**

In `docs/plans/BACKLOG.md` under "Media input", set status to "Phase 1 (core + Gemini) implemented on `feat/media-input`; phases 2–5 pending".

**Step 5: Full verification**

```bash
.zen_venv/bin/ruff check . && .zen_venv/bin/black --check . && .zen_venv/bin/isort --check-only .
.zen_venv/bin/python -m pytest tests/ -q -m "not integration" -p no:cacheprovider
```

Expected: lint clean; all new tests pass; only the 3 pre-existing `test_alias_target_restrictions` failures remain.

**Step 6: Commit**

```bash
git add tests/test_media_live.py tools/chat.py tools/shared/base_models.py docs/plans/BACKLOG.md
git commit -m "test(media): live Gemini probes through zen; document media in file fields"
```

---

## Done when

- `zen chat -f video.mp4` answers from the video on Gemini, in both auto mode and with `--model flash`.
- Any non-Gemini model given media fails before an API call, naming capable models.
- No media or binary file is ever embedded as UTF-8 text.
- Every media flag in a catalog is backed by `tests/media_probe_matrix.py`, and the live suite passes for all of them.
- Unit suite: baseline + new tests, only the 3 pre-existing failures.
