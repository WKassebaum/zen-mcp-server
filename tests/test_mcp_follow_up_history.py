"""An MCP follow-up sends the conversation history once and stores the user's own words.

server.reconstruct_thread_context stores the new user turn and embeds the history in the prompt before the
tool runs, so a simple tool must not store the turn again or wrap the prompt in a second history.
"""

import json
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.shared import ModelResponse, ProviderType
from utils.conversation_memory import get_thread

HISTORY_HEADER = "=== CONVERSATION HISTORY"


def _reply(text):
    return ModelResponse(content=text, usage={}, model_name="gemini-3.8-flash", provider=ProviderType.GOOGLE)


async def _chat(server, tmp_path, prompt, reply, continuation_id=None, files=None):
    arguments = {"prompt": prompt, "model": "gemini-3.8-flash", "working_directory_absolute_path": str(tmp_path)}
    if continuation_id:
        arguments["continuation_id"] = continuation_id
    if files:
        arguments["absolute_file_paths"] = files
    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply(reply)) as generate:
        result = await server.handle_call_tool("chat", arguments)
    return json.loads(result[0].text), generate.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_follow_up_prompt_carries_one_history_block(tmp_path):
    import server

    first, _ = await _chat(server, tmp_path, "Pick a colour", "Teal")
    thread_id = first["continuation_offer"]["continuation_id"]

    _, prompt = await _chat(server, tmp_path, "Why that one?", "It is calm", continuation_id=thread_id)

    assert prompt.count(HISTORY_HEADER) == 1
    assert prompt.count("Pick a colour") == 1


@pytest.mark.asyncio
async def test_follow_up_stores_the_users_own_words_once(tmp_path):
    import server

    first, _ = await _chat(server, tmp_path, "Pick a colour", "Teal")
    thread_id = first["continuation_offer"]["continuation_id"]

    await _chat(server, tmp_path, "Why that one?", "It is calm", continuation_id=thread_id)

    turns = get_thread(thread_id).turns
    assert [t.role for t in turns] == ["user", "assistant", "user", "assistant"]
    assert [t.content for t in turns if t.role == "user"] == ["Pick a colour", "Why that one?"]


@pytest.mark.asyncio
async def test_follow_up_still_embeds_newly_attached_files(tmp_path):
    import server

    first, _ = await _chat(server, tmp_path, "Pick a colour", "Teal")
    thread_id = first["continuation_offer"]["continuation_id"]
    notes = tmp_path / "notes.txt"
    notes.write_text("MARKER-MAGENTA-77\n")

    _, prompt = await _chat(
        server, tmp_path, "Compare with my notes", "Done", continuation_id=thread_id, files=[str(notes)]
    )

    assert prompt.count("MARKER-MAGENTA-77") == 1
