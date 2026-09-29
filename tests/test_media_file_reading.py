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
