"""Tests for the media size limit, token estimate and prompt announcement in utils.media."""

import math
import os
import time
import tracemalloc
import zlib
from pathlib import Path

import pytest

import utils.media
from utils.media import (
    MEDIA_MAX_BYTES,
    MediaNotSupportedError,
    check_media_sizes,
    classify_media,
    estimate_media_tokens,
    format_size,
    media_prompt_section,
)

FIXTURES = Path(__file__).parent / "fixtures" / "media"
PDF = str(FIXTURES / "zebra.pdf")
WAV = str(FIXTURES / "pelican.wav")
MP4 = str(FIXTURES / "otter.mp4")


@pytest.fixture(autouse=True)
def _fresh_pdf_page_cache():
    """Each test counts PDF pages afresh (shared fixtures and patched limits must not see old counts)."""
    utils.media._pdf_page_count.cache_clear()
    yield
    utils.media._pdf_page_count.cache_clear()


def _box(box_type: bytes, payload: bytes) -> bytes:
    return (8 + len(payload)).to_bytes(4, "big") + box_type + payload


def _big_box(box_type: bytes, size: int, payload: bytes = b"") -> bytes:
    """A box with a 64-bit size field (size 1 followed by the largesize)."""
    return (1).to_bytes(4, "big") + box_type + size.to_bytes(8, "big") + payload


FTYP = _box(b"ftyp", b"isom\x00\x00\x02\x00isom")


def _mvhd(timescale: int, duration: int, version: int = 0) -> bytes:
    if version == 1:  # 64-bit creation/modification times and duration
        fields = b"\x00" * 16 + timescale.to_bytes(4, "big") + duration.to_bytes(8, "big")
    else:
        fields = b"\x00" * 8 + timescale.to_bytes(4, "big") + duration.to_bytes(4, "big")
    return _box(b"mvhd", bytes([version]) + b"\x00" * 3 + fields + b"\x00" * 80)


def _write(path: Path, head: bytes, size: int | None = None) -> str:
    """Write ``head``; with ``size``, extend the file to that many bytes as a sparse hole."""
    with path.open("wb") as handle:
        handle.write(head)
        if size is not None:
            handle.truncate(size)
    return str(path)


def _sparse_mp4(path: Path, size: int) -> Path:
    """An 'ftyp' header followed by a hole: passes the signature check without writing real data."""
    _write(path, FTYP, size)
    return path


def _estimate(path: str) -> int:
    media = classify_media([path])[1]
    assert len(media) == 1, f"not classified as media: {path}"
    return estimate_media_tokens(media)


def _video_by_size(path: str) -> int:
    """The size-based video estimate: 400 tokens/s at an assumed 64 kB/s."""
    return 400 * max(1, math.ceil(os.path.getsize(path) / 64_000))


def _audio_by_size(path: str) -> int:
    """The size-based audio estimate: 32 tokens/s at an assumed 8 kB/s."""
    return 32 * max(1, math.ceil(os.path.getsize(path) / 8_000))


def _pdf_by_size(path: str) -> int:
    """The size-based PDF estimate: 560 tokens per assumed 4,000-byte page, at most 1000 pages."""
    return 560 * min(1000, max(1, math.ceil(os.path.getsize(path) / 4_000)))


def _estimate_traced(path: str) -> tuple[int, int]:
    """(tokens, peak bytes allocated while estimating) for one media file."""
    media = classify_media([path])[1]
    assert len(media) == 1, f"not classified as media: {path}"
    tracemalloc.start()
    try:
        tokens = estimate_media_tokens(media)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    return tokens, peak


# PCM mono, 16 kHz, 16-bit: 32,000 bytes per second.
WAV_FMT = (
    (1).to_bytes(2, "little")  # PCM
    + (1).to_bytes(2, "little")  # mono
    + (16_000).to_bytes(4, "little")  # sample rate
    + (32_000).to_bytes(4, "little")  # byte rate
    + (2).to_bytes(2, "little")  # block align
    + (16).to_bytes(2, "little")  # bits per sample
)


def _wav_header(data_size: int, fmt: bytes = WAV_FMT, fmt_size: int | None = None) -> bytes:
    fmt_size = len(fmt) if fmt_size is None else fmt_size
    return (
        b"RIFF"
        + (0).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + fmt_size.to_bytes(4, "little")
        + fmt
        + b"data"
        + data_size.to_bytes(4, "little")
    )


def _pdf(pages: int, compressed_pages: int = 0) -> bytes:
    """A valid PDF 1.5 with ``pages`` blank pages, indexed by a cross-reference stream.

    The last ``compressed_pages`` page objects are stored only inside a FlateDecode object stream,
    so their '/Type /Page' never appears in the file's raw bytes.
    """
    page_numbers = list(range(3, 3 + pages))
    kids = b" ".join(b"%d 0 R" % number for number in page_numbers)
    page = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << >> >>"
    plain = {1: b"<< /Type /Catalog /Pages 2 0 R >>", 2: b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, pages)}
    compressed = page_numbers[pages - compressed_pages :]
    plain.update(dict.fromkeys(page_numbers[: pages - compressed_pages], page))
    out, offsets, next_number = b"%PDF-1.5\n", {}, 3 + pages
    for number, body in plain.items():
        offsets[number] = len(out)
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    if compressed:
        stream_number, next_number = next_number, next_number + 1
        index = b" ".join(b"%d %d" % (number, i * (len(page) + 1)) for i, number in enumerate(compressed)) + b"\n"
        data = zlib.compress(index + b"".join(page + b"\n" for _ in compressed))
        offsets[stream_number] = len(out)
        out += (
            b"%d 0 obj\n<< /Type /ObjStm /N %d /First %d /Filter /FlateDecode /Length %d >>\nstream\n"
            % (stream_number, len(compressed), len(index), len(data))
            + data
            + b"\nendstream\nendobj\n"
        )
    xref_number = next_number
    offsets[xref_number] = len(out)
    rows = [b"\x00\x00\x00\x00\x00\xff\xff"]
    for number in range(1, xref_number + 1):
        if number in offsets:
            rows.append(b"\x01" + offsets[number].to_bytes(4, "big") + b"\x00\x00")
        else:
            rows.append(b"\x02" + stream_number.to_bytes(4, "big") + compressed.index(number).to_bytes(2, "big"))
    xref = b"".join(rows)
    out += (
        b"%d 0 obj\n<< /Type /XRef /Size %d /W [1 4 2] /Root 1 0 R /Length %d >>\nstream\n"
        % (xref_number, xref_number + 1, len(xref))
        + xref
        + b"\nendstream\nendobj\n"
    )
    return out + b"startxref\n%d\n%%%%EOF\n" % offsets[xref_number]


def test_check_media_sizes_accepts_fixtures():
    check_media_sizes(classify_media([PDF, WAV, MP4])[1])


def test_check_media_sizes_rejects_oversized_file(tmp_path):
    huge = _sparse_mp4(tmp_path / "huge.mp4", MEDIA_MAX_BYTES + 1)
    media = classify_media([str(huge)])[1]
    with pytest.raises(MediaNotSupportedError) as exc:
        check_media_sizes(media)
    message = str(exc.value)
    assert f"{huge} (2.0 GB, 2,000,000,001 bytes)" in message  # the caller's full path, exact size
    assert "limited to 2.0 GB each (Gemini Files API per-file limit; 2,000,000,000 bytes)" in message


def test_file_exactly_at_the_limit_is_accepted(tmp_path):
    assert MEDIA_MAX_BYTES == 2_000_000_000  # decimal 2 GB: conservative whichever unit the API means
    check_media_sizes(classify_media([str(_sparse_mp4(tmp_path / "limit.mp4", MEDIA_MAX_BYTES))])[1])


def test_size_error_lists_every_oversized_file(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = _sparse_mp4(tmp_path / "a" / "clip.mp4", MEDIA_MAX_BYTES + 1)
    second = _sparse_mp4(tmp_path / "b" / "clip.mp4", 3 * 10**9)
    with pytest.raises(MediaNotSupportedError) as exc:
        check_media_sizes(classify_media([str(first), MP4, str(second)])[1])
    message = str(exc.value)
    assert f": {first} (2.0 GB, 2,000,000,001 bytes), {second} (3.0 GB, 3,000,000,000 bytes)." in message
    assert "otter.mp4" not in message


def test_estimate_reads_exact_durations():
    _, (pdf, wav, mp4) = classify_media([PDF, WAV, MP4])
    assert estimate_media_tokens([mp4]) == 3 * 400  # mvhd: 3 s, stored after mdat
    assert estimate_media_tokens([wav]) == 2 * 32  # 1.96 s of 16 kHz mono, rounded up
    assert estimate_media_tokens([pdf]) == 560  # one page
    assert estimate_media_tokens([pdf, wav, mp4]) == 560 + 64 + 1200
    assert estimate_media_tokens([]) == 0


def test_estimate_reads_version_1_movie_header(tmp_path):
    mvhd = _box(b"mvhd", b"\x01\x00\x00\x00" + b"\x00" * 16 + (1000).to_bytes(4, "big") + (90_000).to_bytes(8, "big"))
    clip = tmp_path / "long.mov"
    clip.write_bytes(_box(b"ftyp", b"qt  \x00\x00\x02\x00qt  ") + _box(b"mdat", b"\x00" * 64) + _box(b"moov", mvhd))
    assert estimate_media_tokens(classify_media([str(clip)])[1]) == 90 * 400


def test_estimate_falls_back_to_size_without_a_header(tmp_path):
    clip = _sparse_mp4(tmp_path / "raw.mp4", 2 * 1024 * 1024)  # no moov box
    assert estimate_media_tokens(classify_media([str(clip)])[1]) == 400 * 33  # 2 MiB at 64 kB/s = 32.8 s


def test_estimate_treats_zero_movie_duration_as_unknown(tmp_path):
    # Fragmented MP4s often leave the mvhd duration at 0; the real length lives in the fragments.
    clip = _write(
        tmp_path / "fragmented.mp4",
        _box(b"ftyp", b"iso5\x00\x00\x02\x00iso5") + _box(b"moov", _mvhd(1000, 0)),
        10 * 1024 * 1024,
    )
    assert _estimate(clip) == 400 * 164  # 10 MiB at 64 kB/s = 163.8 s


# --- PDF pages: counted from page objects, size-based only when they cannot be ---------------------


@pytest.mark.parametrize("pages", [1, 3, 12])
def test_pdf_pages_are_counted(tmp_path, pages):
    assert _estimate(_write(tmp_path / "doc.pdf", _pdf(pages))) == 560 * pages


def test_pdf_pages_inside_an_object_stream_are_counted(tmp_path):
    assert _estimate(_write(tmp_path / "packed.pdf", _pdf(5, compressed_pages=5))) == 560 * 5


def test_pdf_pages_both_plain_and_in_an_object_stream_are_counted(tmp_path):
    # one page stored as a plain object and three inside an object stream, all from one save
    assert _estimate(_write(tmp_path / "mixed.pdf", _pdf(4, compressed_pages=3))) == 560 * 4


def test_pdf_page_count_is_capped_at_gemini_limit(tmp_path):
    assert _estimate(_write(tmp_path / "long.pdf", _pdf(1200))) == 560 * 1000


def test_pdf_without_page_objects_falls_back_to_size(tmp_path):
    doc = _write(tmp_path / "odd.pdf", b"%PDF-1.7\n" + b"x" * (40_000 - 9))
    assert _estimate(doc) == 560 * 10  # 40,000 B at 4,000 B/page


def test_pdf_over_the_scan_limit_is_not_read(tmp_path):
    # Three real page objects, then a hole past 64 MiB: estimated by size (capped), not by scanning.
    doc = _write(tmp_path / "huge.pdf", _pdf(3), 64 * 1024 * 1024 + 1)
    assert _estimate(doc) == 560 * 1000


def test_pdf_scan_reads_only_the_file(tmp_path):
    # A small PDF must not cost a buffer the size of the 64 MiB scan limit.
    tokens, peak = _estimate_traced(_write(tmp_path / "zebra.pdf", Path(PDF).read_bytes()))
    assert tokens == 560
    assert peak < 1024 * 1024


def test_pdf_page_object_spellings(tmp_path):
    body = (
        b"<</Type/Page>> <</Type /Page/Parent 1 0 R>> << /Type\n/Page >> "  # three pages
        b"<</Type /Page1>> <</Type /Page_x>> <</Type /PageLabel>> <</Type /Pages>>"  # none
    )
    assert _estimate(_write(tmp_path / "forms.pdf", b"%PDF-1.4\n" + body + b"\n%%EOF\n")) == 560 * 3


PLAIN_PAGE = b"1 0 obj\n<< /Type /Page /Parent 3 0 R >>\nendobj\n"
PADDING = b"%" + b"x" * 40_000 + b"\n"  # a comment, so the size-based estimate is ~11 pages


def test_pdf_with_an_undecodable_object_stream_errs_high(tmp_path):
    # One plain page plus an object stream that is not zlib data (as when the PDF is encrypted): the
    # pages it may hold cannot be counted, so the size-based estimate is the floor.
    stream = b"2 0 obj\n<< /Type /ObjStm /N 300 /First 10 /Filter /FlateDecode >>\nstream\n"
    doc = _write(
        tmp_path / "enc.pdf", b"%PDF-1.5\n" + PLAIN_PAGE + stream + b"\xff" * 40_000 + b"\nendstream\nendobj\n"
    )
    assert _estimate(doc) == _pdf_by_size(doc) == 560 * 11


def test_pdf_object_stream_with_a_predictor_errs_high(tmp_path):
    # A predictor-filtered object stream inflates, but its bytes are not readable as objects.
    data = zlib.compress(b"4 0\n<< /Type /Font >>")
    stream = (
        b"2 0 obj\n<< /Type /ObjStm /N 1 /First 4 /Filter /FlateDecode /DecodeParms << /Predictor 12 >> >>\nstream\n"
    )
    doc = _write(tmp_path / "pred.pdf", b"%PDF-1.5\n" + PLAIN_PAGE + stream + data + b"\nendstream\nendobj\n" + PADDING)
    assert _estimate(doc) == _pdf_by_size(doc)


@pytest.mark.parametrize("limit,value", [("PDF_INFLATE_MAX_BYTES", 10), ("PDF_MAX_OBJECT_STREAMS", 0)])
def test_pdf_object_stream_limits_err_high(tmp_path, monkeypatch, limit, value):
    # One plain page and five in an object stream, padded to ~41 KB. When a limit stops the walk,
    # the pages it did not count are covered by the size-based estimate.
    content = _pdf(6, compressed_pages=5) + PADDING
    assert _estimate(_write(tmp_path / "counted.pdf", content)) == 560 * 6
    monkeypatch.setattr(utils.media, limit, value)
    limited = _write(tmp_path / "limited.pdf", content)
    assert _estimate(limited) == _pdf_by_size(limited) == 560 * 11


def test_pdf_markers_inside_an_inflated_stream_are_skipped(tmp_path):
    # A stored (level 0) deflate stream shows its contents verbatim in the file: here a dictionary
    # that looks like another object stream. It must not be inflated again (that would fail and make
    # the estimate fall back to the file size).
    data = zlib.compress(b"4 0\n<< /Type /Font >>\n<< /Type /ObjStm >>\nstream\n" + b"y" * 200, 0)
    stream = b"2 0 obj\n<< /Type /ObjStm /N 1 /First 4 /Filter /FlateDecode >>\nstream\n"
    doc = _write(
        tmp_path / "stored.pdf", b"%PDF-1.5\n" + PLAIN_PAGE + stream + data + b"\nendstream\nendobj\n" + PADDING
    )
    assert _estimate(doc) == 560


def test_pdf_inflation_is_streamed(tmp_path):
    # A zlib bomb (32 MiB of zeros) followed by 8 MiB of incompressible bytes in one object stream:
    # inflating costs the file itself plus a few MiB, never the inflated size.
    bomb = zlib.compressobj(9)
    compressed = b"".join(bomb.compress(bytes(1 << 20)) for _ in range(32)) + bomb.flush()
    head = b"%PDF-1.5\n1 0 obj\n<< /Type /ObjStm /N 1 /First 4 /Filter /FlateDecode >>\nstream\n"
    doc = _write(tmp_path / "bomb.pdf", head + compressed + os.urandom(8 << 20) + b"\nendstream\nendobj\n")
    tokens, peak = _estimate_traced(doc)
    assert peak < os.path.getsize(doc) + 4 * 1024 * 1024
    assert tokens == _pdf_by_size(doc)


@pytest.mark.parametrize("input_bytes,output_bytes", [(5, 7), (64, 3), (64 * 1024, 1024 * 1024)])
def test_pdf_page_objects_split_between_inflated_pieces_count_once(tmp_path, monkeypatch, input_bytes, output_bytes):
    # With tiny pieces every page object straddles a boundary; the count must match a whole-stream search.
    content = (
        b"4 0\n<< /Type /Pages /Kids [] >>\n"
        + b"<< /Type /Page >>\n" * 30
        + b"<< /Type /Page1 >>\n<< /Type\n/Page /Parent 4 0 R >>\n"
    )
    stream = b"2 0 obj\n<< /Type /ObjStm /N 33 /First 4 /Filter /FlateDecode >>\nstream\n"
    doc = b"%PDF-1.5\n" + stream + zlib.compress(content) + b"\nendstream\nendobj\n"
    monkeypatch.setattr(utils.media, "_PDF_INFLATE_INPUT_BYTES", input_bytes)
    monkeypatch.setattr(utils.media, "_PDF_INFLATE_OUTPUT_BYTES", output_bytes)
    assert _estimate(_write(tmp_path / "split.pdf", doc)) == 560 * 31


def test_pdf_page_count_is_cached_until_the_file_changes(tmp_path, monkeypatch):
    doc = _write(tmp_path / "doc.pdf", _pdf(3))
    media = classify_media([doc])[1]
    opened = []

    def counting_open(file, *args, **kwargs):
        opened.append(str(file))
        return open(file, *args, **kwargs)

    monkeypatch.setattr(utils.media, "open", counting_open, raising=False)
    assert estimate_media_tokens(media) == estimate_media_tokens(media) == 560 * 3
    assert opened.count(media[0].source_path) == 1
    stat = os.stat(doc)
    os.utime(doc, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert estimate_media_tokens(media) == 560 * 3
    assert opened.count(media[0].source_path) == 2


def test_page_object_with_long_whitespace_is_not_counted(tmp_path):
    # At most 32 whitespace bytes between /Type and /Page are recognised, so every match (with the
    # character after it) fits the 64-byte carry-over between inflated pieces, and a piecewise count
    # equals a whole-stream count. Writers put one space or none; 100 is not a page object we look for.
    body = b"<< /Type /Page >>\n<< /Type" + b" " * 100 + b"/Page >>\n"
    assert _estimate(_write(tmp_path / "spaced.pdf", b"%PDF-1.4\n" + body)) == 560


def test_page_object_with_32_spaces_across_a_piece_boundary_counts_once(tmp_path):
    # The spaced object starts 20 bytes before the first 1 MiB inflated piece ends.
    spaced = b"<< /Type" + b" " * 32 + b"/Page >>\n"
    content = b"4 0\n" + b"%" * (1024 * 1024 - 20 - 4) + spaced + b"<< /Type /Page >>\n"
    assert content.index(b"<< /Type" + b" " * 32) == 1024 * 1024 - 20
    stream = b"2 0 obj\n<< /Type /ObjStm /N 2 /First 4 /Filter /FlateDecode >>\nstream\n"
    doc = _write(tmp_path / "boundary.pdf", b"%PDF-1.5\n" + stream + zlib.compress(content) + b"\nendstream\nendobj\n")
    assert _estimate(doc) == 560 * 2


ONE_PAGE = b"%PDF-1.4\n1 0 obj\n<< /Type /Page >>\nendobj\n" + b"%" * 100 + b"\n"
THREE_PAGES = b"%PDF-1.4\n1 0 obj\n<< /Type /Page >><< /Type /Page >><< /Type /Page >>\nendobj\n"
THREE_PAGES += b"%" * (len(ONE_PAGE) - len(THREE_PAGES) - 1) + b"\n"


def test_page_count_cache_sees_a_rewrite_with_restored_mtime(tmp_path):
    # Same path, inode, size and mtime: only the change time (which utime cannot set) tells them apart.
    doc = _write(tmp_path / "doc.pdf", ONE_PAGE)
    media = classify_media([doc])[1]
    assert estimate_media_tokens(media) == 560
    before = os.stat(doc)
    Path(doc).write_bytes(THREE_PAGES)
    for _ in range(500):  # the change time may tick coarsely (a few ms on some kernels)
        os.utime(doc, ns=(before.st_atime_ns, before.st_mtime_ns))
        after = os.stat(doc)
        if after.st_ctime_ns != before.st_ctime_ns:
            break
        time.sleep(0.01)
    assert (after.st_ino, after.st_size, after.st_mtime_ns) == (before.st_ino, before.st_size, before.st_mtime_ns)
    assert after.st_ctime_ns != before.st_ctime_ns
    assert estimate_media_tokens(media) == 560 * 3


def test_page_count_cache_sees_a_replaced_file_with_restored_mtime(tmp_path):
    # As after cp -p, tar or unzip: a new file (new inode) of the same size and mtime at the same path.
    doc = _write(tmp_path / "doc.pdf", ONE_PAGE)
    media = classify_media([doc])[1]
    assert estimate_media_tokens(media) == 560
    before = os.stat(doc)
    restored = _write(tmp_path / "restored.pdf", THREE_PAGES)
    os.utime(restored, ns=(before.st_atime_ns, before.st_mtime_ns))
    os.replace(restored, doc)
    assert os.stat(doc).st_ino != before.st_ino
    assert estimate_media_tokens(media) == 560 * 3


def test_unreadable_pdf_count_is_not_cached(tmp_path, monkeypatch):
    doc = _write(tmp_path / "doc.pdf", _pdf(3) + PADDING)
    media = classify_media([doc])[1]
    failures = [OSError("transient read failure")]

    def flaky_open(*args, **kwargs):
        if failures:
            raise failures.pop()
        return open(*args, **kwargs)

    monkeypatch.setattr(utils.media, "open", flaky_open, raising=False)
    assert estimate_media_tokens(media) == _pdf_by_size(doc) == 560 * 11  # read failed: size-based
    assert estimate_media_tokens(media) == 560 * 3  # tried again, not served from the cache


# --- WAV headers: declared sizes are never trusted ---------------------------------------------


def test_zero_wav_data_size_runs_to_end_of_file(tmp_path):
    # Streaming WAV writers may never patch the data chunk size, leaving it at 0.
    recording = _write(tmp_path / "streamed.wav", _wav_header(0), 1024 * 1024)
    assert _estimate(recording) == 32 * 33  # (1 MiB - 44 B header) at 32,000 B/s = 32.8 s


@pytest.mark.parametrize("placeholder", [0xFFFFFFFF, 0x7FFFFFFF])
def test_placeholder_wav_data_size_runs_to_end_of_file(tmp_path, placeholder):
    recording = _write(tmp_path / "placeholder.wav", _wav_header(placeholder) + b"\x00" * 320_000)
    assert _estimate(recording) == 32 * 10  # 320,000 B at 32,000 B/s


def test_wav_without_a_byte_rate_falls_back_to_size(tmp_path):
    no_rate = WAV_FMT[:8] + (0).to_bytes(4, "little") + WAV_FMT[12:]
    recording = _write(tmp_path / "norate.wav", _wav_header(8_000, fmt=no_rate), 1024 * 1024)
    assert _estimate(recording) == _audio_by_size(recording) == 32 * 132  # 1 MiB at 8 kB/s = 131.1 s


def test_wav_huge_fmt_chunk_size_is_not_read_into_memory(tmp_path):
    # A 36-byte file whose fmt chunk claims ~4 GB: only the 16 bytes that matter may be read.
    recording = _write(tmp_path / "hugefmt.wav", _wav_header(0, fmt_size=0xFFFFFFF0)[:-8])
    media = classify_media([recording])[1]
    tracemalloc.start()
    try:
        tokens = estimate_media_tokens(media)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 1024 * 1024
    assert tokens == _audio_by_size(recording) == 32


def test_wav_chunk_walk_is_bounded(tmp_path):
    # 2,000 empty chunks before 'data': the walk gives up and the size-based estimate applies.
    head = b"RIFF" + (0).to_bytes(4, "little") + b"WAVE" + b"fmt " + (16).to_bytes(4, "little") + WAV_FMT
    head += b"junk" + (0).to_bytes(4, "little")
    recording = _write(
        tmp_path / "chunky.wav",
        head
        + (b"junk" + (0).to_bytes(4, "little")) * 1999
        + b"data"
        + (320_000).to_bytes(4, "little")
        + b"\x00" * 320_000,
    )
    assert _estimate(recording) == _audio_by_size(recording)


# --- MP4/MOV boxes: declared sizes are clamped to the file --------------------------------------


def test_huge_box_sizes_stay_inside_the_file(tmp_path):
    # moov claims 2**64 - 1 bytes and its child 2**63: neither may move a seek outside the file.
    clip = _write(
        tmp_path / "overflow.mp4", FTYP + _big_box(b"moov", 2**64 - 1, _big_box(b"free", 2**63)) + b"\x00" * 64
    )
    assert _estimate(clip) == _video_by_size(clip)


def test_huge_moov_still_finds_its_movie_header(tmp_path):
    clip = _write(tmp_path / "hugemoov.mp4", FTYP + _big_box(b"moov", 2**64 - 1, _mvhd(1000, 3000)))
    assert _estimate(clip) == 3 * 400


def test_64_bit_box_sizes_are_followed(tmp_path):
    moov = _big_box(b"moov", 16 + len(_mvhd(600, 6000)), _mvhd(600, 6000))
    clip = _write(tmp_path / "large.mp4", FTYP + _big_box(b"mdat", 16 + 64, b"\x00" * 64) + moov)
    assert _estimate(clip) == 10 * 400


def test_moov_with_size_zero_runs_to_end_of_file(tmp_path):
    moov = (0).to_bytes(4, "big") + b"moov" + _mvhd(1000, 3000)
    clip = _write(tmp_path / "tail.mp4", FTYP + _box(b"mdat", b"\x00" * 64) + moov)
    assert _estimate(clip) == 3 * 400


def test_box_header_crossing_its_parents_end_is_not_read(tmp_path):
    # moov ends 12 bytes into a 64-bit mvhd header. The walk must stop there: a body that starts past
    # its end would make read() get a negative size and load the rest of the file.
    moov_body = (1).to_bytes(4, "big") + b"mvhd" + bytes(4)
    moov = (8 + len(moov_body)).to_bytes(4, "big") + b"moov" + moov_body
    clip = _write(tmp_path / "crossing.mp4", FTYP + moov + (64).to_bytes(4, "big"), 32 * 1024 * 1024)
    tokens, peak = _estimate_traced(clip)
    assert peak < 1024 * 1024
    assert tokens == _video_by_size(clip)


class _CountingReader:
    """A file handle that counts read() calls."""

    def __init__(self, handle):
        self._handle, self.reads = handle, 0

    def read(self, *args):
        self.reads += 1
        return self._handle.read(*args)

    def __getattr__(self, name):
        return getattr(self._handle, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self._handle.close()


def test_only_the_first_mvex_is_walked(tmp_path, monkeypatch):
    # ISO 14496-12 allows one mvex per moov: 1024 of them with 1024 children each (about a million
    # boxes) must not be walked. Reads are counted so the bound does not depend on machine speed.
    mvex = _box(b"mvex", _box(b"free", b"") * 1024)
    clip = _write(tmp_path / "nested.mp4", FTYP + _box(b"moov", mvex * 1024))
    media = classify_media([clip])[1]
    handles = []

    def counting_open(*args, **kwargs):
        handles.append(_CountingReader(open(*args, **kwargs)))
        return handles[-1]

    monkeypatch.setattr(utils.media, "open", counting_open, raising=False)
    assert estimate_media_tokens(media) == _video_by_size(clip)
    assert sum(handle.reads for handle in handles) < 4 * 1024


def test_box_smaller_than_its_header_falls_back_to_size(tmp_path):
    clip = _write(
        tmp_path / "short.mp4", FTYP + (4).to_bytes(4, "big") + b"free" + _box(b"moov", _mvhd(1000, 3000)), 640_000
    )
    assert _estimate(clip) == _video_by_size(clip) == 10 * 400


@pytest.mark.parametrize("version,all_ones", [(0, 0xFFFFFFFF), (1, 0xFFFFFFFFFFFFFFFF)])
def test_all_ones_movie_duration_is_unknown(tmp_path, version, all_ones):
    clip = _write(tmp_path / "unknown.mp4", FTYP + _box(b"moov", _mvhd(1000, all_ones, version)), 640_000)
    assert _estimate(clip) == _video_by_size(clip) == 10 * 400


def test_truncated_movie_header_is_unknown(tmp_path):
    # mvhd claims 108 bytes but moov ends 18 bytes into its body; the bytes after moov are mdat.
    body = b"\x00" * 12 + (600).to_bytes(4, "big") + (600 * 3600).to_bytes(4, "big")
    moov = (8 + 8 + 18).to_bytes(4, "big") + b"moov" + (8 + 100).to_bytes(4, "big") + b"mvhd" + body[:18]
    clip = tmp_path / "truncated.mp4"
    with clip.open("wb") as handle:
        handle.write(FTYP + moov + (1024 * 1024).to_bytes(4, "big") + b"mdat")
        handle.truncate(len(FTYP) + len(moov) + 1024 * 1024)
    assert _estimate(str(clip)) == _video_by_size(str(clip))


def test_fragmented_movie_without_mehd_falls_back_to_size(tmp_path):
    # mvhd covers only the first fragment (2 s) of a 20 MiB file.
    moov = _box(b"moov", _mvhd(1000, 2000) + _box(b"mvex", _box(b"trex", b"\x00" * 24)))
    clip = _write(tmp_path / "fragmented.mp4", FTYP + moov + _box(b"moof", b"\x00" * 8), 20 * 1024 * 1024)
    assert _estimate(clip) == _video_by_size(clip) == 400 * 328


@pytest.mark.parametrize("version", [0, 1])
def test_fragmented_movie_uses_mehd_fragment_duration(tmp_path, version):
    width = 8 if version == 1 else 4
    mehd = _box(b"mehd", bytes([version]) + b"\x00" * 3 + (600_000).to_bytes(width, "big"))
    moov = _box(b"moov", _mvhd(1000, 2000) + _box(b"mvex", mehd))
    clip = _write(tmp_path / "fragmented.mp4", FTYP + moov + _box(b"moof", b"\x00" * 8), 20 * 1024 * 1024)
    assert _estimate(clip) == 600 * 400  # mehd: 600,000 ticks at 1000/s


def test_box_walk_is_bounded(tmp_path):
    # 100,000 empty boxes before moov: the walk gives up and the size-based estimate applies.
    clip = _write(tmp_path / "tiny.mp4", FTYP + _box(b"free", b"") * 100_000 + _box(b"moov", _mvhd(1000, 3000)))
    assert _estimate(clip) == _video_by_size(clip)


# --- Formats without an exact-duration reader, and where the bytes are read from -----------------


@pytest.mark.parametrize(
    "name,head,by_size",
    [
        ("a.mp3", b"\xff\xfb\x90\x00", _audio_by_size),
        ("a.ogg", b"OggS\x00\x02", _audio_by_size),
        ("a.flac", b"fLaC", _audio_by_size),
        ("a.webm", b"\x1a\x45\xdf\xa3", _video_by_size),
        ("a.mpeg", b"\x00\x00\x01\xba", _video_by_size),
    ],
)
def test_formats_without_a_duration_reader_use_size(tmp_path, name, head, by_size):
    media = _write(tmp_path / name, head, 800_000)
    assert _estimate(media) == by_size(media)


def test_m4a_uses_the_audio_rate(tmp_path):
    song = _write(
        tmp_path / "song.m4a", _box(b"ftyp", b"M4A \x00\x00\x02\x00M4A ") + _box(b"moov", _mvhd(44_100, 5 * 44_100))
    )
    assert _estimate(song) == 5 * 32


def test_estimate_reads_the_validated_file_not_the_callers_path(tmp_path):
    three_seconds = tmp_path / "otter.mp4"
    three_seconds.write_bytes(Path(MP4).read_bytes())
    ninety_seconds = _write(tmp_path / "long.mp4", FTYP + _box(b"moov", _mvhd(1000, 90_000)))
    latest = tmp_path / "latest"  # no media suffix: detected through its target
    latest.symlink_to(three_seconds)
    media = classify_media([str(latest)])[1]
    latest.unlink()
    latest.symlink_to(ninety_seconds)  # swapped after validation
    assert estimate_media_tokens(media) == 3 * 400


def test_media_prompt_section_lists_every_attachment():
    section = media_prompt_section(classify_media([PDF, MP4])[1])
    assert section.count("--- MEDIA FILE:") == 2
    assert "attached to this request as native video input" in section
    assert media_prompt_section([]) == ""


def test_media_prompt_section_numbers_attachments_in_order():
    section = media_prompt_section(classify_media([PDF, MP4])[1])
    assert section.index(f"--- MEDIA FILE: {PDF} ") < section.index(f"--- MEDIA FILE: {MP4} ")
    assert "native pdf input (attachment 1 of 2; the media parts follow in this order)." in section
    assert "native video input (attachment 2 of 2; the media parts follow in this order)." in section


def test_media_prompt_section_shows_small_files_in_kb(tmp_path):
    big = _sparse_mp4(tmp_path / "big.mp4", 3 * 1024 * 1024 + 200 * 1024)
    section = media_prompt_section(classify_media([PDF, MP4, str(big)])[1])
    assert f"--- MEDIA FILE: {PDF} (pdf, application/pdf, 0.6 KB) ---" in section  # 587 B
    assert f"--- MEDIA FILE: {MP4} (video, video/mp4, 7.9 KB) ---" in section  # 7,856 B
    assert f"--- MEDIA FILE: {big} (video, video/mp4, 3.4 MB) ---" in section  # 3,350,528 B


@pytest.mark.parametrize(
    "num_bytes,expected",
    [
        (0, "0.0 KB"),
        (587, "0.6 KB"),
        (7_856, "7.9 KB"),
        (999_949, "999.9 KB"),
        (999_999, "1.0 MB"),  # would round to "1000.0 KB"
        (3_350_528, "3.4 MB"),
        (999_999_999, "1.0 GB"),
        (2_000_000_000, "2.0 GB"),
        (3 * 10**9, "3.0 GB"),
    ],
)
def test_format_size(num_bytes, expected):
    assert format_size(num_bytes) == expected


def test_describe_uses_format_size():
    assert classify_media([MP4])[1][0].describe() == "video otter.mp4, 7.9 KB"
