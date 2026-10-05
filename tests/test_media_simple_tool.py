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
    # Pin the encoder kinds so these tests do not depend on what GeminiModelProvider declares.
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
async def test_follow_up_on_incapable_model_omits_first_turn_media(tmp_path, gemini_encodes_media):
    # The first turn's video is re-attached on follow-ups; a model that cannot take video gets a note instead, and
    # the call proceeds (only media this call names itself is refused).
    import server

    thread_id = await _first_turn(server, tmp_path)
    reply = ModelResponse(content="Summary.", usage={}, model_name="o3", provider=ProviderType.OPENAI)
    with patch.object(OpenAIModelProvider, "generate_content", return_value=reply) as generate:
        await server.handle_call_tool(
            "chat",
            {
                "prompt": "Now summarise it",
                "model": "o3",
                "continuation_id": thread_id,
                "working_directory_absolute_path": str(tmp_path),
            },
        )
    generate.assert_called_once()
    assert generate.call_args.kwargs.get("media") is None
    prompt = generate.call_args.kwargs["prompt"]
    assert "[omitted: earlier otter.mp4 — o3 does not take video]" in prompt
    assert "do not describe their contents from memory" in prompt
    assert "--- MEDIA FILE:" not in prompt


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
async def test_follow_up_with_other_files_re_attaches_earlier_media(tmp_path, gemini_encodes_media):
    # Naming other files no longer drops the first turn's video: earlier media travels with every follow-up.
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
    assert [m.name for m in generate.call_args.kwargs["media"]] == ["otter.mp4"]
    prompt = generate.call_args.kwargs["prompt"]
    assert "print('hi')" in prompt
    assert f"--- MEDIA FILE: {MP4} (video, video/mp4" in prompt and "(attachment 1 of 1;" in prompt
    assert "NOT ATTACHED" not in prompt


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
