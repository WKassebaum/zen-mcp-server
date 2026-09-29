"""Tests for the media size limit, token estimate and prompt announcement in utils.media."""

import math
import os
import tracemalloc
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
    """The size-based video estimate: 300 tokens/s at an assumed 64 kB/s."""
    return 300 * max(1, math.ceil(os.path.getsize(path) / 64_000))


def _audio_by_size(path: str) -> int:
    """The size-based audio estimate: 32 tokens/s at an assumed 8 kB/s."""
    return 32 * max(1, math.ceil(os.path.getsize(path) / 8_000))


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


def test_estimate_treats_zero_movie_duration_as_unknown(tmp_path):
    # Fragmented MP4s often leave the mvhd duration at 0; the real length lives in the fragments.
    clip = _write(
        tmp_path / "fragmented.mp4",
        _box(b"ftyp", b"iso5\x00\x00\x02\x00iso5") + _box(b"moov", _mvhd(1000, 0)),
        10 * 1024 * 1024,
    )
    assert _estimate(clip) == 300 * 164  # 10 MiB at 64 kB/s = 163.8 s


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
    assert _estimate(clip) == 3 * 300


def test_64_bit_box_sizes_are_followed(tmp_path):
    moov = _big_box(b"moov", 16 + len(_mvhd(600, 6000)), _mvhd(600, 6000))
    clip = _write(tmp_path / "large.mp4", FTYP + _big_box(b"mdat", 16 + 64, b"\x00" * 64) + moov)
    assert _estimate(clip) == 10 * 300


def test_moov_with_size_zero_runs_to_end_of_file(tmp_path):
    moov = (0).to_bytes(4, "big") + b"moov" + _mvhd(1000, 3000)
    clip = _write(tmp_path / "tail.mp4", FTYP + _box(b"mdat", b"\x00" * 64) + moov)
    assert _estimate(clip) == 3 * 300


def test_box_smaller_than_its_header_falls_back_to_size(tmp_path):
    clip = _write(
        tmp_path / "short.mp4", FTYP + (4).to_bytes(4, "big") + b"free" + _box(b"moov", _mvhd(1000, 3000)), 640_000
    )
    assert _estimate(clip) == _video_by_size(clip) == 10 * 300


@pytest.mark.parametrize("version,all_ones", [(0, 0xFFFFFFFF), (1, 0xFFFFFFFFFFFFFFFF)])
def test_all_ones_movie_duration_is_unknown(tmp_path, version, all_ones):
    clip = _write(tmp_path / "unknown.mp4", FTYP + _box(b"moov", _mvhd(1000, all_ones, version)), 640_000)
    assert _estimate(clip) == _video_by_size(clip) == 10 * 300


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
    assert _estimate(clip) == _video_by_size(clip) == 300 * 328


@pytest.mark.parametrize("version", [0, 1])
def test_fragmented_movie_uses_mehd_fragment_duration(tmp_path, version):
    width = 8 if version == 1 else 4
    mehd = _box(b"mehd", bytes([version]) + b"\x00" * 3 + (600_000).to_bytes(width, "big"))
    moov = _box(b"moov", _mvhd(1000, 2000) + _box(b"mvex", mehd))
    clip = _write(tmp_path / "fragmented.mp4", FTYP + moov + _box(b"moof", b"\x00" * 8), 20 * 1024 * 1024)
    assert _estimate(clip) == 600 * 300  # mehd: 600,000 ticks at 1000/s


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
    assert estimate_media_tokens(media) == 3 * 300


def test_media_prompt_section_lists_every_attachment():
    section = media_prompt_section(classify_media([PDF, MP4])[1])
    assert section.count("--- MEDIA FILE:") == 2
    assert "attached to this request as native video input" in section
