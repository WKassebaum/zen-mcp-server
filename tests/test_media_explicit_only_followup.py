"""A follow-up that omits ``model`` must not carry media to an explicit-only provider (xAI) by reusing its model.

server.reconstruct_thread_context reuses the previous assistant turn's model when a continuation names none. Auto
mode often picks Grok for text (xAI comes first in priority), so without a check a PDF attached on the follow-up, or
carried over from the first turn, would reach Grok although the user never named it on that call.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.shared import ModelResponse, ProviderType
from providers.xai import XAIModelProvider

PDF = str(Path(__file__).parent / "fixtures" / "media" / "zebra.pdf")


def _reply(model, provider):
    return ModelResponse(content="ok", usage={}, model_name=model, provider=provider)


async def _chat(server, tmp_path, model=None, continuation_id=None, files=None):
    arguments = {"prompt": "What is the code word?", "working_directory_absolute_path": str(tmp_path)}
    if model:
        arguments["model"] = model
    if continuation_id:
        arguments["continuation_id"] = continuation_id
    if files:
        arguments["absolute_file_paths"] = files
    with (
        patch.object(XAIModelProvider, "generate_content", return_value=_reply("grok-4.7", ProviderType.XAI)) as grok,
        patch.object(
            GeminiModelProvider, "generate_content", return_value=_reply("gemini-2.5-flash", ProviderType.GOOGLE)
        ) as gemini,
    ):
        result = await server.handle_call_tool("chat", arguments)
    return json.loads(result[0].text), grok, gemini


async def _grok_thread(server, tmp_path, files=None):
    first, grok, _ = await _chat(server, tmp_path, model="grok-4.7", files=files)
    assert grok.called
    return first["continuation_offer"]["continuation_id"]


@pytest.mark.asyncio
async def test_follow_up_pdf_does_not_reuse_the_grok_model(tmp_path):
    import server

    thread_id = await _grok_thread(server, tmp_path)

    _, grok, gemini = await _chat(server, tmp_path, continuation_id=thread_id, files=[PDF])

    assert not grok.called
    assert gemini.called
    assert [a.name for a in gemini.call_args.kwargs["media"]] == ["zebra.pdf"]


@pytest.mark.asyncio
async def test_first_turn_pdf_carried_into_a_follow_up_does_not_reuse_the_grok_model(tmp_path):
    import server

    thread_id = await _grok_thread(server, tmp_path, files=[PDF])

    _, grok, gemini = await _chat(server, tmp_path, continuation_id=thread_id)

    assert not grok.called
    assert gemini.called


@pytest.mark.asyncio
async def test_follow_up_naming_grok_still_sends_it_the_pdf(tmp_path):
    import server

    thread_id = await _grok_thread(server, tmp_path)

    _, grok, gemini = await _chat(server, tmp_path, model="grok-4.7", continuation_id=thread_id, files=[PDF])

    assert grok.called
    assert not gemini.called
    assert [a.name for a in grok.call_args.kwargs["media"]] == ["zebra.pdf"]


@pytest.mark.asyncio
async def test_text_follow_up_still_reuses_the_grok_model(tmp_path):
    import server

    thread_id = await _grok_thread(server, tmp_path)

    _, grok, gemini = await _chat(server, tmp_path, continuation_id=thread_id)

    assert grok.called
    assert not gemini.called


@pytest.mark.asyncio
async def test_unavailable_model_error_suggests_a_model_that_takes_the_pdf(tmp_path):
    # Anthropic is not registered in unit tests, so a Claude model is "not available"; the suggestion used to be
    # auto mode's text pick, a Grok model, which would then get the PDF without the user having chosen Grok.
    import server
    from tools.shared.exceptions import ToolExecutionError

    arguments = {
        "prompt": "What is the code word?",
        "model": "claude-sonnet-5-5",
        "working_directory_absolute_path": str(tmp_path),
        "absolute_file_paths": [PDF],
    }
    with pytest.raises(ToolExecutionError) as raised:
        await server.handle_call_tool("chat", arguments)
    message = json.loads(raised.value.payload)["content"]
    suggested = message.split("Suggested model for chat: '")[1].split("'")[0]
    assert not suggested.startswith("grok"), suggested
