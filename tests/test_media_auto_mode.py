"""Auto mode routes media to capable models; the MCP size check never pre-empts the media check."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.registry import ModelProviderRegistry
from tools.chat import ChatTool
from tools.codereview import CodeReviewTool
from tools.shared.exceptions import ToolExecutionError
from utils.conversation_memory import add_turn, create_thread
from utils.media import MediaKind

MP4 = str(Path(__file__).parent / "fixtures" / "media" / "otter.mp4")


def _sparse_video(tmp_path, size=2 * 1024 * 1024) -> str:
    """A ~2 MB mp4: an 'ftyp' header and a hole. Far over o3's text budget if it were counted as text."""
    clip = tmp_path / "screen.mp4"
    with clip.open("wb") as handle:
        handle.write(b"\x00\x00\x00\x10ftypisom\x00\x00\x02\x00")
        handle.truncate(size)
    return str(clip)


def test_resolve_model_context_passes_required_media():
    tool = ChatTool()
    request = tool.get_request_model()(
        prompt="hi", absolute_file_paths=[MP4], working_directory_absolute_path="/tmp", model="auto"
    )
    with patch.object(ModelProviderRegistry, "get_preferred_fallback_model", return_value="gemini-3.8-flash") as pick:
        tool._resolve_model_context({"absolute_file_paths": [MP4], "model": "auto"}, request)
    assert pick.call_args.kwargs["required_media"] == frozenset({MediaKind.VIDEO})


@pytest.mark.asyncio
async def test_server_auto_mode_passes_required_media(tmp_path):
    import server

    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)),
        patch.object(
            ModelProviderRegistry,
            "get_preferred_fallback_model",
            wraps=ModelProviderRegistry.get_preferred_fallback_model,
        ) as pick,
        patch.object(ChatTool, "execute", return_value=[]),
    ):
        await server.handle_call_tool(
            "chat",
            {
                "prompt": "hi",
                "model": "auto",
                "absolute_file_paths": [MP4],
                "working_directory_absolute_path": str(tmp_path),
            },
        )
    assert pick.call_args_list[0].kwargs["required_media"] == frozenset({MediaKind.VIDEO})


@pytest.mark.asyncio
async def test_server_auto_mode_without_capable_model_is_a_tool_error(tmp_path):
    import server

    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset()):
        with pytest.raises(ToolExecutionError) as exc:
            await server.handle_call_tool(
                "chat",
                {
                    "prompt": "hi",
                    "model": "auto",
                    "absolute_file_paths": [MP4],
                    "working_directory_absolute_path": str(tmp_path),
                },
            )
    payload = json.loads(str(exc.value))
    assert payload["metadata"]["requested_model"] == "auto"  # refused while resolving auto, not by a picked model
    assert payload["content"].startswith("No available model can take video input: GEMINI_API_KEY")


@pytest.mark.asyncio
async def test_server_auto_mode_counts_media_from_earlier_workflow_steps(tmp_path):
    import server

    code = tmp_path / "app.py"
    code.write_text("print('hi')\n")
    thread_id = create_thread("codereview", {"step": "Review the recording", "relevant_files": [MP4]})
    add_turn(thread_id, "assistant", "step 1 recorded", files=[MP4], tool_name="codereview")
    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)),
        patch.object(
            ModelProviderRegistry,
            "get_preferred_fallback_model",
            wraps=ModelProviderRegistry.get_preferred_fallback_model,
        ) as pick,
        patch.object(CodeReviewTool, "execute", return_value=[]),
    ):
        await server.handle_call_tool(
            "codereview",
            {
                "step": "Final step",
                "step_number": 2,
                "total_steps": 2,
                "next_step_required": False,
                "findings": "done",
                "relevant_files": [str(code)],  # the final step narrowed the list: no media in this call
                "model": "auto",
                "continuation_id": thread_id,
            },
        )
    media_calls = [c for c in pick.call_args_list if c.kwargs.get("required_media")]
    assert media_calls and media_calls[-1].kwargs["required_media"] == frozenset({MediaKind.VIDEO})


@pytest.mark.asyncio
async def test_large_media_is_not_counted_as_text_at_mcp_boundary(tmp_path):
    import server

    clip = _sparse_video(tmp_path)
    with patch.object(ChatTool, "execute", return_value=[]) as execute:
        await server.handle_call_tool(
            "chat",
            {
                "prompt": "What happens in this recording?",
                "model": "gemini-3.8-flash",
                "absolute_file_paths": [clip],
                "working_directory_absolute_path": str(tmp_path),
            },
        )
    execute.assert_called_once()  # before the fix: code_too_large (2 MB counted as ~600K text tokens)


@pytest.mark.asyncio
async def test_large_media_on_incapable_model_gets_media_error_not_too_large(tmp_path):
    import server

    clip = _sparse_video(tmp_path)
    with patch.object(OpenAIModelProvider, "generate_content") as generate:
        with pytest.raises(ToolExecutionError) as exc:
            await server.handle_call_tool(
                "chat",
                {
                    "prompt": "What happens in this recording?",
                    "model": "o3",
                    "absolute_file_paths": [clip],
                    "working_directory_absolute_path": str(tmp_path),
                },
            )
    generate.assert_not_called()
    payload = json.loads(str(exc.value))
    assert payload["status"] == "error"
    assert "cannot take video input (screen.mp4)" in payload["content"]


@pytest.mark.asyncio
async def test_text_files_are_still_size_checked_next_to_media(tmp_path):
    import server

    big = tmp_path / "huge.py"
    big.write_text("x = 1\n" * 400_000)  # ~2.4 MB of text: over o3's file budget
    with patch.object(ChatTool, "execute", return_value=[]) as execute:
        with pytest.raises(ToolExecutionError) as exc:
            await server.handle_call_tool(
                "chat",
                {
                    "prompt": "Review",
                    "model": "o3",
                    "absolute_file_paths": [MP4, str(big)],
                    "working_directory_absolute_path": str(tmp_path),
                },
            )
    execute.assert_not_called()
    assert json.loads(str(exc.value))["status"] == "code_too_large"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs FIFOs")
@pytest.mark.asyncio
async def test_size_check_never_opens_a_fifo_named_like_a_text_file(tmp_path):
    import server
    import utils.media

    fifo = tmp_path / "pipe.ts"  # .ts is the one text extension looks_binary opens (MPEG-TS sniff)
    os.mkfifo(fifo)
    original = utils.media.looks_binary

    def guarded(path, *args, **kwargs):
        if os.path.realpath(path) == os.path.realpath(fifo):
            pytest.fail("looks_binary opened a FIFO: reading it would block the request forever")
        return original(path, *args, **kwargs)

    with (
        patch("utils.media.looks_binary", side_effect=guarded),
        patch.object(ChatTool, "execute", return_value=[]) as execute,
    ):
        await server.handle_call_tool(
            "chat",
            {
                "prompt": "hi",
                "model": "gemini-3.8-flash",
                "absolute_file_paths": [str(fifo)],
                "working_directory_absolute_path": str(tmp_path),
            },
        )
    execute.assert_called_once()


@pytest.mark.asyncio
async def test_continuation_reconstruction_never_sizes_history_with_an_incapable_model(tmp_path):
    # Continuation + model=auto + media no provider can take: the history-sizing fallback in
    # reconstruct_thread_context must refuse with the media message, not pick an incapable model.
    import server

    thread_id = create_thread("chat", {"prompt": "earlier question"})
    add_turn(thread_id, "assistant", "earlier answer", tool_name="chat")  # no model_name: stays auto
    arguments = {
        "prompt": "What happens in this recording?",
        "model": "auto",
        "absolute_file_paths": [MP4],
        "working_directory_absolute_path": str(tmp_path),
        "continuation_id": thread_id,
    }
    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset()),
        patch("utils.conversation_memory.build_conversation_history", return_value=("", 0)) as build_history,
    ):
        with pytest.raises(ToolExecutionError) as exc:
            await server.reconstruct_thread_context(dict(arguments))
    build_history.assert_not_called()
    payload = json.loads(str(exc.value))
    assert payload["metadata"]["requested_model"] == "auto"
    assert payload["content"].startswith("No available model can take video input: GEMINI_API_KEY")


@pytest.mark.asyncio
async def test_continuation_in_auto_mode_without_capable_model_is_a_tool_error(tmp_path):
    import server

    thread_id = create_thread("chat", {"prompt": "earlier question"})
    add_turn(thread_id, "assistant", "earlier answer", tool_name="chat")
    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset()),
        patch.object(ChatTool, "execute", return_value=[]) as execute,
    ):
        with pytest.raises(ToolExecutionError) as exc:
            await server.handle_call_tool(
                "chat",
                {
                    "prompt": "What happens in this recording?",
                    "model": "auto",
                    "absolute_file_paths": [MP4],
                    "working_directory_absolute_path": str(tmp_path),
                    "continuation_id": thread_id,
                },
            )
    execute.assert_not_called()
    assert json.loads(str(exc.value))["content"].startswith("No available model can take video input")
