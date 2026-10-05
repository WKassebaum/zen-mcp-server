"""BaseTool media helpers: validation, prompt announcement, token reserve, re-attach plan and its notes."""

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


def _thread_with_media(*paths):
    thread_id = create_thread("chat", {"prompt": "look"})
    add_turn(thread_id, "assistant", "seen", media=list(paths), tool_name="chat")
    return thread_id


def test_plan_omits_earlier_media_the_model_cannot_take():
    # Earlier media is never refused: the model gets a note instead (only media the call names is refused)
    tool = ChatTool()
    plan = tool._plan_call_media([], _thread_with_media(MP4), _context("o3", {}, set()), 100_000)
    assert plan.attachments == () and plan.own == ()
    assert plan.omitted == ("[omitted: earlier otter.mp4 — o3 does not take video]",)
    section = plan.prompt_section()
    assert "[omitted: earlier otter.mp4 — o3 does not take video]" in section
    assert "do not describe their contents from memory" in section


def test_plan_without_earlier_media_is_the_calls_own_media():
    tool = ChatTool()
    own = tool._media_from_paths([MP4])
    context = _context("m", {"supports_video": True}, {MediaKind.VIDEO})
    for continuation_id in (None, create_thread("chat", {"prompt": "look"})):
        plan = tool._plan_call_media(own, continuation_id, context, 100_000)
        assert plan.attachments == tuple(own) and plan.own == tuple(own) and plan.omitted == ()


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


def test_plan_re_attaches_earlier_media_and_announces_it():
    tool = ChatTool()
    context = _context("m", {"supports_video": True}, {MediaKind.VIDEO})
    plan = tool._plan_call_media([], _thread_with_media(MP4), context, 100_000)
    assert [a.path for a in plan.attachments] == [MP4] and plan.own == () and plan.omitted == ()
    section = plan.prompt_section()
    assert f"--- MEDIA FILE: {MP4} (video" in section and "NOT ATTACHED" not in section
    # A media-free, thread-free plan announces nothing
    assert tool._plan_call_media([], None, context, 100_000).prompt_section() == ""


def test_plan_expands_home_in_recorded_paths(tmp_path, monkeypatch):
    # The chat tool expands "~" in request paths; a recorded "~" path must name the same file when re-attached.
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "clip.mp4").write_bytes(Path(MP4).read_bytes())
    context = _context("m", {"supports_video": True}, {MediaKind.VIDEO})
    plan = ChatTool()._plan_call_media([], _thread_with_media("~/clip.mp4"), context, 100_000)
    assert [a.source_path for a in plan.attachments] == [str((tmp_path / "clip.mp4").resolve())]


def test_plan_matches_earlier_media_by_resolved_file(tmp_path):
    link = tmp_path / "same-otter.mp4"
    link.symlink_to(MP4)
    tool = ChatTool()
    own = tool._media_from_paths([str(link)])
    context = _context("m", {"supports_video": True}, {MediaKind.VIDEO})
    # The same file under another name is this call's own: attached once, under the call's name, nothing omitted.
    plan = tool._plan_call_media(own, _thread_with_media(MP4), context, 100_000)
    assert [a.path for a in plan.attachments] == [str(link)] and plan.omitted == ()
