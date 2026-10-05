"""Intent words: 'frontier', 'balanced' and 'fast' stand for a pick, as 'auto' does. Any other name is a model,
used exactly as named: it never reaches the resolver.

Providers are registered on dummy keys and no provider is called.
"""

import json
import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.registry import INTENT_MODELS, ModelProviderRegistry
from providers.shared import ProviderType
from tools.chat import ChatTool
from tools.models import ToolModelCategory
from tools.shared.exceptions import ToolExecutionError
from utils.conversation_memory import add_turn, create_thread
from utils.media import MediaKind, MediaNotSupportedError

EXTENDED = ToolModelCategory.EXTENDED_REASONING
BALANCED = ToolModelCategory.BALANCED
FAST = ToolModelCategory.FAST_RESPONSE

CONF_DIR = Path(__file__).resolve().parent.parent / "conf"
PDF_ONLY = frozenset({MediaKind.PDF})
THREE_KEYS = {"GEMINI_API_KEY": "test-key", "OPENAI_API_KEY": "test-key", "XAI_API_KEY": "test-key"}


def _clear_providers():
    import utils.model_restrictions

    ModelProviderRegistry.clear_cache()
    for provider_type in list(ProviderType):
        ModelProviderRegistry.unregister_provider(provider_type)
    utils.model_restrictions._restriction_service = None


@contextmanager
def _configured(env: dict[str, str]):
    """Register exactly the providers the MCP server would for ``env``."""
    from server import configure_providers

    with patch.dict(os.environ, env, clear=True):
        _clear_providers()
        configure_providers()
        try:
            yield
        finally:
            _clear_providers()  # conftest's autouse fixture re-registers Google/OpenAI/xAI for later tests


def _rank(model_name: str) -> int:
    provider = ModelProviderRegistry.get_provider_for_model(model_name)
    return provider.get_capabilities(model_name).get_effective_capability_rank()


def _provider_type(model_name: str) -> ProviderType:
    return ModelProviderRegistry.get_provider_for_model(model_name).get_provider_type()


# ---------------------------------------------------------------------------
# The words
# ---------------------------------------------------------------------------


def test_no_catalog_name_or_alias_is_an_intent_word():
    words = {"auto", *INTENT_MODELS}
    checked = 0
    for path in sorted(CONF_DIR.glob("*_models.json")):
        for entry in json.loads(path.read_text()).get("models", []):
            names = {entry["model_name"].lower(), *(alias.lower() for alias in entry.get("aliases", []))}
            assert not names & words, f"{path.name}: {entry['model_name']} uses {names & words}"
            checked += 1
    assert checked > 100  # every catalog was read


def test_intent_words_are_case_insensitive_and_nothing_else_is_one():
    assert INTENT_MODELS == ("frontier", "balanced", "fast")
    for word in ("frontier", "FRONTIER", "Balanced", "fast", " fast ", "auto", "AUTO"):
        assert ModelProviderRegistry.is_model_intent(word), word
    for name in ("gemini-2.5-flash", "flash", "pro", "frontier-1", "", None):
        assert not ModelProviderRegistry.is_model_intent(name), name
        assert ModelProviderRegistry.resolve_model_intent(name, BALANCED) is None, name


# ---------------------------------------------------------------------------
# The resolver
# ---------------------------------------------------------------------------


def test_frontier_is_the_top_ranked_model_across_providers():
    with _configured(THREE_KEYS):
        model = ModelProviderRegistry.resolve_model_intent("frontier", FAST)
        capabilities = ModelProviderRegistry.get_provider_for_model(model).get_capabilities(model)
        assert capabilities.intelligence_score == 20
        assert capabilities.get_effective_capability_rank() == 111
        available = ModelProviderRegistry.get_available_models(respect_restrictions=True)
        assert _rank(model) == max(_rank(name) for name in available)
        # gpt-6-astra and gpt-6-sol tie at 111: the canonical name breaks it, and a premium model may win
        assert model == "gpt-6-astra"
        assert ModelProviderRegistry.resolve_model_intent("Frontier", BALANCED) == model


def test_fast_and_balanced_take_their_own_category_whatever_the_tool():
    with _configured(THREE_KEYS):
        for tool_category in ToolModelCategory:
            fast = ModelProviderRegistry.resolve_model_intent("fast", tool_category)
            balanced = ModelProviderRegistry.resolve_model_intent("balanced", tool_category)
            assert fast == ModelProviderRegistry.get_preferred_fallback_model(FAST)
            assert balanced == ModelProviderRegistry.get_preferred_fallback_model(BALANCED)


def test_each_word_picks_differently_where_the_categories_differ():
    # OpenAI alone has a different pick per category, so this shows each word uses its own.
    with _configured({"OPENAI_API_KEY": "test-key"}):
        assert ModelProviderRegistry.resolve_model_intent("frontier", FAST) == "gpt-6-astra"
        assert ModelProviderRegistry.resolve_model_intent("balanced", FAST) == "gpt-6-sol"
        assert ModelProviderRegistry.resolve_model_intent("fast", EXTENDED) == "gpt-6-luna"
        for tool_category in ToolModelCategory:
            assert ModelProviderRegistry.resolve_model_intent(
                "auto", tool_category
            ) == ModelProviderRegistry.get_preferred_fallback_model(tool_category)


def test_frontier_ties_break_by_provider_priority():
    # gpt-5.4 and gemini-3.5-flash both rank 106 and grok-4.6 105: Google comes before OpenAI.
    env = {
        **THREE_KEYS,
        "OPENAI_ALLOWED_MODELS": "gpt-5.4",
        "GOOGLE_ALLOWED_MODELS": "gemini-3.5-flash",
        "XAI_ALLOWED_MODELS": "grok-4.6",
    }
    with _configured(env):
        assert _rank("gpt-5.4") == _rank("gemini-3.5-flash") > _rank("grok-4.6")
        assert ModelProviderRegistry.resolve_model_intent("frontier", BALANCED) == "gemini-3.5-flash"


def test_an_allow_list_limits_frontier():
    with _configured({**THREE_KEYS, "OPENAI_ALLOWED_MODELS": "gpt-6-luna,o3"}):
        model = ModelProviderRegistry.resolve_model_intent("frontier", BALANCED)
    assert model not in ("gpt-6-astra", "gpt-6-sol")
    assert model == "grok-4.7"  # 110: the best model left once OpenAI's 111s are not allowed


def test_no_intent_word_sends_a_pdf_to_grok():
    # Gemini and OpenAI are held below Grok, so Grok tops the text pick for every word.
    env = {**THREE_KEYS, "GOOGLE_ALLOWED_MODELS": "gemini-3.8-flash", "OPENAI_ALLOWED_MODELS": "gpt-5.5"}
    with _configured(env):
        grok = ModelProviderRegistry.get_provider(ProviderType.XAI)
        assert MediaKind.PDF in grok.get_capabilities("grok-4.7").supported_media_kinds()  # flagged, yet excluded
        for word in ("frontier", "balanced", "fast", "auto"):
            assert _provider_type(ModelProviderRegistry.resolve_model_intent(word, BALANCED)) == ProviderType.XAI
            model = ModelProviderRegistry.resolve_model_intent(word, BALANCED, required_media=PDF_ONLY)
            provider = ModelProviderRegistry.get_provider_for_model(model)
            assert provider.get_provider_type() != ProviderType.XAI, (word, model)
            assert MediaKind.PDF in provider.get_capabilities(model).supported_media_kinds()


def test_frontier_refuses_media_no_model_can_take():
    with _configured(THREE_KEYS), patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset()):
        with pytest.raises(MediaNotSupportedError, match="No available model can take video input"):
            ModelProviderRegistry.resolve_model_intent("frontier", BALANCED, required_media={MediaKind.VIDEO})


# ---------------------------------------------------------------------------
# MCP boundary and CLI path
# ---------------------------------------------------------------------------


async def _run_chat(tmp_path, **arguments) -> dict:
    """Arguments ChatTool.execute receives after the MCP boundary resolved the model."""
    import server

    with patch.object(ChatTool, "execute", return_value=[]) as execute:
        await server.handle_call_tool(
            "chat", {"prompt": "hi", "working_directory_absolute_path": str(tmp_path), **arguments}
        )
    execute.assert_called_once()
    return execute.call_args[0][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("word", ["frontier", "Frontier", "balanced", "fast"])
async def test_mcp_boundary_runs_an_intent_word_on_the_resolved_model(tmp_path, word, caplog):
    expected = ModelProviderRegistry.resolve_model_intent(word, ChatTool().get_model_category())
    assert expected and not ModelProviderRegistry.is_model_intent(expected)
    with caplog.at_level("INFO", logger="server"):
        arguments = await _run_chat(tmp_path, model=word)
    assert arguments["model"] == expected
    assert arguments["_resolved_model_name"] == expected
    assert arguments["_model_context"].model_name == expected
    assert f"{word.lower()} resolved to {expected}" in caplog.text


@pytest.mark.asyncio
async def test_mcp_boundary_frontier_is_the_flagship(tmp_path):
    arguments = await _run_chat(tmp_path, model="frontier")
    assert arguments["_resolved_model_name"] == "gpt-6-astra"  # conftest keys: Gemini, OpenAI, xAI


def test_cli_path_resolves_an_intent_word():
    tool = ChatTool()
    request = tool.get_request_model()(prompt="hi", working_directory_absolute_path="/tmp", model="frontier")
    model_name, model_context = tool._resolve_model_context({"model": "frontier"}, request)
    assert model_name == model_context.model_name == "gpt-6-astra"


# ---------------------------------------------------------------------------
# A named model is used exactly as named
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("named", ["gemini-2.5-flash", "flash", "gpt-6-sol", "grok-4.7"])
async def test_a_named_model_never_goes_through_the_resolver(tmp_path, named):
    refuse = AssertionError("a named model reached the resolver")
    with (
        patch.object(ModelProviderRegistry, "resolve_model_intent", side_effect=refuse) as resolver,
        patch.object(ModelProviderRegistry, "get_preferred_fallback_model", side_effect=refuse) as fallback,
    ):
        arguments = await _run_chat(tmp_path, model=named)
        tool = ChatTool()
        request = tool.get_request_model()(prompt="hi", working_directory_absolute_path="/tmp", model=named)
        cli_name, cli_context = tool._resolve_model_context({"model": named}, request)
    resolver.assert_not_called()
    fallback.assert_not_called()
    assert arguments["model"] == arguments["_resolved_model_name"] == named
    assert arguments["_model_context"].model_name == named
    assert cli_name == cli_context.model_name == named


@pytest.mark.asyncio
async def test_an_unavailable_named_model_is_refused_not_swapped(tmp_path):
    import server

    with (
        patch.object(ModelProviderRegistry, "resolve_model_intent") as resolver,
        patch.object(ChatTool, "execute", return_value=[]) as execute,
    ):
        with pytest.raises(ToolExecutionError) as exc:
            await server.handle_call_tool(
                "chat",
                {"prompt": "hi", "model": "claude-opus-5-5", "working_directory_absolute_path": str(tmp_path)},
            )
    resolver.assert_not_called()
    execute.assert_not_called()
    payload = json.loads(str(exc.value))
    assert payload["metadata"]["requested_model"] == "claude-opus-5-5"
    assert "Model 'claude-opus-5-5' is not available" in payload["content"]


# ---------------------------------------------------------------------------
# Follow-ups
# ---------------------------------------------------------------------------


def _thread_answered_by(model_name: str) -> str:
    thread_id = create_thread("chat", {"prompt": "earlier question"})
    add_turn(thread_id, "assistant", "earlier answer", tool_name="chat", model_name=model_name)
    return thread_id


@pytest.mark.asyncio
async def test_a_follow_up_with_an_intent_word_resolves_fresh(tmp_path):
    expected = ModelProviderRegistry.resolve_model_intent("fast", FAST)
    assert expected != "gemini-2.5-flash"
    arguments = await _run_chat(tmp_path, model="fast", continuation_id=_thread_answered_by("gemini-2.5-flash"))
    assert arguments["_resolved_model_name"] == expected


@pytest.mark.asyncio
async def test_a_follow_up_without_a_model_still_reuses_the_previous_one(tmp_path):
    arguments = await _run_chat(tmp_path, continuation_id=_thread_answered_by("gemini-2.5-flash"))
    assert arguments["_resolved_model_name"] == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_a_follow_up_sizes_its_history_for_the_resolved_model(tmp_path):
    # chat is FAST_RESPONSE (grok-4.7 here); frontier is gpt-6-astra, whose window the history must fit.
    import server

    thread_id = _thread_answered_by("gemini-2.5-flash")
    with patch("utils.conversation_memory.build_conversation_history", return_value=("", 0)) as build_history:
        await server.reconstruct_thread_context(
            {
                "prompt": "next",
                "model": "frontier",
                "continuation_id": thread_id,
                "working_directory_absolute_path": "/tmp",
            }
        )
    assert build_history.call_args[0][1].model_name == "gpt-6-astra"


# ---------------------------------------------------------------------------
# Where the words are announced
# ---------------------------------------------------------------------------

INTENT_SENTENCE = "Or an intent: 'frontier' (best available), 'balanced', 'fast'; 'auto' picks per tool."


@pytest.mark.parametrize("auto_mode", [True, False])
def test_the_model_field_announces_the_intent_words(auto_mode):
    tool = ChatTool()
    with patch.object(ChatTool, "is_effective_auto_mode", return_value=auto_mode):
        description = tool.get_model_field_schema()["description"]
    assert INTENT_SENTENCE in description
    assert "exact name" in description  # named models are still used as named


@pytest.mark.asyncio
async def test_listmodels_lists_the_intent_words():
    from tools.listmodels import ListModelsTool

    result = await ListModelsTool().execute({})
    content = json.loads(result[0].text)["content"]
    header, intent_line = [line for line in content.splitlines() if line.strip()][:2]
    assert header == "# Available AI Models"
    for word in ("`frontier`", "`balanced`", "`fast`", "`auto`"):
        assert word in intent_line
