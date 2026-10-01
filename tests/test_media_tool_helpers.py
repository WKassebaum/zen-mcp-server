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
from utils.media import MEDIA_MAX_BYTES, MediaKind, format_size

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
    content = _error(exc)["content"]
    assert f"limited to {format_size(MEDIA_MAX_BYTES)} each" in content
    assert "huge.mp4" in content and f"{MEDIA_MAX_BYTES + 1:,} bytes" in content


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
    assert "SKIPPED FILES" not in content  # otter.mp4 is estimated at 1,200 tokens
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


def test_paths_from_initial_context_expands_home():
    # The chat tool expands "~" in request paths before classifying media; carried-over paths must match.
    arguments = {"absolute_file_paths": ["~/clip.mp4"], "_initial_context_keys": ["absolute_file_paths"]}
    expected = [str(Path.home() / "clip.mp4")]
    assert ChatTool()._paths_from_initial_context(arguments, "absolute_file_paths") == expected


def test_unattached_thread_media_note_matches_resolved_file(tmp_path):
    link = tmp_path / "same-otter.mp4"
    link.symlink_to(MP4)
    thread_id = create_thread("chat", {"prompt": "look"})
    add_turn(thread_id, "user", "look at this", files=[MP4])
    tool = ChatTool()
    # The same file under another name is attached, so nothing is missing.
    assert tool._unattached_thread_media_note(thread_id, tool._media_from_paths([str(link)])) == ""
