"""Media and binary files must never be embedded as text; BOM-marked text must stay readable."""

from pathlib import Path

import utils.file_utils
import utils.security_config
from tools.chat import ChatTool
from utils.conversation_memory import ConversationTurn, ThreadContext, get_conversation_file_list
from utils.file_utils import read_file_content
from utils.media import media_type_for

FIXTURES = Path(__file__).parent / "fixtures" / "media"
MP4 = str(FIXTURES / "otter.mp4")
TS_PACKET = b"\x47\x40\x00\x10" + b"\xff" * 184


def test_media_file_gets_placeholder_not_garbage():
    content, tokens = read_file_content(MP4)
    assert content.startswith(f"\n--- MEDIA FILE (NOT ATTACHED): {MP4} (video, video/mp4, ")
    # never the attached-media header of utils.media.media_prompt_section
    assert "--- MEDIA FILE:" not in content
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
    assert content.startswith(f"\n--- MEDIA FILE (NOT ATTACHED): {link} (video, video/mp4")


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
    capture.write_bytes(TS_PACKET * 3)
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
    prompt_content, remaining = ChatTool().handle_prompt_file([str(prompt)])
    assert prompt_content is None
    assert remaining == [str(prompt)]  # kept, so media detection attaches it instead of dropping it


def test_binary_prompt_txt_is_kept_as_a_file(tmp_path):
    blob = tmp_path / "blob"
    blob.write_bytes(b"\x7fELF\x00\x00\x00binary")
    prompt = tmp_path / "prompt.txt"
    prompt.symlink_to(blob)
    code = tmp_path / "app.py"
    code.write_text("x = 1\n")
    prompt_content, remaining = ChatTool().handle_prompt_file([str(code), str(prompt)])
    assert prompt_content is None
    assert remaining == [str(code), str(prompt)]


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


def test_text_file_is_validated_once(tmp_path, monkeypatch):
    code = tmp_path / "app.py"
    code.write_text("x = 1\n")
    real = utils.file_utils.resolve_and_validate_path
    calls = []

    def counting(path_str):
        calls.append(path_str)
        return real(path_str)

    monkeypatch.setattr(utils.file_utils, "resolve_and_validate_path", counting)
    read_file_content(str(code))
    assert calls == [str(code)]
    read_file_content(MP4)  # the media check reuses the validated path as well
    assert calls == [str(code), MP4]
    calls.clear()
    # Neither a media name nor a symlink: no filesystem work (get_conversation_file_list calls this per file).
    assert media_type_for(str(code)) is None
    assert calls == []


def test_utf8_bom_is_stripped(tmp_path):
    code = tmp_path / "app.py"
    code.write_bytes("x = 1\ny = 2\n".encode("utf-8-sig"))
    content, _ = read_file_content(str(code), include_line_numbers=True)
    assert "\ufeff" not in content
    assert "x = 1" in content


def test_utf8_bom_prompt_txt_has_no_bom(tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_bytes("Review this.\n".encode("utf-8-sig"))  # PowerShell 5.1 Set-Content -Encoding UTF8
    prompt_content, _ = ChatTool().handle_prompt_file([str(prompt)])
    assert prompt_content.strip() == "Review this."


def test_binary_starting_with_a_utf16_bom_is_rejected(tmp_path):
    # MPEG-1 Layer I frames with CRC start FF FE, which is also the UTF-16-LE byte-order mark.
    tone = tmp_path / "tone.mp2"
    tone.write_bytes(b"\xff\xfe\x90\x44" + b"\x00\x00\x12\x34" * 200)
    content, _ = read_file_content(str(tone))
    assert content.startswith(f"\n--- BINARY FILE: {tone} ---")


def test_mpeg_ts_named_ts_is_binary(tmp_path):
    segment = tmp_path / "seg0.ts"  # .ts is a TypeScript extension, so the NUL sniff alone would skip it
    segment.write_bytes(TS_PACKET * 3)
    content, _ = read_file_content(str(segment))
    assert content.startswith(f"\n--- BINARY FILE: {segment} ---")


def test_typescript_named_ts_stays_text(tmp_path):
    source = tmp_path / "app.ts"
    source.write_text("Greeting = 'G';\n" * 40)
    content, _ = read_file_content(str(source))
    assert "--- BEGIN FILE:" in content and "Greeting = 'G';" in content


def test_media_and_binary_checks_precede_the_size_limit(tmp_path):
    content, _ = read_file_content(MP4, max_size=100)
    assert content.startswith(f"\n--- MEDIA FILE (NOT ATTACHED): {MP4} ")
    blob = tmp_path / "firmware.bin"
    blob.write_bytes(b"\x7fELF\x00\x00\x00" * 100)
    content, _ = read_file_content(str(blob), max_size=100)
    assert content.startswith(f"\n--- BINARY FILE: {blob} ---")


def test_binary_placeholder_names_images(tmp_path):
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x01" * 30)
    content, _ = read_file_content(str(shot))
    assert content.startswith(f"\n--- BINARY FILE: {shot} ---")
    assert "image file: pass it in the `images` field, not the file list" in content


def test_binary_placeholder_names_invalid_media(tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"\x00\x00\x00\x18junk" + b"\x00" * 40)
    content, _ = read_file_content(str(broken))
    assert content.startswith(f"\n--- BINARY FILE: {broken} ---")
    assert "does not look like a valid .mp4 file" in content
    assert "not a supported media type" not in content
