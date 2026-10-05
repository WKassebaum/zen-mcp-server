"""Consensus refuses media any listed model cannot read, before consulting anyone."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.shared import ModelResponse, ProviderType
from tools.consensus import ConsensusTool
from tools.shared.exceptions import ToolExecutionError
from utils.media import MediaKind

PDF = str(Path(__file__).parent / "fixtures" / "media" / "zebra.pdf")
# OpenAI models read PDFs (live-probed 2026-10-03) but no OpenAI encoder takes video, so a video is what
# makes o3 an incapable consensus model in the refusal tests below.
VIDEO = str(Path(__file__).parent / "fixtures" / "media" / "otter.mp4")


# Consensus refuses a roster of fewer than two models, so single-model cases list a second one that step 1 never
# consults (step 1 consults the first model only).
def _step1(models, media=PDF):
    return {
        "step": "Should we ship this spec?",
        "step_number": 1,
        "total_steps": len(models),
        "next_step_required": True,
        "findings": "Initial review of the attached spec.",
        "models": [{"model": m, "stance": "neutral"} for m in models],
        "relevant_files": [media],
    }


@pytest.mark.asyncio
async def test_consensus_preflight_names_incapable_models():
    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)),
        patch.object(GeminiModelProvider, "generate_content") as generate,
    ):
        with pytest.raises(ToolExecutionError) as exc:
            await ConsensusTool().execute(_step1(["gemini-3.8-flash", "o3"], media=VIDEO))
    generate.assert_not_called()  # no model was consulted, not even the capable one
    assert "o3" in str(exc.value)
    assert "gemini-3.8-flash cannot" not in str(exc.value)


@pytest.mark.asyncio
async def test_consensus_sends_media_to_capable_model():
    reply = ModelResponse(content="Ship it.", usage={}, model_name="gemini-3.8-flash", provider=ProviderType.GOOGLE)
    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)),
        patch.object(GeminiModelProvider, "generate_content", return_value=reply) as generate,
    ):
        await ConsensusTool().execute(_step1(["gemini-3.8-flash", "gemini-3.5-flash"]))  # step 1 consults the first
    assert [m.name for m in generate.call_args.kwargs["media"]] == ["zebra.pdf"]
    assert "attached to this request as native pdf input" in generate.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_consensus_preflight_refusal_is_a_readable_tool_error():
    with patch.object(OpenAIModelProvider, "generate_content") as generate:
        with pytest.raises(ToolExecutionError) as exc:
            await ConsensusTool().execute(_step1(["o3", "gemini-3.8-flash"], media=VIDEO))  # Gemini takes video
    generate.assert_not_called()
    payload = json.loads(str(exc.value))
    assert payload["status"] == "error"
    assert payload["content"].startswith("These consensus models cannot take the attached video input: o3.")


@pytest.mark.asyncio
async def test_consult_model_refuses_media_for_an_incapable_model():
    # A later step's model is checked again when consulted; the failure is that model's error entry.
    tool = ConsensusTool()
    tool._current_arguments = {}
    tool.initial_prompt = "Should we ship this spec?"
    request = tool.get_workflow_request_model()(**_step1(["o3"], media=VIDEO))
    with patch.object(OpenAIModelProvider, "generate_content") as generate:
        result = await tool._consult_model({"model": "o3", "stance": "neutral"}, request)
    generate.assert_not_called()
    assert result["status"] == "error"
    assert "cannot take video input (otter.mp4)" in result["error"]


@pytest.mark.asyncio
async def test_consensus_without_media_passes_none(tmp_path):
    notes = tmp_path / "notes.md"
    notes.write_text("# Notes\n")
    reply = ModelResponse(content="Ship it.", usage={}, model_name="gemini-3.8-flash", provider=ProviderType.GOOGLE)
    arguments = _step1(["gemini-3.8-flash", "gemini-3.5-flash"])
    arguments["relevant_files"] = [str(notes)]
    with patch.object(GeminiModelProvider, "generate_content", return_value=reply) as generate:
        await ConsensusTool().execute(arguments)
    assert generate.call_args.kwargs.get("media") is None


@pytest.mark.asyncio
async def test_preflight_leaves_unavailable_models_to_their_usual_error_entry():
    # An unknown model is not a media refusal: it fails when consulted, exactly as it does without media.
    with patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)):
        result = await ConsensusTool().execute(_step1(["no-such-model", "gemini-3.8-flash"]))
    response = json.loads(result[0].text)["model_response"]
    assert response["model"] == "no-such-model" and response["status"] == "error"
    assert "cannot take" not in response["error"]


@pytest.mark.asyncio
async def test_consensus_sends_pdf_to_an_openai_model():
    reply = ModelResponse(content="Ship it.", usage={}, model_name="o3", provider=ProviderType.OPENAI)
    with patch.object(OpenAIModelProvider, "generate_content", return_value=reply) as generate:
        await ConsensusTool().execute(_step1(["o3", "gpt-5.5"]))
    assert [m.name for m in generate.call_args.kwargs["media"]] == ["zebra.pdf"]
