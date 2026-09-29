"""Native media attachments (PDF, audio, video) for model requests.

Media files are never read as text. They are detected from explicit file paths by
extension *and* magic bytes, carried alongside the prompt, and encoded by providers
that declare support for them (``ModelProvider.MEDIA_KINDS``).
"""

from __future__ import annotations

import functools
import math
import os
import re
import zlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import Enum
from itertools import islice
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

# Argument keys that carry file paths: simple tools read absolute_file_paths, workflow tools
# relevant_files, and the CLI sends the same two keys. No request model reads a "files" field.
FILE_ARGUMENT_KEYS = ("absolute_file_paths", "relevant_files")

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


def _validated_path(path: str) -> Path | None:
    """``path`` resolved and checked like a text file (absolute, not a dangerous directory), else None."""
    from .file_utils import resolve_and_validate_path  # file_utils imports this module

    try:
        return resolve_and_validate_path(path)
    except (ValueError, PermissionError, RuntimeError, OSError):  # RuntimeError: symlink loop
        return None


def _detect_media(path: str, resolved: Path) -> tuple[MediaKind, str, int] | None:
    """(kind, mime, size in bytes) if the validated file ``resolved`` is correctly signed media.

    A media extension on either the caller's ``path`` or the resolved target counts. The file is
    only opened and measured through ``resolved``; ``path`` is never re-followed.
    """
    candidates = [s for s in dict.fromkeys((Path(path).suffix.lower(), resolved.suffix.lower())) if s in MEDIA_TYPES]
    if not candidates:
        return None
    try:
        # is_file() keeps a FIFO or device named like media from being opened: reading one would
        # block or never end. Directories need no check here: opening one raises OSError below.
        if not resolved.is_file():
            return None
        for extension in candidates:
            with resolved.open("rb") as handle:
                if _magic_matches(extension, _read_signature(handle, extension)):
                    kind, mime = MEDIA_TYPES[extension]
                    return kind, mime, resolved.stat().st_size
    except OSError:  # includes a file that disappears after validation
        return None
    return None


def media_type_for(path: str) -> tuple[MediaKind, str] | None:
    """Return (kind, mime) if ``path`` is an existing, correctly signed media file.

    The path must pass the same security validation as text files (absolute, not under a
    dangerous system directory). A media extension on either the given path or its symlink
    target counts, so ``latest -> recording.mp4`` and ``clip.mp4 -> blob`` are both media;
    the magic bytes must match that extension either way.
    """
    resolved = _validated_path(path)
    if resolved is None:
        return None
    detected = _detect_media(path, resolved)
    if detected is None:
        return None
    kind, mime, _ = detected
    return kind, mime


def format_size(num_bytes: int) -> str:
    """'7.9 KB' below 1 MB, '12.3 MB' below 1 GB, else '2.1 GB'.

    Decimal units (1 KB = 1000 bytes), like MEDIA_MAX_BYTES, so the 2 GB limit reads "2.0 GB".
    """
    for unit, scale in (("KB", 10**3), ("MB", 10**6)):
        if round(num_bytes / scale, 1) < 1000:
            return f"{num_bytes / scale:.1f} {unit}"
    return f"{num_bytes / 10**9:.1f} GB"


@dataclass(frozen=True)
class MediaAttachment:
    """A media file to send with the prompt.

    ``path`` is the caller's string, kept for display and comparisons. ``source_path`` is the
    resolved, security-validated file: read the bytes from it, never from ``path``, so symlinks
    are not followed again after validation.
    """

    path: str
    kind: MediaKind
    mime_type: str
    size_bytes: int
    source_path: str

    @property
    def name(self) -> str:
        return Path(self.path).name

    def describe(self) -> str:
        return f"{self.kind.value} {self.name}, {format_size(self.size_bytes)}"


def classify_media(paths: Iterable[str] | None) -> tuple[list[str], list[MediaAttachment]]:
    """Split explicit paths into (text_paths, media_attachments), preserving order.

    Media is deduped on the resolved file: the first caller path for a file is kept, and later
    spellings of it (``dir/./x.mp4``, a symlink, a trailing slash) are dropped without re-reading it.
    """
    if isinstance(paths, str):
        raise TypeError("classify_media expects a list of paths, not a single path string")
    text_paths: list[str] = []
    media: list[MediaAttachment] = []
    seen: set[Path] = set()
    for path in paths or []:
        resolved = _validated_path(path)
        if resolved is None:
            text_paths.append(path)
            continue
        if resolved in seen:
            continue
        detected = _detect_media(path, resolved)
        if detected is None:
            text_paths.append(path)
            continue
        seen.add(resolved)
        kind, mime, size = detected
        media.append(MediaAttachment(path=path, kind=kind, mime_type=mime, size_bytes=size, source_path=str(resolved)))
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


# ---------------------------------------------------------------------------
# Size limit, token estimate and prompt announcement
# ---------------------------------------------------------------------------

# Largest single media file zen sends: the Gemini Files API per-file limit, "2 GB". Counted in decimal
# bytes, so the check is conservative whichever unit the API means.
MEDIA_MAX_BYTES = 2_000_000_000

# Input-token planning figures from the Gemini media docs (video and audio checked 2026-09-27): a
# video frame is 258 tokens at 1 frame/s (66 at low media resolution) plus 32 tokens/s of audio, so
# 300/s covers the high-resolution case; audio is 32 tokens/s. A PDF page is 560 tokens for Gemini 3
# models at the default media resolution
# (https://ai.google.dev/gemini-api/docs/media-resolution, checked 2026-09-28).
# tests/test_media_live.py checks all three against real usage.
VIDEO_TOKENS_PER_SECOND = 300
AUDIO_TOKENS_PER_SECOND = 32
PDF_TOKENS_PER_PAGE = 560
# Used when the duration or page count is not cheaply readable: a low bitrate / small page, so the
# estimate errs high and text files get less room, never more.
FALLBACK_BYTES_PER_SECOND = {MediaKind.VIDEO: 64_000, MediaKind.AUDIO: 8_000}
FALLBACK_BYTES_PER_PDF_PAGE = 4_000

# PDF page counting: Gemini reads at most 1000 pages of a PDF. Only files up to PDF_SCAN_MAX_BYTES are
# read, and compressed object streams are inflated to at most PDF_INFLATE_MAX_BYTES in total, from at
# most PDF_MAX_OBJECT_STREAMS candidates.
PDF_MAX_PAGES = 1000
PDF_SCAN_MAX_BYTES = 64 * 1024 * 1024
PDF_INFLATE_MAX_BYTES = 64 * 1024 * 1024
PDF_MAX_OBJECT_STREAMS = 4096
# Object streams are inflated a piece at a time (input slice, output piece), so memory stays near the
# output piece size whatever a stream expands to. The last _PDF_MATCH_CARRY bytes of each output piece
# are searched again with the next one, so a page object split between pieces is still found.
_PDF_INFLATE_INPUT_BYTES = 64 * 1024
_PDF_INFLATE_OUTPUT_BYTES = 1024 * 1024
_PDF_MATCH_CARRY = 64
_PDF_PAGE_OBJECT = re.compile(rb"/Type\s*/Page(?![A-Za-z0-9_])")  # not /Pages, /Page1, /Page_x
_PDF_OBJECT_STREAM = re.compile(rb"/Type\s*/ObjStm(?![A-Za-z])")
_PDF_STREAM_DATA = re.compile(rb"(?<!end)stream(?:\r\n|\n|\r)")
_PDF_DICT_MAX_BYTES = 4096  # how far past '/Type /ObjStm' its 'stream' keyword may be


def check_media_sizes(media: Iterable[MediaAttachment]) -> None:
    """Fail fast, naming each file by the caller's path, if any attachment is larger than MEDIA_MAX_BYTES."""
    too_large = [attachment for attachment in media if attachment.size_bytes > MEDIA_MAX_BYTES]
    if too_large:
        names = ", ".join(f"{a.path} ({format_size(a.size_bytes)}, {a.size_bytes:,} bytes)" for a in too_large)
        raise MediaNotSupportedError(
            f"Media files are limited to {format_size(MEDIA_MAX_BYTES)} each "
            f"(Gemini Files API per-file limit; {MEDIA_MAX_BYTES:,} bytes): {names}."
        )


def _inflated_pages(stream: memoryview, budget: int, max_pages: int) -> tuple[int, int, bool]:
    """(page objects, bytes inflated, finished) for one FlateDecode stream, inflated in pieces.

    ``finished`` is False when the budget or the data ran out before the end of the zlib stream.
    Raises zlib.error for data that is not a zlib stream.
    """
    inflater = zlib.decompressobj()
    pages, inflated, carry = 0, 0, b""
    for offset in range(0, len(stream), _PDF_INFLATE_INPUT_BYTES):
        pending = stream[offset : offset + _PDF_INFLATE_INPUT_BYTES]
        while not inflater.eof and pages < max_pages:
            room = min(budget - inflated, _PDF_INFLATE_OUTPUT_BYTES)
            if room <= 0:
                return pages, inflated, False
            output = inflater.decompress(pending, room)
            pending = inflater.unconsumed_tail
            if not output:  # this input slice is used up
                break
            inflated += len(output)
            window = carry + output
            del output  # hold one inflated piece at a time
            searched = max(0, len(window) - _PDF_MATCH_CARRY)  # matches starting later are re-searched
            pages += sum(1 for match in _PDF_PAGE_OBJECT.finditer(window) if match.start() < searched)
            carry = window[searched:]
            del window
        if inflater.eof or pages >= max_pages:
            break
    pages += sum(1 for _ in _PDF_PAGE_OBJECT.finditer(carry))
    return min(pages, max_pages), inflated, inflater.eof or pages >= max_pages


def _pdf_object_stream_pages(data: bytes, max_pages: int) -> tuple[int, bool]:
    """(page objects inside FlateDecode object streams, whether every object stream was read).

    Not every stream is read when one does not inflate (encrypted, another filter, damaged), uses a
    predictor (its inflated bytes are not objects), has no end, or a limit stops the walk.
    """
    view, pages, budget, consumed_to, complete = memoryview(data), 0, PDF_INFLATE_MAX_BYTES, 0, True
    for candidate, marker in enumerate(_PDF_OBJECT_STREAM.finditer(data)):
        if pages >= max_pages:
            break
        if candidate >= PDF_MAX_OBJECT_STREAMS or budget <= 0:
            return pages, False
        if marker.start() < consumed_to:  # inside a stream already read
            continue
        start = _PDF_STREAM_DATA.search(data, marker.end(), marker.end() + _PDF_DICT_MAX_BYTES)
        if start is None:  # not a stream dictionary
            continue
        end = data.find(b"endstream", start.end())
        if end < 0:
            return pages, False
        consumed_to = end
        lookback = max(0, marker.start() - _PDF_DICT_MAX_BYTES)
        dictionary = data.rfind(b"obj", lookback, marker.start())
        if data.find(b"/DecodeParms", dictionary if dictionary >= 0 else lookback, start.start()) >= 0:
            complete = False
            continue
        try:
            found, used, finished = _inflated_pages(view[start.end() : end], budget, max_pages - pages)
        except zlib.error:
            complete = False
            continue
        pages, budget, complete = pages + found, budget - used, complete and finished
    return pages, complete


def _pdf_pages_by_size(size_bytes: int) -> int:
    return min(max(1, math.ceil(size_bytes / FALLBACK_BYTES_PER_PDF_PAGE)), PDF_MAX_PAGES)


@functools.lru_cache(maxsize=256)
def _pdf_page_count(source_path: str, size_bytes: int, mtime_ns: int) -> int:
    """Pages in the PDF at ``source_path``, counted from its page objects (plain and inside object
    streams) and capped at PDF_MAX_PAGES.

    Cached on (path, size, modification time), so the several estimates made for one request read the
    file once. Size-based when the file is too large to scan or no page object is found, and never
    below the size-based count when an object stream could not be read, so the estimate errs high.
    """
    by_size = _pdf_pages_by_size(size_bytes)
    if size_bytes > PDF_SCAN_MAX_BYTES:
        return by_size
    try:
        with open(source_path, "rb") as handle:
            # read(n) allocates n bytes up front: ask for the file's size, not the scan limit.
            data = handle.read(size_bytes + 1)
    except OSError:
        return by_size
    if len(data) > PDF_SCAN_MAX_BYTES:
        return by_size
    pages = sum(1 for _ in islice(_PDF_PAGE_OBJECT.finditer(data), PDF_MAX_PAGES))
    complete = True
    if pages < PDF_MAX_PAGES:
        found, complete = _pdf_object_stream_pages(data, PDF_MAX_PAGES - pages)
        pages += found
    if not pages or not complete:
        pages = max(pages, by_size)
    return min(pages, PDF_MAX_PAGES)


def _pdf_pages(attachment: MediaAttachment) -> int:
    """Pages in a PDF attachment (see _pdf_page_count)."""
    try:
        mtime_ns = os.stat(attachment.source_path).st_mtime_ns
    except OSError:
        return _pdf_pages_by_size(attachment.size_bytes)
    return _pdf_page_count(attachment.source_path, attachment.size_bytes, mtime_ns)


# Header walks stop after this many chunks or boxes at one level, so a crafted file cannot make the
# estimate step through millions of tiny entries; the size-based fallback applies instead.
MAX_CONTAINER_ENTRIES = 1024


def _wav_duration_s(handle: BinaryIO, file_size: int) -> float | None:
    """Duration from a RIFF/WAVE header: data size / byte rate. Declared chunk sizes are not trusted."""
    if handle.read(12)[8:12] != b"WAVE":
        return None
    byte_rate = 0
    for _ in range(MAX_CONTAINER_ENTRIES):
        chunk = handle.read(8)
        if len(chunk) < 8:
            return None
        chunk_id, chunk_size = chunk[:4], int.from_bytes(chunk[4:8], "little")
        body_size = chunk_size + (chunk_size & 1)  # RIFF chunks are word-aligned
        if chunk_id == b"fmt ":
            fmt = handle.read(min(body_size, 16))  # the byte rate is at offset 8; never read a huge size
            byte_rate = int.from_bytes(fmt[8:12], "little") if len(fmt) >= 12 else 0
            handle.seek(body_size - len(fmt), 1)
        elif chunk_id == b"data":
            # Streaming writers leave 0 or a placeholder past the end of the file (0xFFFFFFFF,
            # 0x7FFFFFFF) when they never patch the header: the audio then runs to the end of the file.
            remaining = max(0, file_size - handle.tell())
            if chunk_size == 0 or chunk_size > remaining:
                chunk_size = remaining
            return chunk_size / byte_rate if byte_rate and chunk_size else None
        else:
            handle.seek(body_size, 1)
    return None


def _bmff_boxes(handle: BinaryIO, start: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    """(type, body start, body end) of up to MAX_CONTAINER_ENTRIES boxes in ``[start, end)``.

    Each box is clamped to its parent, so a declared size past the end of the file (up to 2**64 - 1)
    never moves a seek outside it. Stops at a box too small for its own header.
    """
    offset = start
    for _ in range(MAX_CONTAINER_ENTRIES):
        if offset + 8 > end:
            return
        handle.seek(offset)
        header = handle.read(16)
        if len(header) < 8:
            return
        size, header_size = int.from_bytes(header[:4], "big"), 8
        if size == 1:  # 64-bit box size follows the type
            if len(header) < 16:
                return
            size, header_size = int.from_bytes(header[8:16], "big"), 16
        elif size == 0:  # box runs to the end of its parent
            size = end - offset
        if size < header_size or offset + header_size > end:
            return
        box_end = min(offset + size, end)
        yield header[4:8], offset + header_size, box_end
        offset = box_end


def _known_duration(field: bytes) -> int | None:
    """A duration field's value, or None when it is 0 or all ones (both mean unknown)."""
    value = int.from_bytes(field, "big")
    return None if value == 0 or value == (1 << (8 * len(field))) - 1 else value


def _mvhd_timing(handle: BinaryIO, start: int, end: int) -> tuple[int, int | None]:
    """(timescale, duration) from a movie header body; (0, None) if the body is too short."""
    handle.seek(start)
    body = handle.read(min(end - start, 32))
    if body[:1] == b"\x01":  # version 1: 64-bit creation/modification times and duration
        if len(body) < 32:
            return 0, None
        return int.from_bytes(body[20:24], "big"), _known_duration(body[24:32])
    if len(body) < 20:
        return 0, None
    return int.from_bytes(body[12:16], "big"), _known_duration(body[16:20])


def _mehd_duration(handle: BinaryIO, start: int, end: int) -> int | None:
    """fragment_duration from a movie extends header body (in the mvhd timescale), or None."""
    handle.seek(start)
    body = handle.read(min(end - start, 12))
    width = 8 if body[:1] == b"\x01" else 4
    return _known_duration(body[4 : 4 + width]) if len(body) >= 4 + width else None


def _bmff_duration_s(handle: BinaryIO, file_size: int) -> float | None:
    """Duration from the movie header ('moov' -> 'mvhd') of an MP4/MOV/M4A file, wherever moov sits.

    In a fragmented file (moov holds an 'mvex' box) mvhd may cover only the first fragment, so the
    'mehd' fragment duration is used instead, and without one the duration is unknown.
    """
    for box, start, end in _bmff_boxes(handle, 0, file_size):
        if box != b"moov":
            continue
        timescale, duration, fragmented, fragment_duration = 0, None, False, None
        for child, child_start, child_end in _bmff_boxes(handle, start, end):
            if child == b"mvhd":
                timescale, duration = _mvhd_timing(handle, child_start, child_end)
            elif child == b"mvex" and not fragmented:  # ISO 14496-12: at most one per moov
                fragmented = True
                for grandchild, mehd_start, mehd_end in _bmff_boxes(handle, child_start, child_end):
                    if grandchild == b"mehd":
                        fragment_duration = _mehd_duration(handle, mehd_start, mehd_end)
        if fragmented:
            duration = fragment_duration
        return duration / timescale if timescale and duration else None
    return None


def _duration_s(attachment: MediaAttachment) -> float | None:
    """Exact duration where the container header makes it cheap (WAV, MP4/MOV/M4A), else None."""
    try:
        with open(attachment.source_path, "rb") as handle:
            if attachment.mime_type == "audio/wav":
                return _wav_duration_s(handle, attachment.size_bytes)
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
            total += PDF_TOKENS_PER_PAGE * _pdf_pages(attachment)
            continue
        seconds = _duration_s(attachment)
        if seconds is None:
            seconds = attachment.size_bytes / FALLBACK_BYTES_PER_SECOND[attachment.kind]
        rate = VIDEO_TOKENS_PER_SECOND if attachment.kind is MediaKind.VIDEO else AUDIO_TOKENS_PER_SECOND
        total += rate * max(1, math.ceil(seconds))
    return total


def media_prompt_section(media: Iterable[MediaAttachment]) -> str:
    """Prompt text announcing attachments, built from the attachment list so the two cannot disagree.

    Media parts carry no file name, so each entry says its position; providers attach the media
    parts in this same order.
    """
    attachments = list(media)
    return "".join(
        f"\n--- MEDIA FILE: {a.path} ({a.kind.value}, {a.mime_type}, {format_size(a.size_bytes)}) ---\n"
        f"Not embedded as text: attached to this request as native {a.kind.value} input "
        f"(attachment {number} of {len(attachments)}; the media parts follow in this order).\n"
        "--- END FILE ---\n"
        for number, a in enumerate(attachments, 1)
    )
