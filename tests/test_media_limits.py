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
