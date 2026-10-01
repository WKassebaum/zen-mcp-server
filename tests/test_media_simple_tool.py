"""Simple tools (chat and friends) validate native media, pass it to the provider, and track it across turns."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.shared import ModelResponse, ProviderType
from tools.chat import ChatTool
from tools.shared.exceptions import ToolExecutionError
from utils.media import MediaKind
from utils.model_context import ModelContext

FIXTURES = Path(__file__).parent / "fixtures" / "media"
MP4 = str(FIXTURES / "otter.mp4")


def _gemini_reply(text="OTTER-9"):
    return ModelResponse(content=text, usage={}, model_name="gemini-3.8-flash", provider=ProviderType.GOOGLE)


@pytest.fixture
def gemini_encodes_media():
    # The Gemini encoder arrives in Task 15; until then pretend it exists.
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        yield


@pytest.mark.asyncio
async def test_chat_sends_media_to_provider(tmp_path, gemini_encodes_media):
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await ChatTool().execute(
            {
                "prompt": "What text is shown?",
                "absolute_file_paths": [MP4],
                "working_directory_absolute_path": str(tmp_path),
                "model": "gemini-3.8-flash",
                "_model_context": ModelContext("gemini-3.8-flash"),
                "_resolved_model_name": "gemini-3.8-flash",
            }
        )
    media = generate.call_args.kwargs["media"]
    assert [m.name for m in media] == ["otter.mp4"]
    assert "--- MEDIA FILE:" in generate.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_chat_without_media_passes_none(tmp_path):
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply("hi")) as generate:
        await ChatTool().execute(
            {
                "prompt": "hello",
                "working_directory_absolute_path": str(tmp_path),
                "model": "gemini-3.8-flash",
                "_model_context": ModelContext("gemini-3.8-flash"),
                "_resolved_model_name": "gemini-3.8-flash",
            }
        )
    assert generate.call_args.kwargs.get("media") is None


@pytest.mark.asyncio
async def test_incapable_model_fails_before_any_api_call(tmp_path):
    with patch.object(OpenAIModelProvider, "generate_content") as generate:
        with pytest.raises(ToolExecutionError) as exc:
            await ChatTool().execute(
                {
                    "prompt": "What is shown?",
                    "absolute_file_paths": [MP4],
                    "working_directory_absolute_path": str(tmp_path),
                    "model": "o3",
                    "_model_context": ModelContext("o3"),
                    "_resolved_model_name": "o3",
                }
            )
    generate.assert_not_called()
    assert "cannot take video input (otter.mp4)" in json.loads(str(exc.value))["content"]


async def _first_turn(server, tmp_path) -> str:
    """MCP turn 1: chat on Gemini with the video attached. Returns the continuation_id."""
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()):
        result = await server.handle_call_tool(
            "chat",
            {
                "prompt": "What text is shown?",
                "model": "gemini-3.8-flash",
                "absolute_file_paths": [MP4],
                "working_directory_absolute_path": str(tmp_path),
            },
        )
    return json.loads(result[0].text)["continuation_offer"]["continuation_id"]


@pytest.mark.asyncio
async def test_follow_up_on_incapable_model_names_first_turn_media(tmp_path, gemini_encodes_media):
    import server

    thread_id = await _first_turn(server, tmp_path)
    with patch.object(OpenAIModelProvider, "generate_content") as generate:
        with pytest.raises(ToolExecutionError) as exc:
            await server.handle_call_tool(
                "chat",
                {
                    "prompt": "Now summarise it",
                    "model": "o3",
                    "continuation_id": thread_id,
                    "working_directory_absolute_path": str(tmp_path),
                },
            )
    generate.assert_not_called()
    content = json.loads(str(exc.value))["content"]
    assert "cannot take video input (otter.mp4)" in content
    assert "otter.mp4 came from the first turn of this conversation" in content


@pytest.mark.asyncio
async def test_follow_up_on_same_model_re_attaches_first_turn_media(tmp_path, gemini_encodes_media):
    import server

    thread_id = await _first_turn(server, tmp_path)
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await server.handle_call_tool(
            "chat",
            {
                "prompt": "Describe the colours",
                "model": "gemini-3.8-flash",
                "continuation_id": thread_id,
                "working_directory_absolute_path": str(tmp_path),
            },
        )
    assert [m.name for m in generate.call_args.kwargs["media"]] == ["otter.mp4"]
    assert "MEDIA NOT ATTACHED" not in generate.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_follow_up_with_other_files_says_media_is_not_attached(tmp_path, gemini_encodes_media):
    import server

    code = tmp_path / "app.py"
    code.write_text("print('hi')\n")
    thread_id = await _first_turn(server, tmp_path)
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await server.handle_call_tool(
            "chat",
            {
                "prompt": "Review this code instead",
                "model": "gemini-3.8-flash",
                "continuation_id": thread_id,
                "absolute_file_paths": [str(code)],
                "working_directory_absolute_path": str(tmp_path),
            },
        )
    assert generate.call_args.kwargs.get("media") is None
    prompt = generate.call_args.kwargs["prompt"]
    assert "=== MEDIA NOT ATTACHED ===" in prompt and "video otter.mp4" in prompt


@pytest.mark.asyncio
async def test_empty_response_retry_resends_media(tmp_path, gemini_encodes_media):
    empty = ModelResponse(
        content="",
        usage={},
        model_name="gemini-3.8-flash",
        provider=ProviderType.GOOGLE,
        metadata={"finish_reason": "STOP"},
    )
    with patch.object(GeminiModelProvider, "generate_content", side_effect=[empty, _gemini_reply()]) as generate:
        await ChatTool().execute(
            {
                "prompt": "What text is shown?",
                "absolute_file_paths": [MP4],
                "working_directory_absolute_path": str(tmp_path),
                "model": "gemini-3.8-flash",
                "_model_context": ModelContext("gemini-3.8-flash"),
                "_resolved_model_name": "gemini-3.8-flash",
            }
        )
    assert generate.call_count == 2
    for call in generate.call_args_list:
        assert [m.name for m in call.kwargs["media"]] == ["otter.mp4"]
