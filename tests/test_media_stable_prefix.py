"""Media requests keep a byte-stable prefix across the turns of a conversation, so providers' prompt caches hit.

Layout for media requests (design section 4): the system prompt as its own element, then the media parts in
first-seen order across the thread, then the changing text (history plus the new request). Each case runs real chat
turns through the MCP server with only the provider's SDK client mocked, and compares the request payloads, serialized
with ``json.dumps(sort_keys=False)``, up to the end of the last media part.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from providers.anthropic import AnthropicProvider
from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.openrouter import CLAUDE_CACHE_BREAKPOINT_TEXT, OpenRouterProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ProviderType
from providers.xai import XAIModelProvider
from utils.media import MediaKind

PDF = Path(__file__).parent / "fixtures" / "media" / "zebra.pdf"
CHAT_MEDIA_TYPES = ("file", "input_audio", "video_url")
RESPONSES_MEDIA_TYPES = ("input_file", "input_audio", "input_video")


# --- per-endpoint clients and payloads ------------------------------------------------------------------------------


def _gemini_client():
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(
        text="ok", candidates=[MagicMock(finish_reason=None)], usage_metadata=None
    )
    return client, client.models.generate_content


def _gemini_payload(call) -> tuple[dict, list]:
    contents = call.kwargs["contents"]
    parts = contents[0]["parts"]
    media = [part for part in parts if "inline_data" in part or "file_data" in part]
    return {"system_instruction": call.kwargs["config"].system_instruction, "contents": contents}, media


def _anthropic_client():
    client = MagicMock()
    stream = MagicMock()
    stream.text_stream = ["ok"]
    stream.get_final_message.return_value = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=1, output_tokens=1), stop_reason="end_turn"
    )
    client.messages.stream.return_value.__enter__.return_value = stream
    return client, client.messages.stream


def _anthropic_payload(call) -> tuple[dict, list]:
    messages = call.kwargs["messages"]
    media = [block for block in messages[-1]["content"] if block["type"] == "document"]
    return {"system": call.kwargs["system"], "messages": messages}, media


def _chat_client():
    client = MagicMock()
    message = SimpleNamespace(content="ok", annotations=None)
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        model="m",
        id="c",
        created=0,
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    return client, client.chat.completions.create


def _chat_payload(call) -> tuple[dict, list]:
    messages = call.kwargs["messages"]
    media = [part for part in messages[-1]["content"] if part["type"] in CHAT_MEDIA_TYPES]
    return {"messages": messages}, media


def _responses_client():
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(
        output_text="ok",
        output=[],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2),
        model="m",
        id="r",
        created_at=0,
    )
    return client, client.responses.create


def _responses_payload(call) -> tuple[dict, list]:
    items = call.kwargs["input"]
    media = [part for part in items[-1]["content"] if part["type"] in RESPONSES_MEDIA_TYPES]
    return {"input": items}, media


@dataclass(frozen=True)
class Case:
    provider_class: type
    model: str
    client: Callable[[], tuple[Any, MagicMock]]
    payload: Callable[[Any], tuple[dict, list]]


CASES = {
    "gemini": Case(GeminiModelProvider, "gemini-3.8-flash", _gemini_client, _gemini_payload),
    "anthropic": Case(AnthropicProvider, "claude-sonnet-5-5", _anthropic_client, _anthropic_payload),
    "openai-chat": Case(OpenAIModelProvider, "gpt-5.5", _chat_client, _chat_payload),
    "openai-responses": Case(OpenAIModelProvider, "gpt-6-luna", _responses_client, _responses_payload),
    "xai-responses": Case(XAIModelProvider, "grok-4.7", _responses_client, _responses_payload),
    "openrouter-chat": Case(OpenRouterProvider, "google/gemini-3.8-flash", _chat_client, _chat_payload),
    "openrouter-chat-claude": Case(OpenRouterProvider, "anthropic/claude-sonnet-5.5", _chat_client, _chat_payload),
    "openrouter-responses": Case(OpenRouterProvider, "openai/gpt-6-luna", _responses_client, _responses_payload),
}


@pytest.fixture(autouse=True)
def every_provider(monkeypatch):
    providers = {
        ProviderType.GOOGLE: ("GEMINI_API_KEY", GeminiModelProvider),
        ProviderType.OPENAI: ("OPENAI_API_KEY", OpenAIModelProvider),
        ProviderType.XAI: ("XAI_API_KEY", XAIModelProvider),
        ProviderType.ANTHROPIC: ("ANTHROPIC_API_KEY", AnthropicProvider),
        ProviderType.OPENROUTER: ("OPENROUTER_API_KEY", OpenRouterProvider),
    }
    ModelProviderRegistry.reset_for_testing()
    for provider_type, (key, provider_class) in providers.items():
        monkeypatch.setenv(key, "dummy-key-for-tests")
        ModelProviderRegistry.register_provider(provider_type, provider_class)
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        yield
    ModelProviderRegistry.reset_for_testing()


def _serialized(payload: dict) -> str:
    return json.dumps(payload, sort_keys=False)


def _without_markers(value: Any) -> Any:
    """``value`` without Claude's ``cache_control`` markers. The marker moves to the last media block as files are
    added; Anthropic's cache key is the content up to each breakpoint, and a breakpoint finds the previous request's
    entry at an earlier block (20-block lookback), so a moved marker is not an invalidator."""
    if isinstance(value, dict):
        return {key: _without_markers(item) for key, item in value.items() if key != "cache_control"}
    if isinstance(value, list):
        return [_without_markers(item) for item in value]
    return value


def _media_end(payload: dict, media: list) -> int:
    """Offset in the serialized payload just past the last media part."""
    serialized, last = _serialized(payload), json.dumps(media[-1], sort_keys=False)
    position = serialized.rfind(last)
    assert position >= 0, "the last media part must appear verbatim in the payload"
    return position + len(last)


async def _turns(case: Case, tmp_path) -> list[tuple[dict, list]]:
    """Turn 1 attaches a.pdf; turn 2 names no files (a.pdf is re-attached); turn 3 names b.pdf."""
    import server

    first = tmp_path / "a.pdf"
    first.write_bytes(PDF.read_bytes())
    second = tmp_path / "b.pdf"
    second.write_bytes(PDF.read_bytes().replace(b"ZEBRA", b"HORSE"))
    client, sdk_call = case.client()
    base = {"model": case.model, "working_directory_absolute_path": str(tmp_path)}
    turns = [
        {"prompt": "What is the code word?", "absolute_file_paths": [str(first)]},
        {"prompt": "Spell it backwards, please, and explain."},
        {"prompt": "Compare it with this one.", "absolute_file_paths": [str(second)]},
    ]
    payloads = []
    continuation_id = None
    with patch.object(case.provider_class, "client", new_callable=PropertyMock, return_value=client):
        for turn in turns:
            arguments = {**base, **turn}
            if continuation_id:
                arguments["continuation_id"] = continuation_id
            result = await server.handle_call_tool("chat", arguments)
            continuation_id = continuation_id or json.loads(result[0].text)["continuation_offer"]["continuation_id"]
            payloads.append(case.payload(sdk_call.call_args))
    return payloads


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(CASES))
async def test_follow_up_payloads_share_their_prefix_through_the_last_media_part(name, tmp_path):
    (first, first_media), (second, second_media), (third, third_media) = await _turns(CASES[name], tmp_path)
    assert (len(first_media), len(second_media), len(third_media)) == (1, 1, 2)

    # Turn 2 re-attaches turn 1's file: identical bytes up to the end of the last media part, then the text differs
    end = _media_end(first, first_media)
    assert _media_end(second, second_media) == end
    assert _serialized(first)[:end] == _serialized(second)[:end]
    assert _serialized(first) != _serialized(second)

    # Turn 3 adds a file: the earlier file keeps its place, so turn 2's media prefix is turn 3's too. Compared without
    # cache_control markers: native Claude's marker moves from a.pdf to b.pdf, which keeps the cached entry at a.pdf
    second, third = _without_markers(second), _without_markers(third)
    end = _media_end(second, _without_markers(second_media))
    assert _serialized(third)[:end] == _serialized(second)[:end]
    assert _without_markers(third_media[0]) == _without_markers(second_media[0])
    assert _without_markers(third_media[1]) != _without_markers(second_media[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(CASES))
async def test_media_parts_come_before_the_text_and_the_system_prompt_stands_alone(name, tmp_path):
    case = CASES[name]
    (payload, media), _, _ = await _turns(case, tmp_path)
    serialized = _serialized(payload)
    prompt_text = "What is the code word?"
    assert serialized.index(json.dumps(prompt_text)[1:-1]) > _media_end(payload, media)
    if case.payload is _gemini_payload:
        assert payload["system_instruction"] and prompt_text not in payload["system_instruction"]
    elif case.payload is _anthropic_payload:
        assert payload["system"] and prompt_text not in payload["system"]
    elif case.payload is _chat_payload:
        system, user = payload["messages"]
        assert system["role"] == "system" and prompt_text not in system["content"]
        assert user["content"][-1]["type"] == "text"
    else:
        system, user = payload["input"]
        assert [part["type"] for part in system["content"]] == ["input_text"]
        assert prompt_text not in system["content"][0]["text"]
        assert user["content"][-1]["type"] == "input_text"


@pytest.mark.asyncio
async def test_openrouter_claude_breakpoint_follows_the_media_on_every_turn(tmp_path):
    turns = await _turns(CASES["openrouter-chat-claude"], tmp_path)
    for payload, media in turns:
        content = payload["messages"][-1]["content"]
        breakpoint_part = content[len(media)]
        assert breakpoint_part == {
            "type": "text",
            "text": CLAUDE_CACHE_BREAKPOINT_TEXT,
            "cache_control": {"type": "ephemeral"},
        }


@pytest.mark.asyncio
async def test_media_free_follow_up_keeps_todays_layout(tmp_path):
    # No media anywhere in the thread: Gemini still folds the system prompt into the text part, as before phase 5b
    import server

    client, sdk_call = _gemini_client()
    arguments = {"prompt": "hello", "model": "gemini-3.8-flash", "working_directory_absolute_path": str(tmp_path)}
    with patch.object(GeminiModelProvider, "client", new_callable=PropertyMock, return_value=client):
        result = await server.handle_call_tool("chat", arguments)
        thread_id = json.loads(result[0].text)["continuation_offer"]["continuation_id"]
        await server.handle_call_tool("chat", {**arguments, "prompt": "again", "continuation_id": thread_id})
    contents = sdk_call.call_args.kwargs["contents"]
    assert len(contents) == 1 and len(contents[0]["parts"]) == 1 and set(contents[0]["parts"][0]) == {"text"}
    assert sdk_call.call_args.kwargs["config"].system_instruction is None
