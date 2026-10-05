"""Grok takes media only when a call names it, in consensus too, and an alias never double-books a panel model.

Consensus screens media at step 1, but each later step attaches its own relevant_files. A panel member that an intent
word picked (frontier, fast, balanced, auto) must refuse media on any step when its provider takes media only for a
named model (xAI, and x-ai/* models on OpenRouter), while a Grok model the request names gets it.
Each test registers exactly the providers the MCP server would for Gemini, OpenAI and xAI keys; generate_content
is mocked, so nothing is called.
"""

import json
import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.openrouter import OpenRouterProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ModelResponse, ProviderType
from providers.xai import XAIModelProvider
from tools.consensus import ConsensusTool
from utils.media import MediaKind

PDF = str(Path(__file__).parent / "fixtures" / "media" / "zebra.pdf")


def _clear_providers():
    import utils.model_restrictions

    ModelProviderRegistry.clear_cache()
    for provider_type in list(ProviderType):
        ModelProviderRegistry.unregister_provider(provider_type)
    utils.model_restrictions._restriction_service = None


@pytest.fixture(autouse=True)
def _three_providers():
    from server import configure_providers

    env = dict.fromkeys(("GEMINI_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY"), "test-key")
    with patch.dict(os.environ, env, clear=True):
        _clear_providers()
        configure_providers()
        yield
    _clear_providers()  # conftest's autouse fixture re-registers Google/OpenAI/xAI for later tests


def _recorder(calls, provider_type):
    def generate_content(self, **kwargs):
        calls.append((provider_type, kwargs["model_name"], [a.name for a in kwargs.get("media") or []]))
        return ModelResponse(content="ok", usage={}, model_name=kwargs["model_name"], provider=provider_type)

    return generate_content


async def _run(models, files_from_step=2, files_only_on=None):
    """Run every consensus step; steps from ``files_from_step`` on attach the PDF. Returns (calls, step results)."""
    calls, results = [], []
    tool = ConsensusTool()
    with (
        patch.object(XAIModelProvider, "generate_content", _recorder(calls, ProviderType.XAI)),
        patch.object(GeminiModelProvider, "generate_content", _recorder(calls, ProviderType.GOOGLE)),
        patch.object(OpenAIModelProvider, "generate_content", _recorder(calls, ProviderType.OPENAI)),
    ):
        first = json.loads(
            (
                await tool.execute(
                    {
                        "step": "Ship it?",
                        "step_number": 1,
                        "total_steps": 1,
                        "next_step_required": True,
                        "findings": "x",
                    }
                    | {"models": models}
                )
            )[0].text
        )
        results.append(first)
        total = first["total_steps"]
        thread_id = first["continuation_offer"]["continuation_id"]
        for step in range(2, total + 1):
            arguments = {
                "step": "noted",
                "step_number": step,
                "total_steps": total,
                "next_step_required": step < total,
                "findings": "x",
                "continuation_id": thread_id,
            }
            if (step == files_only_on) if files_only_on is not None else step >= files_from_step:
                arguments["relevant_files"] = [PDF]
            results.append(json.loads((await tool.execute(arguments))[0].text))
    return calls, results, [m["model"] for m in tool.models_to_consult]


@pytest.mark.asyncio
async def test_a_grok_member_picked_by_frontier_never_gets_later_step_media():
    calls, results, roster = await _run(
        [{"model": "frontier", "stance": "for"}, {"model": "frontier", "stance": "against"}]
    )

    assert roster.count("grok-4.7") == 2  # conftest's panel leads with Grok, once per stance
    assert not [call for call in calls if call[0] == ProviderType.XAI and call[2]]
    grok_with_media = [
        r["model_response"] for r in results[1:] if r.get("model_response", {}).get("model") == "grok-4.7"
    ]
    assert grok_with_media and all(response["status"] == "error" for response in grok_with_media)
    assert "name" in grok_with_media[0]["error"].lower()
    # The other members still read the PDF
    assert [call for call in calls if call[0] == ProviderType.GOOGLE and call[2] == ["zebra.pdf"]]


@pytest.mark.asyncio
async def test_a_grok_model_the_request_names_gets_later_step_media():
    calls, _, _ = await _run([{"model": "gemini-3.1-pro-preview"}, {"model": "grok-4.7"}])

    assert (ProviderType.XAI, "grok-4.7", ["zebra.pdf"]) in calls


@pytest.mark.asyncio
async def test_an_alias_and_frontier_do_not_consult_one_model_twice():
    # 'pro' is a Gemini alias of the panel's gemini-3.1-pro-preview
    canonical = ModelProviderRegistry.get_provider_for_model("pro").get_capabilities("pro").model_name
    assert canonical == "gemini-3.1-pro-preview"

    _, _, roster = await _run([{"model": "pro"}, {"model": "frontier"}], files_from_step=99)

    assert roster.count("pro") + roster.count("gemini-3.1-pro-preview") == 1
    assert roster[0] == "pro"  # the named entry stays exactly as named


def test_an_x_ai_openrouter_model_never_gets_auto_routed_media_even_if_flagged():
    provider = OpenRouterProvider(api_key="test-key")
    grok = provider.get_capabilities("x-ai/grok-4.7")
    flagged = replace(grok, supports_pdf=True)
    with patch.object(provider, "get_capabilities", return_value=flagged):
        kept = ModelProviderRegistry._filter_models_for_media(provider, ["x-ai/grok-4.7"], frozenset({MediaKind.PDF}))
    assert kept == []
    assert ModelProviderRegistry.takes_media_only_when_named(provider, "x-ai/grok-4.7")
    # OpenRouter aliases of Grok resolve to x-ai/* models: the guard must see through them
    for alias in ("grok", "grok-4.7", "grok4"):
        assert provider.get_capabilities(alias).model_name.startswith("x-ai/"), alias
        assert ModelProviderRegistry.takes_media_only_when_named(provider, alias), alias
    with patch.object(provider, "get_capabilities", return_value=flagged):
        assert (
            ModelProviderRegistry._filter_models_for_media(provider, ["grok", "grok-4.7"], frozenset({MediaKind.PDF}))
            == []
        )
    assert not ModelProviderRegistry.takes_media_only_when_named(provider, "google/gemini-3.5-flash")


@pytest.mark.asyncio
async def test_a_grok_member_picked_by_frontier_never_gets_re_attached_media():
    # The PDF is attached on step 2 only (to gemini); later steps re-attach it from the thread (phase 5b), and the
    # Grok member's step names no files of its own
    calls, results, roster = await _run(
        [{"model": "frontier", "stance": "for"}, {"model": "frontier", "stance": "against"}], files_only_on=2
    )
    assert roster.count("grok-4.7") == 2
    assert not [call for call in calls if call[0] == ProviderType.XAI and call[2]]
    later_grok = [r["model_response"] for r in results[2:] if r.get("model_response", {}).get("model") == "grok-4.7"]
    assert later_grok and all(response["status"] == "error" for response in later_grok)
    # Not vacuous: members after step 2 that name no files got the PDF re-attached
    assert len([call for call in calls if call[0] != ProviderType.XAI and call[2] == ["zebra.pdf"]]) >= 2
