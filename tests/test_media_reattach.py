"""Media attached on any earlier turn travels with every follow-up (design section 3).

- Each turn records the media its call sent (ConversationTurn.media); get_conversation_media_list reads it back newest
  first, deduped by resolved file.
- A follow-up sends its own media plus the earlier media, attached in first-seen order across the thread. A file is
  never attached twice. initial_context carries first-turn text files only.
- Earlier media is left out, with a note in the manifest, when the file is gone, the model cannot take its kind, or
  the token budget runs out (oldest first). This call's own media is never left out: it is refused as before.
"""

import json
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ModelResponse, ProviderType
from providers.xai import XAIModelProvider
from tools.chat import ChatTool
from tools.consensus import ConsensusTool
from utils.conversation_memory import (
    add_turn,
    create_thread,
    get_conversation_media_first_seen,
    get_conversation_media_list,
    get_storage,
    get_thread,
)
from utils.media import MediaKind, format_size

FIXTURES = Path(__file__).parent / "fixtures" / "media"
PDF = str(FIXTURES / "zebra.pdf")
MP4 = str(FIXTURES / "otter.mp4")
GEMINI = "gemini-3.8-flash"


@pytest.fixture(autouse=True)
def providers_available(monkeypatch):
    # Earlier tests in the suite can leave the registry without these providers
    for key in ("GEMINI_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY"):
        monkeypatch.setenv(key, "dummy-key-for-tests")
    ModelProviderRegistry.reset_for_testing()
    ModelProviderRegistry.register_provider(ProviderType.GOOGLE, GeminiModelProvider)
    ModelProviderRegistry.register_provider(ProviderType.OPENAI, OpenAIModelProvider)
    ModelProviderRegistry.register_provider(ProviderType.XAI, XAIModelProvider)
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        yield
    ModelProviderRegistry.reset_for_testing()


def _pdf(tmp_path, name, marker=b"ZEBRA"):
    path = tmp_path / name
    path.write_bytes(Path(PDF).read_bytes().replace(b"ZEBRA", marker))
    return str(path)


def _reply(model=GEMINI, provider=ProviderType.GOOGLE, content="ok"):
    return ModelResponse(content=content, usage={}, model_name=model, provider=provider)


def _names(call):
    return [attachment.name for attachment in call.kwargs.get("media") or []]


async def _chat(tmp_path, files=None, model=GEMINI, continuation_id=None, provider_class=GeminiModelProvider):
    """One MCP chat turn on a mocked provider. Returns (continuation_id, generate_content mock)."""
    import server

    arguments = {"prompt": "What does it say?", "working_directory_absolute_path": str(tmp_path)}
    if model:
        arguments["model"] = model
    if files:
        arguments["absolute_file_paths"] = list(files)
    if continuation_id:
        arguments["continuation_id"] = continuation_id
    reply = _reply(model or GEMINI, ModelProviderRegistry.get_provider_for_model(model or GEMINI).get_provider_type())
    with patch.object(provider_class, "generate_content", return_value=reply) as generate:
        result = await server.handle_call_tool("chat", arguments)
    payload = json.loads(result[0].text)
    return (payload.get("continuation_offer") or {}).get("continuation_id") or continuation_id, generate


# --- recording and lookup -------------------------------------------------------------------------------------------


def test_turn_media_round_trips_through_storage():
    thread_id = create_thread("chat", {"prompt": "look"})
    add_turn(thread_id, "assistant", "seen", files=[PDF], media=[PDF], tool_name="chat")
    assert get_thread(thread_id).turns[-1].media == [PDF]


def test_turn_stored_without_the_media_field_loads():
    thread_id = create_thread("chat", {"prompt": "look"})
    add_turn(thread_id, "user", "look", files=[PDF])
    stored = get_storage().get(f"thread:{thread_id}")
    for turn in stored["turns"]:
        turn.pop("media", None)  # as stored before turns recorded media
    get_storage().set(f"thread:{thread_id}", stored)
    thread = get_thread(thread_id)
    assert thread is not None and thread.turns[-1].media is None
    assert get_conversation_media_list(thread) == []


def test_media_list_is_newest_first_and_deduped_by_resolved_file(tmp_path):
    first, second = _pdf(tmp_path, "a.pdf"), _pdf(tmp_path, "b.pdf", b"HORSE")
    alias = tmp_path / "alias.pdf"
    alias.symlink_to(first)
    thread_id = create_thread("chat", {"prompt": "look"})
    add_turn(thread_id, "assistant", "1", media=[first], tool_name="chat")
    add_turn(thread_id, "user", "2", files=[second])  # a user turn records no media: nothing was sent yet
    add_turn(thread_id, "assistant", "2", media=[second], tool_name="chat")
    add_turn(thread_id, "assistant", "3", media=[str(alias)], tool_name="chat")
    thread = get_thread(thread_id)
    assert get_conversation_media_list(thread) == [str(alias), second]
    assert get_conversation_media_first_seen(thread) == [first, second]


# --- simple tools ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_third_turn_sends_both_earlier_pdfs(tmp_path):
    first, second = _pdf(tmp_path, "a.pdf"), _pdf(tmp_path, "b.pdf", b"HORSE")
    thread_id, _ = await _chat(tmp_path, files=[first])
    await _chat(tmp_path, files=[second], continuation_id=thread_id)
    _, generate = await _chat(tmp_path, continuation_id=thread_id)

    assert get_conversation_media_list(get_thread(thread_id)) == [second, first]  # newest first
    assert _names(generate.call_args) == ["a.pdf", "b.pdf"]  # attached in first-seen order
    prompt = generate.call_args.kwargs["prompt"]
    assert re.findall(r"--- MEDIA FILE: (.+?) \(pdf", prompt) == [first, second]
    assert "(attachment 1 of 2;" in prompt and "(attachment 2 of 2;" in prompt


@pytest.mark.asyncio
async def test_turns_record_only_the_media_they_named(tmp_path):
    first, second = _pdf(tmp_path, "a.pdf"), _pdf(tmp_path, "b.pdf", b"HORSE")
    thread_id, _ = await _chat(tmp_path, files=[first])
    await _chat(tmp_path, files=[second], continuation_id=thread_id)
    await _chat(tmp_path, continuation_id=thread_id)
    recorded = [turn.media for turn in get_thread(thread_id).turns if turn.role == "assistant"]
    # Re-attached media keeps its own turn's age, so budget trimming drops what was attached longest ago
    assert recorded == [[first], [second], None]


@pytest.mark.asyncio
async def test_first_turn_text_file_comes_back_once_through_initial_context(tmp_path):
    notes = tmp_path / "notes.py"
    notes.write_text("MARKER_TEXT_FILE = 1\n")
    thread_id, _ = await _chat(tmp_path, files=[PDF, str(notes)])
    _, generate = await _chat(tmp_path, continuation_id=thread_id)

    prompt = generate.call_args.kwargs["prompt"]
    assert prompt.count("MARKER_TEXT_FILE = 1") == 1
    assert _names(generate.call_args) == ["zebra.pdf"]  # through re-attach, not initial_context
    assert prompt.count("--- MEDIA FILE:") == 1


@pytest.mark.asyncio
async def test_initial_context_no_longer_carries_media():
    import server

    thread_id = create_thread("chat", {"prompt": "look", "absolute_file_paths": [PDF, "/tmp/notes.py"]})
    add_turn(thread_id, "assistant", "seen", files=[PDF, "/tmp/notes.py"], media=[PDF], tool_name="chat")
    arguments = await server.reconstruct_thread_context(
        {"prompt": "again", "continuation_id": thread_id, "model": GEMINI}, tool_name="chat"
    )
    assert arguments["absolute_file_paths"] == ["/tmp/notes.py"]
    assert "_initial_context_keys" not in arguments


@pytest.mark.asyncio
async def test_naming_an_earlier_pdf_again_attaches_it_once(tmp_path):
    first = _pdf(tmp_path, "a.pdf")
    alias = tmp_path / "same-a.pdf"
    alias.symlink_to(first)
    thread_id, _ = await _chat(tmp_path, files=[first])
    _, generate = await _chat(tmp_path, files=[first], continuation_id=thread_id)
    assert _names(generate.call_args) == ["a.pdf"]
    _, generate = await _chat(tmp_path, files=[str(alias)], continuation_id=thread_id)
    assert _names(generate.call_args) == ["same-a.pdf"]
    assert generate.call_args.kwargs["prompt"].count("--- MEDIA FILE:") == 1


@pytest.mark.asyncio
async def test_deleted_earlier_file_is_omitted_with_a_note(tmp_path):
    first = _pdf(tmp_path, "report.pdf")
    thread_id, _ = await _chat(tmp_path, files=[first])
    os.remove(first)
    _, generate = await _chat(tmp_path, continuation_id=thread_id)
    assert generate.called
    assert generate.call_args.kwargs.get("media") is None
    assert "[omitted: earlier report.pdf — file no longer exists]" in generate.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_follow_up_to_a_model_without_video_omits_the_earlier_video(tmp_path):
    first = _pdf(tmp_path, "a.pdf")
    thread_id, _ = await _chat(tmp_path, files=[MP4, first])
    reply = _reply("o3", ProviderType.OPENAI)
    with patch.object(OpenAIModelProvider, "generate_content", return_value=reply) as generate:
        import server

        await server.handle_call_tool(
            "chat",
            {
                "prompt": "Summarise it",
                "model": "o3",
                "continuation_id": thread_id,
                "working_directory_absolute_path": str(tmp_path),
            },
        )
    assert generate.called  # the call proceeds
    assert _names(generate.call_args) == ["a.pdf"]  # o3 reads PDFs
    assert "[omitted: earlier otter.mp4 — o3 does not take video]" in generate.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_this_calls_own_media_is_still_refused(tmp_path):
    from tools.shared.exceptions import ToolExecutionError

    thread_id, _ = await _chat(tmp_path, files=[PDF])
    with patch("providers.registry.ModelProviderRegistry.find_media_capable_models", return_value=[GEMINI]):
        with pytest.raises(ToolExecutionError, match=r"cannot take video input \(otter.mp4\)"):
            await _chat(
                tmp_path, files=[MP4], model="o3", continuation_id=thread_id, provider_class=OpenAIModelProvider
            )


@pytest.mark.asyncio
async def test_over_budget_drops_the_oldest_earlier_file(tmp_path):
    first, second, third = (_pdf(tmp_path, f"{n}.pdf", m) for n, m in (("a", b"ONE"), ("b", b"TWO"), ("c", b"SIX")))
    thread_id, _ = await _chat(tmp_path, files=[first])
    await _chat(tmp_path, files=[second], continuation_id=thread_id)

    def estimate(media, *rates):
        return 1_000 * len(list(media))

    with (
        patch("utils.media.estimate_media_tokens", side_effect=estimate),
        patch.object(ChatTool, "_file_token_budget", return_value=1_500),
    ):
        _, generate = await _chat(tmp_path, continuation_id=thread_id)
        assert _names(generate.call_args) == ["b.pdf"]
        assert "[omitted: older a.pdf — over budget]" in generate.call_args.kwargs["prompt"]

        # This call's own media is never dropped, even when it alone is over budget
        _, generate = await _chat(tmp_path, files=[third], continuation_id=thread_id)
        assert _names(generate.call_args) == ["c.pdf"]
        prompt = generate.call_args.kwargs["prompt"]
        assert "[omitted: older a.pdf — over budget]" in prompt
        assert "[omitted: older b.pdf — over budget]" in prompt


@pytest.mark.asyncio
async def test_cli_follow_up_re_attaches_too(tmp_path):
    # The CLI runs tools in-process: no server reconstruction, the tool builds the history itself
    first = _pdf(tmp_path, "a.pdf")
    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply()):
        result = await ChatTool().execute(
            {
                "prompt": "What does it say?",
                "absolute_file_paths": [first],
                "working_directory_absolute_path": str(tmp_path),
                "model": GEMINI,
            }
        )
    thread_id = json.loads(result[0].text)["continuation_offer"]["continuation_id"]
    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply()) as generate:
        await ChatTool().execute(
            {
                "prompt": "And now?",
                "continuation_id": thread_id,
                "working_directory_absolute_path": str(tmp_path),
                "model": GEMINI,
            }
        )
    assert _names(generate.call_args) == ["a.pdf"]


@pytest.mark.asyncio
async def test_re_attached_upload_reuses_the_cached_upload(tmp_path, monkeypatch):
    # Phase 5a's upload cache: re-attaching a file Gemini took through the Files API costs no new upload
    from types import SimpleNamespace
    from unittest.mock import MagicMock, PropertyMock

    import server

    monkeypatch.setenv("ZEN_MEDIA_UPLOAD_CACHE", str(tmp_path / "zen" / "media_uploads.json"))
    monkeypatch.setattr(GeminiModelProvider, "INLINE_MEDIA_MAX_BYTES", 1024)  # the 67 KB WAV is uploaded
    wav = str(FIXTURES / "pelican.wav")
    remote = SimpleNamespace(
        name="files/w", uri="https://gen.test/files/w", mime_type="audio/wav", state=SimpleNamespace(name="ACTIVE")
    )
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(
        text="ok", candidates=[MagicMock(finish_reason=None)], usage_metadata=None
    )
    client.files.upload.return_value = remote
    client.files.get.return_value = remote
    arguments = {"prompt": "Transcribe", "model": GEMINI, "working_directory_absolute_path": str(tmp_path)}
    with patch.object(GeminiModelProvider, "client", new_callable=PropertyMock, return_value=client):
        first = await server.handle_call_tool("chat", {**arguments, "absolute_file_paths": [wav]})
        thread_id = json.loads(first[0].text)["continuation_offer"]["continuation_id"]
        second = await server.handle_call_tool("chat", {**arguments, "continuation_id": thread_id})

    assert client.files.upload.call_count == 1
    parts = client.models.generate_content.call_args.kwargs["contents"][0]["parts"]
    assert parts[0] == {"file_data": {"file_uri": "https://gen.test/files/w", "mime_type": "audio/wav"}}
    attached = json.loads(second[0].text)["metadata"]["media_attached"]
    assert [(record["name"], record["transport"]) for record in attached] == [("pelican.wav", "cached")]


# --- workflow and consensus -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_final_step_re_attaches_earlier_media(tmp_path):
    import server

    code = tmp_path / "app.py"
    code.write_text("print('hi')\n")
    own = _pdf(tmp_path, "spec.pdf", b"HORSE")
    thread_id, _ = await _chat(tmp_path, files=[MP4])
    expert = ModelResponse(
        content='{"status": "analysis_complete"}', usage={}, model_name=GEMINI, provider=ProviderType.GOOGLE
    )
    with patch.object(GeminiModelProvider, "generate_content", return_value=expert) as generate:
        await server.handle_call_tool(
            "analyze",
            {
                "step": "Final step",
                "step_number": 1,
                "total_steps": 1,
                "next_step_required": False,
                "findings": "done",
                "relevant_files": [str(code), own],
                "model": GEMINI,
                "continuation_id": thread_id,
            },
        )
    assert _names(generate.call_args) == ["otter.mp4", "spec.pdf"]
    prompt = generate.call_args.kwargs["prompt"]
    assert re.findall(r"--- MEDIA FILE: (.+?) \((?:pdf|video)", prompt) == [MP4, own]
    analyze_turn = [t for t in get_thread(thread_id).turns if t.tool_name == "analyze"][-1]
    assert analyze_turn.media == [own]  # the expert call's own media


@pytest.mark.asyncio
async def test_consensus_re_attaches_earlier_media(tmp_path):
    thread_id, _ = await _chat(tmp_path, files=[PDF])
    reply = _reply()
    with patch.object(GeminiModelProvider, "generate_content", return_value=reply) as generate:
        await ConsensusTool().execute(
            {
                "step": "Should we ship this spec?",
                "step_number": 1,
                "total_steps": 2,
                "next_step_required": True,
                "findings": "Initial review.",
                "models": [{"model": GEMINI, "stance": "neutral"}, {"model": "gemini-3.5-flash", "stance": "neutral"}],
                "continuation_id": thread_id,
            }
        )
    assert _names(generate.call_args) == ["zebra.pdf"]
    assert f"--- MEDIA FILE: {PDF} (pdf" in generate.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_consensus_later_step_gets_the_proposal_media_by_re_attach(tmp_path):
    import server

    models = [{"model": GEMINI, "stance": "for"}, {"model": "gemini-3.5-flash", "stance": "against"}]
    step = {"total_steps": 2, "findings": "Reviewed.", "models": models}
    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply()):
        first = await server.handle_call_tool(
            "consensus",
            {**step, "step": "Ship this spec?", "step_number": 1, "next_step_required": True, "relevant_files": [PDF]},
        )
    thread_id = json.loads(first[0].text)["continuation_offer"]["continuation_id"]
    assert [t.media for t in get_thread(thread_id).turns] == [[PDF]]  # the proposal's media

    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply()) as generate:
        await server.handle_call_tool(
            "consensus",
            {
                **step,
                "step": "Model 1 said yes",
                "step_number": 2,
                "next_step_required": False,
                "continuation_id": thread_id,
            },
        )
    assert _names(generate.call_args) == ["zebra.pdf"]
    assert generate.call_args.kwargs["prompt"].count("--- MEDIA FILE:") == 1


# --- explicit-only providers ----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grok_reuse_is_blocked_when_only_re_attached_media_is_present(tmp_path):
    thread_id, _ = await _chat(tmp_path)  # turn 1: text only, so initial_context holds no media
    await _chat(tmp_path, files=[PDF], continuation_id=thread_id)  # turn 2: Gemini reads the PDF
    # Turn 3 names Grok: it takes the earlier PDF because this call named it
    _, grok = await _chat(tmp_path, model="grok-4.7", continuation_id=thread_id, provider_class=XAIModelProvider)
    assert _names(grok.call_args) == ["zebra.pdf"]

    # Turn 4 names no model and no files: reusing Grok would hand it the re-attached PDF unasked
    import server

    arguments = {"prompt": "And?", "continuation_id": thread_id, "working_directory_absolute_path": str(tmp_path)}
    with (
        patch.object(XAIModelProvider, "generate_content", return_value=_reply("grok-4.7", ProviderType.XAI)) as grok,
        patch.object(GeminiModelProvider, "generate_content", return_value=_reply()) as gemini,
    ):
        await server.handle_call_tool("chat", arguments)
    assert not grok.called
    assert gemini.called and _names(gemini.call_args) == ["zebra.pdf"]


def test_call_media_kinds_counts_recorded_media_for_any_tool():
    import server

    thread_id = create_thread("chat", {"prompt": "look"})
    add_turn(thread_id, "assistant", "seen", files=[MP4], media=[MP4], tool_name="chat")
    thread = get_thread(thread_id)
    assert server._call_media_kinds("chat", server.TOOLS["chat"], {}, thread) == frozenset({MediaKind.VIDEO})


def test_cli_auto_mode_routes_on_recorded_media(tmp_path):
    # In-process (CLI) auto resolution must count the thread's media too, or it may pick an explicit-only provider
    thread_id = create_thread("chat", {"prompt": "look"})
    add_turn(thread_id, "assistant", "seen", media=[PDF], tool_name="chat")
    tool = ChatTool()
    request = tool.get_request_model()(
        prompt="again", continuation_id=thread_id, working_directory_absolute_path=str(tmp_path), model="auto"
    )
    with patch.object(ModelProviderRegistry, "resolve_model_intent", return_value=GEMINI) as resolve:
        tool._resolve_model_context({"model": "auto", "continuation_id": thread_id}, request)
    assert resolve.call_args.kwargs["required_media"] == frozenset({MediaKind.PDF})


# --- a call's own text files come before earlier media --------------------------------------------------------------


def _per_media_estimate(media, *rates):
    return 1_000 * len(list(media))


def _big_text_file(tmp_path):
    """big.py, about 2,000 tokens as workflow tools and consensus embed it (line-numbered)."""
    from utils.file_utils import read_file_content

    path = tmp_path / "big.py"
    path.write_text("".join(f"BIG_MARKER_{n:04d} = '{'x' * 24}'\n" for n in range(170)))
    tokens = read_file_content(str(path), include_line_numbers=True)[1]
    assert 1_600 < tokens < 2_400, tokens  # the budgets below assume about 2,000
    return str(path)


async def _analyze_final_step(files, continuation_id=None):
    import server

    arguments = {
        "step": "Final step",
        "step_number": 1,
        "total_steps": 1,
        "next_step_required": False,
        "findings": "done",
        "relevant_files": files,
        "model": GEMINI,
    }
    if continuation_id:
        arguments["continuation_id"] = continuation_id
    expert = ModelResponse(
        content='{"status": "analysis_complete"}', usage={}, model_name=GEMINI, provider=ProviderType.GOOGLE
    )
    with patch.object(GeminiModelProvider, "generate_content", return_value=expert) as generate:
        await server.handle_call_tool("analyze", arguments)
    return generate


@pytest.mark.asyncio
async def test_workflow_own_text_files_come_before_re_attached_media(tmp_path):
    # The reviewer's case: a chat turn attaches a.pdf; analyze's final step on the thread names big.py, with a
    # 3,500-token file budget. big.py (~2,000) fits alone; with the PDF (1,000) re-attached first, it did not.
    big, pdf = _big_text_file(tmp_path), _pdf(tmp_path, "a.pdf")
    thread_id, _ = await _chat(tmp_path, files=[pdf])
    with (
        patch("utils.media.estimate_media_tokens", side_effect=_per_media_estimate),
        patch("tools.workflow.workflow_mixin._expert_file_budget", return_value=3_500),
    ):
        alone = await _analyze_final_step([big])
        follow_up = await _analyze_final_step([big], continuation_id=thread_id)

    assert "BIG_MARKER_0169" in alone.call_args.kwargs["prompt"]  # control: without earlier media it fits
    prompt = follow_up.call_args.kwargs["prompt"]
    assert "BIG_MARKER_0169" in prompt and "SKIPPED FILES" not in prompt
    assert follow_up.call_args.kwargs.get("media") is None
    assert "[omitted: older a.pdf — over budget]" in prompt


@pytest.mark.asyncio
async def test_workflow_re_attaches_earlier_media_into_what_its_text_leaves(tmp_path):
    # Not over-cautious: with room for both, the PDF still goes out next to big.py
    big, pdf = _big_text_file(tmp_path), _pdf(tmp_path, "a.pdf")
    thread_id, _ = await _chat(tmp_path, files=[pdf])
    with (
        patch("utils.media.estimate_media_tokens", side_effect=_per_media_estimate),
        patch("tools.workflow.workflow_mixin._expert_file_budget", return_value=5_000),
    ):
        follow_up = await _analyze_final_step([big], continuation_id=thread_id)
    assert _names(follow_up.call_args) == ["a.pdf"]
    assert "BIG_MARKER_0169" in follow_up.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_debug_plans_media_against_the_budget_it_embeds_with(tmp_path):
    # Debug embeds its files through _prepare_file_content_for_prompt (BaseTool._file_token_budget), not the
    # workflow expert allocation: re-attach must trim against that same number
    import server
    from tools.debug import DebugIssueTool

    big, pdf = _big_text_file(tmp_path), _pdf(tmp_path, "a.pdf")
    thread_id, _ = await _chat(tmp_path, files=[pdf])
    expert = ModelResponse(
        content='{"status": "analysis_complete"}', usage={}, model_name=GEMINI, provider=ProviderType.GOOGLE
    )
    with (
        patch("utils.media.estimate_media_tokens", side_effect=_per_media_estimate),
        patch("tools.workflow.workflow_mixin._expert_file_budget", return_value=100_000),
        patch.object(DebugIssueTool, "_file_token_budget", return_value=2_500),
        patch.object(GeminiModelProvider, "generate_content", return_value=expert) as generate,
    ):
        await server.handle_call_tool(
            "debug",
            {
                "step": "Root cause found",
                "step_number": 1,
                "total_steps": 1,
                "next_step_required": False,
                "findings": "The loop never ends.",
                "hypothesis": "Off-by-one in the loop bound",
                "confidence": "high",
                "relevant_files": [big],
                "model": GEMINI,
                "continuation_id": thread_id,
            },
        )
    prompt = generate.call_args.kwargs["prompt"]
    assert "BIG_MARKER_0169" in prompt and "SKIPPED FILES" not in prompt
    assert generate.call_args.kwargs.get("media") is None
    assert "[omitted: older a.pdf — over budget]" in prompt


async def _consensus_step_one(files, continuation_id=None):
    arguments = {
        "step": "Should we ship this?",
        "step_number": 1,
        "total_steps": 2,
        "next_step_required": True,
        "findings": "Initial review.",
        "models": [{"model": GEMINI, "stance": "neutral"}, {"model": "gemini-3.5-flash", "stance": "neutral"}],
        "relevant_files": files,
    }
    if continuation_id:
        arguments["continuation_id"] = continuation_id
    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply()) as generate:
        await ConsensusTool().execute(arguments)
    return generate


@pytest.mark.asyncio
async def test_consensus_own_text_files_come_before_re_attached_media(tmp_path):
    big, pdf = _big_text_file(tmp_path), _pdf(tmp_path, "a.pdf")
    thread_id, _ = await _chat(tmp_path, files=[pdf])
    with (
        patch("utils.media.estimate_media_tokens", side_effect=_per_media_estimate),
        patch.object(ConsensusTool, "_file_token_budget", return_value=2_500),
    ):
        alone = await _consensus_step_one([big])
        follow_up = await _consensus_step_one([big], continuation_id=thread_id)

    assert "BIG_MARKER_0169" in alone.call_args.kwargs["prompt"]  # control
    prompt = follow_up.call_args.kwargs["prompt"]
    assert "BIG_MARKER_0169" in prompt and "SKIPPED FILES" not in prompt
    assert follow_up.call_args.kwargs.get("media") is None
    assert "[omitted: older a.pdf — over budget]" in prompt


# --- first-turn media no turn recorded (older threads, clink, a workflow without an expert call) -------------------


def _legacy_thread(tmp_path, *paths):
    """A thread whose first turn named ``paths`` but whose turns recorded no media, as stored before 5b."""
    thread_id = create_thread("chat", {"prompt": "look", "absolute_file_paths": list(paths)})
    add_turn(thread_id, "user", "look", files=list(paths))
    add_turn(thread_id, "assistant", "seen", files=list(paths), tool_name="chat")
    return thread_id


@pytest.mark.asyncio
async def test_legacy_first_turn_media_is_re_attached_once(tmp_path):
    pdf = _pdf(tmp_path, "a.pdf")
    thread_id = _legacy_thread(tmp_path, pdf)
    _, generate = await _chat(tmp_path, continuation_id=thread_id)
    assert _names(generate.call_args) == ["a.pdf"]
    assert generate.call_args.kwargs["prompt"].count("--- MEDIA FILE:") == 1


@pytest.mark.asyncio
async def test_legacy_first_turn_media_is_the_oldest_earlier_media(tmp_path):
    first, second = _pdf(tmp_path, "a.pdf"), _pdf(tmp_path, "b.pdf", b"HORSE")
    thread_id = _legacy_thread(tmp_path, first)
    add_turn(thread_id, "assistant", "and b", media=[second], tool_name="chat")
    thread = get_thread(thread_id)
    assert get_conversation_media_list(thread) == [second, first]  # newest first: dropped first when over budget
    assert get_conversation_media_first_seen(thread) == [first, second]  # attached first


def test_first_turn_media_a_turn_recorded_is_not_doubled(tmp_path):
    first, second = _pdf(tmp_path, "a.pdf"), _pdf(tmp_path, "b.pdf", b"HORSE")
    thread_id = create_thread("chat", {"prompt": "look", "absolute_file_paths": [first]})
    add_turn(thread_id, "assistant", "seen", media=[first], tool_name="chat")
    add_turn(thread_id, "assistant", "and b", media=[second], tool_name="chat")
    add_turn(thread_id, "assistant", "a again", media=[first], tool_name="chat")
    thread = get_thread(thread_id)
    assert get_conversation_media_list(thread) == [first, second]
    assert get_conversation_media_first_seen(thread) == [first, second]


@pytest.mark.asyncio
async def test_deleted_legacy_first_turn_media_gets_the_note_and_is_not_read_as_text(tmp_path):
    pdf = _pdf(tmp_path, "report.pdf")
    thread_id = _legacy_thread(tmp_path, pdf)
    os.remove(pdf)
    _, generate = await _chat(tmp_path, continuation_id=thread_id)
    prompt = generate.call_args.kwargs["prompt"]
    assert generate.call_args.kwargs.get("media") is None
    assert "[omitted: earlier report.pdf — file no longer exists]" in prompt
    assert "FILE NOT FOUND" not in prompt


@pytest.mark.asyncio
async def test_media_a_workflow_step_named_without_an_expert_call_is_re_attached(tmp_path):
    # An intermediate analyze step names the PDF but calls no model; a chat follow-up on the thread still sends it
    import server

    pdf = _pdf(tmp_path, "spec.pdf")
    result = await server.handle_call_tool(
        "analyze",
        {
            "step": "Look at the spec",
            "step_number": 1,
            "total_steps": 2,
            "next_step_required": True,
            "findings": "Started.",
            "relevant_files": [pdf],
            "model": GEMINI,
        },
    )
    thread_id = json.loads(result[0].text)["continuation_id"]
    assert get_thread(thread_id).initial_context["relevant_files"] == [pdf]
    assert not any(turn.media for turn in get_thread(thread_id).turns)
    _, generate = await _chat(tmp_path, continuation_id=thread_id)
    assert _names(generate.call_args) == ["spec.pdf"]


# --- history sizing on a follow-up counts the thread's media -------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_follow_up_sizes_history_for_a_model_that_takes_the_threads_pdf(tmp_path):
    # The follow-up names no files, but re-attaches the thread's PDF: the history must be sized for the model auto mode
    # will pick for a PDF (the MCP boundary routes on _call_media_kinds), not for the text-only pick (Grok here)
    import server

    thread_id = create_thread("chat", {"prompt": "look"})
    add_turn(thread_id, "assistant", "seen", media=[PDF], tool_name="chat")  # no model_name: nothing to reuse
    with patch("utils.conversation_memory.build_conversation_history", return_value=("", 0)) as build_history:
        arguments = await server.reconstruct_thread_context(
            {
                "prompt": "And page two?",
                "model": "auto",
                "continuation_id": thread_id,
                "working_directory_absolute_path": str(tmp_path),
            },
            tool_name="chat",
        )
    sized_for = build_history.call_args.args[1]
    assert arguments["_model_context"] is sized_for
    takes = sized_for.capabilities.supported_media_kinds() & frozenset(sized_for.provider.MEDIA_KINDS)
    assert MediaKind.PDF in takes, sized_for.model_name
    assert not ModelProviderRegistry.takes_media_only_when_named(sized_for.provider, sized_for.model_name)


# --- the inline request cap leaves room for the prompt ---------------------------------------------------------------


def _plan_against_cap(tmp_path, cap, **kwargs):
    from utils.media import base64_size, classify_media, plan_media

    own, earlier = _pdf(tmp_path, "own.pdf", b"OWNPD"), _pdf(tmp_path, "old.pdf", b"OLDPD")
    own_media = classify_media([own])[1]
    exact = base64_size(own_media[0].size_bytes) + base64_size(Path(earlier).stat().st_size)
    plan = plan_media(
        own_media,
        [earlier],
        [earlier],
        supported=frozenset({MediaKind.PDF}),
        model_name="m",
        budget_tokens=None,
        model_context=None,
        max_request_bytes=cap(exact),
        **kwargs,
    )
    return plan, exact


def test_media_filling_the_inline_cap_exactly_leaves_room_for_the_prompt(tmp_path):
    # Anthropic's 32 MB counts the prompt and system prompt too: media summing to exactly the cap would be refused
    plan, exact = _plan_against_cap(tmp_path, lambda exact: exact)
    assert [a.name for a in plan.attachments] == ["own.pdf"]
    assert plan.omitted == (f"[omitted: older old.pdf — over the {format_size(exact)} request size limit]",)


def test_the_inline_cap_margin_is_one_megabyte_plus_the_prompt_when_known(tmp_path):
    margin = 1_000_000
    plan, _ = _plan_against_cap(tmp_path, lambda exact: exact + margin + 500, request_text_bytes=500)
    assert [a.name for a in plan.attachments] == ["old.pdf", "own.pdf"]  # exactly what the margin leaves
    plan, _ = _plan_against_cap(tmp_path, lambda exact: exact + margin + 500, request_text_bytes=501)
    assert [a.name for a in plan.attachments] == ["own.pdf"]


def test_the_inline_cap_margin_is_ten_percent_when_the_prompt_is_unknown(tmp_path):
    plan, _ = _plan_against_cap(tmp_path, lambda exact: -(-exact * 10 // 9))  # 90% of it is just over exact
    assert [a.name for a in plan.attachments] == ["old.pdf", "own.pdf"]
    plan, _ = _plan_against_cap(tmp_path, lambda exact: exact * 10 // 9 - 10)
    assert [a.name for a in plan.attachments] == ["own.pdf"]


@pytest.mark.asyncio
async def test_simple_tool_counts_its_prompt_against_the_inline_cap(tmp_path):
    from utils.media import base64_size

    first, second = _pdf(tmp_path, "a.pdf"), _pdf(tmp_path, "b.pdf", b"HORSE")
    thread_id, _ = await _chat(tmp_path, files=[first])
    exact = base64_size(Path(first).stat().st_size) + base64_size(Path(second).stat().st_size)
    with patch.object(OpenAIModelProvider, "MEDIA_REQUEST_MAX_BYTES", exact + 1_000_000 + 64):
        _, generate = await _chat(
            tmp_path, files=[second], model="o3", continuation_id=thread_id, provider_class=OpenAIModelProvider
        )
    # The media fits the cap less 1 MB, but not once the prompt and system prompt (far over 64 bytes) count too
    assert _names(generate.call_args) == ["b.pdf"]
    assert "[omitted: older a.pdf — over the" in generate.call_args.kwargs["prompt"]
