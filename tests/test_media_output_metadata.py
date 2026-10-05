"""What was attached, how it travelled, and xAI's paid search reach the tool output (MCP and the CLI's --json)."""

import json
import logging
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ModelResponse, ProviderType
from providers.xai import XAIModelProvider
from tools.chat import ChatTool
from tools.consensus import ConsensusTool
from tools.thinkdeep import ThinkDeepTool
from utils.media import MediaKind, classify_media
from utils.model_context import ModelContext

FIXTURES = Path(__file__).parent / "fixtures" / "media"
MP4 = str(FIXTURES / "otter.mp4")
PDF = str(FIXTURES / "zebra.pdf")
GEMINI = "gemini-3.8-flash"
GROK = "grok-4.7"

UPLOADED = {"name": "otter.mp4", "kind": "video", "bytes": 7_939, "transport": "uploaded", "file_name": "files/abc"}
CACHED = {**UPLOADED, "transport": "cached"}
INLINE = {"name": "zebra.pdf", "kind": "pdf", "bytes": 587, "transport": "inline"}
UPLOAD_NOTICE = "Uploaded to the Gemini Files API: files/abc (otter.mp4); Google deletes uploads after 48 h."
SEARCH_NOTICE = f"xAI ran 2 server-side search call(s) for {GROK}; billed separately ($5 per 1,000)"


@pytest.fixture(autouse=True)
def providers_available(monkeypatch):
    # Earlier tests in the suite can leave the registry without these providers
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key-for-tests")
    monkeypatch.setenv("XAI_API_KEY", "dummy-key-for-tests")
    ModelProviderRegistry.reset_for_testing()
    ModelProviderRegistry.register_provider(ProviderType.GOOGLE, GeminiModelProvider)
    ModelProviderRegistry.register_provider(ProviderType.XAI, XAIModelProvider)
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        yield


def _reply(content="Otter.", attached=None, model=GEMINI, provider=ProviderType.GOOGLE, **metadata):
    if attached is not None:
        metadata["media_attached"] = attached
    return ModelResponse(content=content, usage={}, model_name=model, provider=provider, metadata=metadata)


def _model_args(model=GEMINI):
    return {"model": model, "_model_context": ModelContext(model), "_resolved_model_name": model}


async def _chat(tmp_path, reply, files=(MP4,), model=GEMINI, provider_class=GeminiModelProvider):
    with patch.object(provider_class, "generate_content", return_value=reply):
        result = await ChatTool().execute(
            {
                "prompt": "What is shown?",
                "absolute_file_paths": list(files),
                "working_directory_absolute_path": str(tmp_path),
                **_model_args(model),
            }
        )
    return json.loads(result[0].text)["metadata"]


# --- simple tools -------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("record", [UPLOADED, CACHED], ids=["uploaded", "cached"])
async def test_simple_tool_shows_media_and_the_upload_notice(tmp_path, record):
    metadata = await _chat(tmp_path, _reply(attached=[record]))
    assert metadata["model_used"] == GEMINI and metadata["provider_used"] == "google"
    assert metadata["media_attached"] == [record]
    assert metadata["media_attached"][0]["file_name"] == "files/abc"
    assert metadata["media_notice"] == UPLOAD_NOTICE


@pytest.mark.asyncio
async def test_simple_tool_without_a_continuation_offer_shows_them_too(tmp_path):
    with patch.object(ChatTool, "_create_continuation_offer", return_value=None):
        metadata = await _chat(tmp_path, _reply(attached=[UPLOADED]))
    assert metadata["media_attached"] == [UPLOADED]
    assert metadata["media_notice"] == UPLOAD_NOTICE


@pytest.mark.asyncio
async def test_inline_media_is_listed_without_a_notice(tmp_path):
    metadata = await _chat(tmp_path, _reply(attached=[INLINE]), files=(PDF,))
    assert metadata["media_attached"] == [INLINE]
    assert "media_notice" not in metadata


@pytest.mark.asyncio
async def test_no_media_adds_no_fields(tmp_path):
    metadata = await _chat(tmp_path, _reply(attached=[]), files=())  # Gemini always reports a (maybe empty) list
    assert "media_attached" not in metadata and "media_notice" not in metadata


# --- workflow and consensus ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ['{"status": "analysis_complete", "summary": "Otter."}', "Plain-text analysis."])
async def test_workflow_expert_analysis_carries_media(tmp_path, content):
    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply(content, attached=[UPLOADED])):
        result = await ThinkDeepTool().execute(
            {
                "step": "What does the clip show?",
                "step_number": 1,
                "total_steps": 1,
                "next_step_required": False,
                "findings": "An otter, probably.",
                "relevant_files": [MP4],
                **_model_args(),
            }
        )
    expert = json.loads(result[0].text)["expert_analysis"]
    assert expert["metadata"]["media_attached"] == [UPLOADED]
    assert expert["metadata"]["media_notice"] == UPLOAD_NOTICE


@pytest.mark.asyncio
async def test_consensus_model_response_carries_media():
    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply("Ship it.", attached=[UPLOADED])):
        result = await ConsensusTool().execute(
            {
                "step": "Is this the right clip?",
                "step_number": 1,
                "total_steps": 1,
                "next_step_required": False,
                "findings": "Initial look.",
                # Consensus needs two models; step 1 consults only the first
                "models": [{"model": GEMINI, "stance": "for"}, {"model": GEMINI, "stance": "against"}],
                "relevant_files": [MP4],
            }
        )
    response_metadata = json.loads(result[0].text)["model_response"]["metadata"]
    assert response_metadata["provider"] == "google" and response_metadata["model_name"] == GEMINI
    assert response_metadata["media_attached"] == [UPLOADED]
    assert response_metadata["media_notice"] == UPLOAD_NOTICE


# --- earlier media left out of a follow-up ---------------------------------------------------------------------------

GONE_NOTICE = "Not re-sent: gone.pdf (file no longer exists)"


def _thread_with_deleted_pdf(tmp_path):
    """A thread whose earlier turn attached gone.pdf, since deleted: every follow-up leaves it out with a note."""
    from utils.conversation_memory import add_turn, create_thread

    gone = tmp_path / "gone.pdf"
    gone.write_bytes(Path(PDF).read_bytes())
    thread_id = create_thread("chat", {"prompt": "look"})
    add_turn(thread_id, "assistant", "seen", media=[str(gone)], tool_name="chat")
    gone.unlink()
    return thread_id


@pytest.mark.asyncio
@pytest.mark.parametrize("offer", [True, False], ids=["continuation-offer", "no-offer"])
async def test_simple_tool_reports_media_left_out(tmp_path, offer):
    thread_id = _thread_with_deleted_pdf(tmp_path)
    with (
        patch.object(GeminiModelProvider, "generate_content", return_value=_reply()),
        patch.object(ChatTool, "_create_continuation_offer", return_value=None) if not offer else nullcontext(),
    ):
        result = await ChatTool().execute(
            {
                "prompt": "And now?",
                "continuation_id": thread_id,
                "working_directory_absolute_path": str(tmp_path),
                **_model_args(),
            }
        )
    metadata = json.loads(result[0].text)["metadata"]
    assert metadata["media_omitted"] == [{"name": "gone.pdf", "reason": "file no longer exists"}]
    assert metadata["media_notice"] == GONE_NOTICE


@pytest.mark.asyncio
async def test_media_left_out_is_appended_to_an_existing_notice(tmp_path):
    thread_id = _thread_with_deleted_pdf(tmp_path)
    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply(attached=[UPLOADED])):
        result = await ChatTool().execute(
            {
                "prompt": "And this clip?",
                "absolute_file_paths": [MP4],
                "continuation_id": thread_id,
                "working_directory_absolute_path": str(tmp_path),
                **_model_args(),
            }
        )
    metadata = json.loads(result[0].text)["metadata"]
    assert metadata["media_notice"] == f"{UPLOAD_NOTICE}\n{GONE_NOTICE}"


@pytest.mark.asyncio
async def test_nothing_left_out_adds_no_fields(tmp_path):
    metadata = await _chat(tmp_path, _reply(attached=[INLINE]), files=(PDF,))
    assert "media_omitted" not in metadata and "media_notice" not in metadata


@pytest.mark.asyncio
async def test_workflow_expert_analysis_reports_media_left_out(tmp_path):
    thread_id = _thread_with_deleted_pdf(tmp_path)
    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply('{"status": "analysis_complete"}')):
        result = await ThinkDeepTool().execute(
            {
                "step": "What changed?",
                "step_number": 1,
                "total_steps": 1,
                "next_step_required": False,
                "findings": "Nothing yet.",
                "continuation_id": thread_id,
                **_model_args(),
            }
        )
    expert = json.loads(result[0].text)["expert_analysis"]
    assert expert["metadata"]["media_omitted"] == [{"name": "gone.pdf", "reason": "file no longer exists"}]
    assert expert["metadata"]["media_notice"] == GONE_NOTICE


@pytest.mark.asyncio
async def test_consensus_model_response_reports_media_left_out(tmp_path):
    thread_id = _thread_with_deleted_pdf(tmp_path)
    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply("Ship it.")):
        result = await ConsensusTool().execute(
            {
                "step": "Ship it?",
                "step_number": 1,
                "total_steps": 2,
                "next_step_required": True,
                "findings": "Initial look.",
                "models": [{"model": GEMINI, "stance": "for"}, {"model": GEMINI, "stance": "against"}],
                "continuation_id": thread_id,
            }
        )
    response_metadata = json.loads(result[0].text)["model_response"]["metadata"]
    assert response_metadata["media_omitted"] == [{"name": "gone.pdf", "reason": "file no longer exists"}]
    assert response_metadata["media_notice"] == GONE_NOTICE


def test_cli_prints_the_media_left_out_notice():
    payload = {"content": "Answer.", "model_response": {"metadata": {"media_notice": GONE_NOTICE}}}
    assert GONE_NOTICE in _human("print_media_notices", payload)


# --- xAI server-side search ---------------------------------------------------------------------------------------


def _xai_provider(server_side_calls):
    provider = XAIModelProvider("test-key")
    provider._client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(
                output_text="ZEBRA-42",
                usage=SimpleNamespace(
                    input_tokens=1_775,
                    output_tokens=2,
                    total_tokens=1_777,
                    num_server_side_tools_used=server_side_calls,
                ),
            )
        )
    )
    return provider


def test_xai_search_calls_log_a_warning(caplog):
    with caplog.at_level(logging.WARNING):
        response = _xai_provider(2).generate_content("What code?", GROK, media=classify_media([PDF])[1])
    assert response.metadata["server_side_tool_calls"] == 2
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING] == [SEARCH_NOTICE]


def test_no_xai_search_calls_log_nothing(caplog):
    with caplog.at_level(logging.WARNING):
        response = _xai_provider(0).generate_content("What code?", GROK, media=classify_media([PDF])[1])
    assert response.metadata["server_side_tool_calls"] == 0
    assert "server-side search" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("calls, notice", [(2, SEARCH_NOTICE), (0, None)])
async def test_xai_search_calls_reach_the_tool_output(tmp_path, calls, notice):
    reply = _reply("ZEBRA-42", model=GROK, provider=ProviderType.XAI, server_side_tool_calls=calls)
    metadata = await _chat(tmp_path, reply, files=(), model=GROK, provider_class=XAIModelProvider)
    assert metadata["server_side_tool_calls"] == calls
    assert metadata.get("media_notice") == notice


@pytest.mark.asyncio
async def test_search_calls_from_another_provider_add_no_notice(tmp_path):
    metadata = await _chat(tmp_path, _reply(server_side_tool_calls=3), files=())  # a Gemini reply
    assert metadata["server_side_tool_calls"] == 3
    assert "media_notice" not in metadata


# --- the CLI ------------------------------------------------------------------------------------------------------


def _human(printer, *args):
    from rich.console import Console

    from zen_cli import main as cli_main

    buffer = Console(record=True, force_terminal=False, width=200)
    original = cli_main.console
    cli_main.console = buffer
    try:
        getattr(cli_main, printer)(*args)
    finally:
        cli_main.console = original
    return buffer.export_text()


class _Text:
    def __init__(self, payload):
        self.text = json.dumps(payload)


def test_cli_prints_the_notice_after_the_answer():
    payload = {"status": "success", "content": "An otter [swimming].", "metadata": {"media_notice": UPLOAD_NOTICE}}
    output = _human("print_result_human", [_Text(payload)])
    assert output.index("An otter") < output.index(UPLOAD_NOTICE)


def test_cli_prints_a_workflow_expert_notice():
    result = {"content": "Step done.", "expert_analysis": {"metadata": {"media_notice": UPLOAD_NOTICE}}}
    output = _human("_present_workflow_step", result, "s1", "thinkdeep")
    assert output.index("Step done.") < output.index(UPLOAD_NOTICE)


def test_cli_notice_is_dimmed():
    from zen_cli import main as cli_main

    payload = {"content": "Answer.", "metadata": {"media_notice": "Notice with [brackets]"}}
    with patch.object(cli_main.console, "print") as printed:
        cli_main.print_result_human([_Text(payload)])
    notice_call = printed.call_args_list[-1]
    renderable = notice_call.args[0]
    assert str(renderable) == "Notice with [brackets]"  # printed as text, not parsed as markup
    assert renderable.style == "dim"
