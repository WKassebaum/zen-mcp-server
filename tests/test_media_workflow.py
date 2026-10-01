"""Workflow tools validate media on every step and send it with the expert analysis call."""

import json
import re
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.shared import ModelResponse, ProviderType
from tools.analyze import AnalyzeTool
from tools.codereview import CodeReviewTool
from tools.debug import DebugIssueTool
from tools.shared.base_models import WorkflowRequest
from tools.shared.exceptions import ToolExecutionError
from tools.thinkdeep import ThinkDeepTool
from utils.media import MediaKind, media_kinds_from_arguments
from utils.model_context import ModelContext

FIXTURES = Path(__file__).parent / "fixtures" / "media"
MP4 = str(FIXTURES / "otter.mp4")
PDF = str(FIXTURES / "zebra.pdf")


def _args(model, context, next_step_required=False, step_number=1, total_steps=1, relevant_files=(MP4,)):
    return {
        "step": "Analyze the recording",
        "step_number": step_number,
        "total_steps": total_steps,
        "next_step_required": next_step_required,
        "findings": "Recording shows a banner.",
        "relevant_files": list(relevant_files),
        "model": model,
        "_model_context": context,
        "_resolved_model_name": model,
    }


def _gemini_reply():
    return ModelResponse(
        content='{"status": "analysis_complete"}', usage={}, model_name="gemini-3.8-flash", provider=ProviderType.GOOGLE
    )


def _announced(prompt: str) -> list[str]:
    """Media paths announced in the prompt (utils.media.media_prompt_section), in order."""
    return re.findall(r"--- MEDIA FILE: (.+?) \((?:pdf|audio|video), ", prompt)


@pytest.fixture
def gemini_encodes_media():
    # The Gemini encoder arrives in Task 15; until then pretend it exists.
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        yield


@pytest.mark.asyncio
async def test_expert_analysis_receives_media(gemini_encodes_media):
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await AnalyzeTool().execute(_args("gemini-3.8-flash", ModelContext("gemini-3.8-flash")))
    assert [m.name for m in generate.call_args.kwargs["media"]] == ["otter.mp4"]
    assert "attached to this request as native video input" in generate.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_workflow_rejects_incapable_model_before_expert_call():
    with patch("providers.registry.ModelProviderRegistry.find_media_capable_models", return_value=["gemini-3.8-flash"]):
        with pytest.raises(ToolExecutionError, match="cannot take video"):
            await AnalyzeTool().execute(_args("o3", ModelContext("o3")))


@pytest.mark.asyncio
async def test_intermediate_step_rejects_incapable_model():
    # Step 1 of 3 embeds no files and calls no model, but must still refuse media the model cannot read.
    with patch.object(OpenAIModelProvider, "generate_content") as generate:
        with pytest.raises(ToolExecutionError, match="cannot take video"):
            await AnalyzeTool().execute(_args("o3", ModelContext("o3"), next_step_required=True, total_steps=3))
    generate.assert_not_called()


@pytest.mark.asyncio
async def test_cli_auto_mode_without_capable_provider_reports_media_hint():
    # CLI mode: no _model_context, model "auto", and no provider that can encode video.
    arguments = {
        "step": "Review the screen recording",
        "step_number": 1,
        "total_steps": 1,
        "next_step_required": False,
        "findings": "Initial review request from CLI",
        "relevant_files": [MP4],
        "files_checked": [MP4],
        "review_type": "full",
        "model": "auto",
    }
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset()):
        with pytest.raises(ToolExecutionError) as exc:
            await CodeReviewTool().execute(arguments)
    content = json.loads(str(exc.value))["content"]
    assert "No available model can take video input" in content and "GEMINI_API_KEY" in content
    assert "Model 'auto' is not available" not in content


@pytest.mark.asyncio
async def test_two_step_mcp_workflow_in_auto_mode_keeps_step_one_media(tmp_path, gemini_encodes_media):
    import server

    code = tmp_path / "app.py"
    code.write_text("print('hi')\n")
    step = {"total_steps": 2, "findings": "Banner text visible", "model": "auto"}
    first = await server.handle_call_tool(
        "analyze",
        {
            **step,
            "step": "Analyze the recording",
            "step_number": 1,
            "next_step_required": True,
            "relevant_files": [MP4, str(code)],
        },
    )
    thread_id = json.loads(first[0].text)["continuation_id"]
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await server.handle_call_tool(
            "analyze",
            {
                **step,
                "step": "Final step",
                "step_number": 2,
                "next_step_required": False,
                "relevant_files": [str(code)],
                "continuation_id": thread_id,
            },
        )
    assert [m.name for m in generate.call_args.kwargs["media"]] == ["otter.mp4"]


def test_bare_string_file_fields_are_wrapped_not_dropped():
    request = WorkflowRequest(
        step="s",
        step_number=1,
        total_steps=1,
        next_step_required=False,
        findings="f",
        relevant_files=MP4,
        files_checked=MP4,
        relevant_context="Thing.method",
    )
    assert request.relevant_files == [MP4]
    assert request.files_checked == [MP4]
    assert request.relevant_context == ["Thing.method"]


def test_empty_string_file_field_is_an_empty_list():
    request = WorkflowRequest(
        step="s", step_number=1, total_steps=1, next_step_required=False, findings="f", relevant_files=""
    )
    assert request.relevant_files == []


def test_auto_mode_routing_sees_a_bare_string_path():
    # server.py routes auto mode on raw arguments, before the request model wraps the string
    assert media_kinds_from_arguments({"relevant_files": MP4}) == frozenset({MediaKind.VIDEO})


@pytest.mark.asyncio
async def test_bare_string_relevant_files_reaches_media_validation():
    arguments = _args("o3", ModelContext("o3"))
    arguments["relevant_files"] = MP4  # a bare string, not a list
    with patch.object(OpenAIModelProvider, "generate_content") as generate:
        with pytest.raises(ToolExecutionError, match="cannot take video"):
            await AnalyzeTool().execute(arguments)
    generate.assert_not_called()


@pytest.mark.asyncio
async def test_expert_announces_media_in_the_order_it_is_attached(tmp_path, gemini_encodes_media):
    # relevant_files are consolidated in a set: the announcement and the attachment list must be built
    # from the same order, or "attachment N of M" points at the wrong part.
    clips = []
    for name in ("e.mp4", "a.pdf", "d.mp4", "b.pdf", "c.mp4"):
        shutil.copy(MP4 if name.endswith(".mp4") else PDF, tmp_path / name)
        clips.append(str(tmp_path / name))
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await AnalyzeTool().execute(_args("gemini-3.8-flash", ModelContext("gemini-3.8-flash"), relevant_files=clips))
    attached = [m.path for m in generate.call_args.kwargs["media"]]
    assert sorted(attached) == sorted(clips)
    assert _announced(generate.call_args.kwargs["prompt"]) == attached


@pytest.mark.asyncio
async def test_debug_expert_call_attaches_and_announces_media_once(tmp_path, gemini_encodes_media):
    # debug builds its own expert context (prepare_expert_analysis_context -> _prepare_file_content_for_prompt)
    clips = []
    for name in ("z.mp4", "m.pdf", "a.mp4"):
        shutil.copy(MP4 if name.endswith(".mp4") else PDF, tmp_path / name)
        clips.append(str(tmp_path / name))
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await DebugIssueTool().execute(
            _args("gemini-3.8-flash", ModelContext("gemini-3.8-flash"), relevant_files=clips)
        )
    attached = [m.path for m in generate.call_args.kwargs["media"]]
    assert sorted(attached) == sorted(clips)
    assert _announced(generate.call_args.kwargs["prompt"]) == attached


@pytest.mark.asyncio
async def test_debug_rejects_incapable_model_before_any_call():
    with patch.object(OpenAIModelProvider, "generate_content") as generate:
        with pytest.raises(ToolExecutionError, match="cannot take video"):
            await DebugIssueTool().execute(_args("o3", ModelContext("o3")))
    generate.assert_not_called()


@pytest.mark.asyncio
async def test_tool_without_files_in_expert_prompt_still_announces_attached_media(gemini_encodes_media):
    # thinkdeep never embeds files in its expert prompt; media it attaches must still be announced.
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await ThinkDeepTool().execute(_args("gemini-3.8-flash", ModelContext("gemini-3.8-flash")))
    assert [m.name for m in generate.call_args.kwargs["media"]] == ["otter.mp4"]
    assert _announced(generate.call_args.kwargs["prompt"]) == [MP4]


@pytest.mark.asyncio
async def test_expert_call_without_media_passes_none(tmp_path):
    code = tmp_path / "app.py"
    code.write_text("print('hi')\n")
    with patch.object(GeminiModelProvider, "generate_content", return_value=_gemini_reply()) as generate:
        await AnalyzeTool().execute(
            _args("gemini-3.8-flash", ModelContext("gemini-3.8-flash"), relevant_files=[str(code)])
        )
    assert generate.call_args.kwargs.get("media") is None
    assert _announced(generate.call_args.kwargs["prompt"]) == []


@pytest.mark.asyncio
async def test_request_that_calls_no_model_is_not_refused():
    # use_assistant_model=False: no expert call, so nothing is sent and there is nothing to refuse
    arguments = _args("o3", ModelContext("o3"))
    arguments["use_assistant_model"] = False
    with patch.object(OpenAIModelProvider, "generate_content") as generate:
        result = await AnalyzeTool().execute(arguments)
    generate.assert_not_called()
    assert json.loads(result[0].text)["status"] != "error"
