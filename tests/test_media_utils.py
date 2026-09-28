"""Tests for utils.media classification helpers."""

import os
from pathlib import Path

import pytest

import utils.media
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
    assert media[0].source_path == str(blob.resolve())  # opened through the validated target, not the link


def test_symlink_loop_is_not_media(tmp_path):
    loop = tmp_path / "loop.mp4"
    loop.symlink_to(loop)
    assert media_type_for(str(loop)) is None


@pytest.mark.parametrize(
    "name,header,expected",
    [
        ("a.ogg", b"OggS\x00\x02" + b"\x00" * 26, (MediaKind.AUDIO, "audio/ogg")),
        ("a.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 28, (MediaKind.VIDEO, "video/webm")),
        ("a.mpg", b"\x00\x00\x01\xba" + b"\x00" * 28, (MediaKind.VIDEO, "video/mpeg")),
        ("a.mpeg", b"\x00\x00\x01\xb3" + b"\x00" * 28, (MediaKind.VIDEO, "video/mpeg")),
        ("a.mov", b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 20, (MediaKind.VIDEO, "video/quicktime")),
        ("a.m4a", b"\x00\x00\x00\x1cftypM4A " + b"\x00" * 20, (MediaKind.AUDIO, "audio/mp4")),
    ],
)
def test_format_signatures(tmp_path, name, header, expected):
    media = tmp_path / name
    media.write_bytes(header)
    assert media_type_for(str(media)) == expected
    impostor = tmp_path / f"impostor{media.suffix}"
    impostor.write_text("plain text wearing a media extension\n")
    assert media_type_for(str(impostor)) is None


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


def test_classify_media_rejects_bare_string():
    with pytest.raises(TypeError):
        classify_media(PDF)  # a str would otherwise be iterated one character at a time


def test_trailing_slash_media_path(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(Path(MP4).read_bytes())
    text_paths, media = classify_media([f"{clip}/"])
    assert text_paths == []
    assert len(media) == 1
    assert media[0].path == f"{clip}/"  # the caller's string is kept for display
    assert media[0].source_path == str(clip.resolve())
    assert media[0].size_bytes == clip.stat().st_size


def test_classify_media_dedupes_on_resolved_file(tmp_path):
    clip = tmp_path / "x.mp4"
    clip.write_bytes(Path(MP4).read_bytes())
    link = tmp_path / "link.mp4"
    link.symlink_to(clip)
    text_paths, media = classify_media([str(clip), f"{tmp_path}/./x.mp4", str(link)])
    assert text_paths == []
    assert len(media) == 1
    assert media[0].path == str(clip)  # the first caller path wins
    assert media[0].source_path == str(clip.resolve())


def test_media_file_vanishing_before_size_is_not_media(tmp_path, monkeypatch):
    clip = tmp_path / "clip.mp4"
    real_magic_matches = utils.media._magic_matches

    def matches_then_vanishes(extension, head):
        matched = real_magic_matches(extension, head)
        clip.unlink()  # deleted after validation and the signature check, before the size is read
        return matched

    monkeypatch.setattr(utils.media, "_magic_matches", matches_then_vanishes)
    clip.write_bytes(Path(MP4).read_bytes())
    assert media_type_for(str(clip)) is None
    clip.write_bytes(Path(MP4).read_bytes())
    assert classify_media([str(clip)]) == ([str(clip)], [])


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


@pytest.mark.parametrize("key", ["absolute_file_paths", "relevant_files"])
def test_media_kinds_from_arguments(key):
    assert media_kinds_from_arguments({key: [MP4]}) == frozenset({MediaKind.VIDEO})
    assert media_kinds_from_arguments({key: None}) == frozenset()
    assert media_kinds_from_arguments({}) == frozenset()


def test_media_kinds_from_arguments_ignores_files_key():
    # No request model reads a "files" field; the CLI sends absolute_file_paths / relevant_files.
    assert media_kinds_from_arguments({"files": [MP4]}) == frozenset()


def test_media_kinds_from_arguments_expands_home(tmp_path, monkeypatch):
    (tmp_path / "clip.mp4").write_bytes(Path(MP4).read_bytes())
    monkeypatch.setenv("HOME", str(tmp_path))
    assert media_kinds_from_arguments({"absolute_file_paths": ["~/clip.mp4"]}) == frozenset({MediaKind.VIDEO})


def test_media_attachment_is_hashable():
    _, media = classify_media([PDF])
    assert isinstance(media[0], MediaAttachment)
    assert len({media[0], media[0]}) == 1
