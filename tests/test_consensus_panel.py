"""The consensus panel ('frontier': the top model of each configured vendor) and its use by consensus and the CLI.

Providers are registered on dummy keys. ConsensusTool._consult_model is mocked, so no provider is called.
"""

import json
import os
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from providers.registry import ModelProviderRegistry
from providers.shared import ProviderType
from tools.consensus import ConsensusTool
from tools.models import ToolModelCategory
from tools.shared.exceptions import ToolExecutionError
from utils.media import MediaKind

PDF_ONLY = frozenset({MediaKind.PDF})
FOUR_KEYS = {
    "GEMINI_API_KEY": "test-key",
    "OPENAI_API_KEY": "test-key",
    "XAI_API_KEY": "test-key",
    "ANTHROPIC_API_KEY": "test-key",
}
# conftest registers Gemini, OpenAI and xAI on dummy keys: the panel every test below gets unless it configures others
CONFTEST_PANEL = ["grok-4.7", "gemini-3.1-pro-preview", "gpt-6-astra"]


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


def _vendor(model_name: str) -> str:
    provider_type = ModelProviderRegistry.get_provider_for_model(model_name).get_provider_type()
    return ModelProviderRegistry._model_vendor(provider_type, model_name)


# ---------------------------------------------------------------------------
# The panel
# ---------------------------------------------------------------------------


def test_four_providers_give_four_vendors_each_its_top_model():
    with _configured(FOUR_KEYS):
        panel = ModelProviderRegistry.frontier_panel()
        assert panel == ["grok-4.7", "gemini-3.1-pro-preview", "claude-fable-5-1", "gpt-6-astra"]
        assert len({_vendor(name) for name in panel}) == 4
        for name in panel:
            provider = ModelProviderRegistry.get_provider_for_model(name)
            allowed = ModelProviderRegistry._get_allowed_models_for_provider(provider, provider.get_provider_type())
            assert provider.rank_models(allowed)[0].model_name == name


def test_the_panel_stops_at_its_limit():
    with _configured(FOUR_KEYS):
        assert ModelProviderRegistry.frontier_panel(limit=2) == ["grok-4.7", "gemini-3.1-pro-preview"]


def test_openrouter_adds_one_model_per_vendor_not_already_on_the_panel():
    with _configured({"ANTHROPIC_API_KEY": "test-key", "OPENROUTER_API_KEY": "test-key"}):
        panel = ModelProviderRegistry.frontier_panel()
        assert panel == [
            "claude-fable-5-1",  # native Anthropic: anthropic/claude-fable-5.1 is not added beside it
            "google/gemini-3.1-pro-preview",
            "openai/gpt-6-astra",
            "x-ai/grok-4.7",
        ]
        assert [_vendor(name) for name in panel] == ["anthropic", "google", "openai", "xai"]


def test_openrouter_alone_gives_a_full_panel():
    with _configured({"OPENROUTER_API_KEY": "test-key"}):
        assert ModelProviderRegistry.frontier_panel() == [
            "anthropic/claude-fable-5.1",
            "google/gemini-3.1-pro-preview",
            "openai/gpt-6-astra",
            "x-ai/grok-4.7",
        ]


def test_a_pdf_panel_leaves_out_grok():
    with _configured(FOUR_KEYS):
        panel = ModelProviderRegistry.frontier_panel(required_media=PDF_ONLY)
        assert panel == ["gemini-3.1-pro-preview", "claude-fable-5-1", "gpt-6-astra"]
        for name in panel:
            provider = ModelProviderRegistry.get_provider_for_model(name)
            assert MediaKind.PDF in provider.get_capabilities(name).supported_media_kinds()


def test_an_allow_list_narrows_a_provider_to_its_allowed_top_model():
    with _configured({**FOUR_KEYS, "OPENAI_ALLOWED_MODELS": "gpt-5.5,o3", "XAI_ALLOWED_MODELS": "grok-4.6"}):
        assert ModelProviderRegistry.frontier_panel() == [
            "grok-4.6",
            "gemini-3.1-pro-preview",
            "claude-fable-5-1",
            "gpt-5.5",
        ]


@pytest.mark.parametrize(
    "provider_type,model_name,vendor",
    [
        (ProviderType.GOOGLE, "gemini-3.8-flash", "google"),
        (ProviderType.XAI, "grok-4.7", "xai"),
        (ProviderType.OPENROUTER, "x-ai/grok-4.7", "xai"),
        (ProviderType.OPENROUTER, "google/gemini-3.8-flash", "google"),
        (ProviderType.OPENROUTER, "anthropic/claude-opus-5.5", "anthropic"),
        (ProviderType.OPENROUTER, "openai/gpt-6-sol", "openai"),
        (ProviderType.OPENROUTER, "moonshotai/kimi-k3", "moonshotai"),
        (ProviderType.AZURE, "gpt-6-sol", "azure"),
        (ProviderType.CUSTOM, "llama3.2", "custom"),
        (ProviderType.DIAL, "gpt-6-sol", "dial"),
    ],
)
def test_model_vendor(provider_type, model_name, vendor):
    assert ModelProviderRegistry._model_vendor(provider_type, model_name) == vendor


# ---------------------------------------------------------------------------
# Consensus step 1
# ---------------------------------------------------------------------------


async def _fake_consult(self, model_config, request):
    return {"model": model_config["model"], "stance": model_config.get("stance", "neutral"), "status": "success"}


def _step(step_number: int, total_steps: int = 2, **extra) -> dict:
    return {
        "step": "Evaluate the proposal",
        "step_number": step_number,
        "total_steps": total_steps,
        "next_step_required": step_number < total_steps,
        "findings": "notes",
        **extra,
    }


async def _step_one(tool: ConsensusTool, **extra) -> dict:
    with patch.object(ConsensusTool, "_consult_model", _fake_consult):
        result = await tool.execute(_step(1, **extra))
    return json.loads(result[0].text)


@pytest.mark.asyncio
async def test_frontier_expands_in_place_and_every_member_keeps_its_stance():
    tool = ConsensusTool()
    models = [{"model": "frontier", "stance": "for", "stance_prompt": "Argue for it"}]
    data = await _step_one(tool, models=models)
    assert tool.models_to_consult == [
        {"model": name, "stance": "for", "stance_prompt": "Argue for it"} for name in CONFTEST_PANEL
    ]
    assert data["total_steps"] == len(CONFTEST_PANEL)
    assert data["model_consulted"] == CONFTEST_PANEL[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("models", [[], None])
async def test_no_models_becomes_the_neutral_panel(models):
    tool = ConsensusTool()
    extra = {} if models is None else {"models": models}
    await _step_one(tool, **extra)
    assert tool.models_to_consult == [{"model": name, "stance": "neutral"} for name in CONFTEST_PANEL]


@pytest.mark.asyncio
async def test_frontier_expands_where_it_stands_and_skips_a_member_named_again():
    tool = ConsensusTool()
    models = [
        {"model": "o3", "stance": "against"},
        {"model": "frontier", "stance": "for"},
        {"model": "gpt-6-astra", "stance": "for"},  # also on the panel: listed once
    ]
    await _step_one(tool, models=models)
    assert [(m["model"], m["stance"]) for m in tool.models_to_consult] == [
        ("o3", "against"),
        ("grok-4.7", "for"),
        ("gemini-3.1-pro-preview", "for"),
        ("gpt-6-astra", "for"),
    ]


@pytest.mark.asyncio
async def test_fast_balanced_and_auto_resolve_with_the_consensus_category():
    # OpenAI alone picks a different model per category (with xAI first, all three would be grok-4.7)
    tool = ConsensusTool()
    assert tool.get_model_category() == ToolModelCategory.EXTENDED_REASONING
    with (
        _configured({"OPENAI_API_KEY": "test-key"}),
        patch.object(
            ModelProviderRegistry, "resolve_model_intent", wraps=ModelProviderRegistry.resolve_model_intent
        ) as resolver,
    ):
        await _step_one(tool, models=[{"model": "fast"}, {"model": "balanced", "stance": "against"}, {"model": "auto"}])
    assert [call.args[:2] for call in resolver.call_args_list] == [
        ("fast", ToolModelCategory.EXTENDED_REASONING),
        ("balanced", ToolModelCategory.EXTENDED_REASONING),
        ("auto", ToolModelCategory.EXTENDED_REASONING),
    ]
    assert tool.models_to_consult == [
        {"model": "gpt-6-luna"},
        {"model": "gpt-6-sol", "stance": "against"},
        {"model": "gpt-6-astra"},
    ]


@pytest.mark.asyncio
async def test_two_intent_words_that_pick_the_same_model_consult_it_once():
    tool = ConsensusTool()
    with pytest.raises(ToolExecutionError) as exc:
        await _step_one(tool, models=[{"model": "fast"}, {"model": "auto"}])  # both grok-4.7 here
    assert "got 1 (grok-4.7)" in json.loads(str(exc.value))["content"]


@pytest.mark.asyncio
async def test_named_consensus_models_are_used_as_named():
    tool = ConsensusTool()
    refuse = AssertionError("a named model reached the resolver")
    with (
        patch.object(ModelProviderRegistry, "resolve_model_intent", side_effect=refuse) as resolver,
        patch.object(ModelProviderRegistry, "frontier_panel", side_effect=refuse) as panel,
    ):
        await _step_one(tool, models=[{"model": "flash"}, {"model": "gpt-5.5", "stance": "for"}])
    resolver.assert_not_called()
    panel.assert_not_called()
    assert tool.models_to_consult == [{"model": "flash"}, {"model": "gpt-5.5", "stance": "for"}]


@pytest.mark.asyncio
async def test_a_single_concrete_model_is_an_error_naming_the_configured_keys():
    tool = ConsensusTool()
    with patch.object(ConsensusTool, "_consult_model") as consult:
        with pytest.raises(ToolExecutionError) as exc:
            await tool.execute(_step(1, models=[{"model": "gpt-5.5"}]))
    consult.assert_not_called()
    content = json.loads(str(exc.value))["content"]
    assert "at least 2 models" in content
    assert "gpt-5.5" in content
    for key in ("XAI_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        assert key in content


@pytest.mark.asyncio
async def test_a_one_provider_panel_is_an_error():
    with _configured({"GEMINI_API_KEY": "test-key"}):
        with pytest.raises(ToolExecutionError) as exc:
            await ConsensusTool().execute(_step(1, models=[{"model": "frontier"}]))
    content = json.loads(str(exc.value))["content"]
    assert "gemini-3.1-pro-preview" in content and "GEMINI_API_KEY" in content
    assert "OPENAI_API_KEY" not in content


@pytest.mark.asyncio
async def test_later_steps_consult_the_expanded_names():
    tool = ConsensusTool()
    consulted = []

    async def record(self, model_config, request):
        consulted.append(model_config["model"])
        return await _fake_consult(self, model_config, request)

    with patch.object(ConsensusTool, "_consult_model", record):
        first = json.loads((await tool.execute(_step(1, models=[{"model": "frontier"}])))[0].text)
        continuation_id = first["continuation_offer"]["continuation_id"]
        for step_number in range(2, first["total_steps"] + 1):
            await tool.execute(_step(step_number, first["total_steps"], continuation_id=continuation_id))
    assert consulted == CONFTEST_PANEL


def test_models_schema_takes_a_single_frontier_entry():
    schema = ConsensusTool().get_input_schema()
    models = schema["properties"]["models"]
    assert models["minItems"] == 1
    assert "Name models explicitly, or use 'frontier' for the top model of each configured provider" in (
        models["description"]
    )


# ---------------------------------------------------------------------------
# CLI: zen consensus consults every model
# ---------------------------------------------------------------------------


def _run_cli(*args: str):
    from zen_cli.main import cli

    consulted = []

    async def record(self, model_config, request):
        consulted.append(model_config["model"])
        return {**(await _fake_consult(self, model_config, request)), "verdict": f"verdict of {model_config['model']}"}

    with patch.object(ConsensusTool, "_consult_model", record):
        result = CliRunner().invoke(cli, ["consensus", "Should we?", *args], catch_exceptions=False)
    return result, consulted


def test_cli_consults_every_named_model():
    result, consulted = _run_cli("--models", "gpt-5.5,flash,o3")
    assert result.exit_code == 0, result.output
    assert consulted == ["gpt-5.5", "flash", "o3"]
    for name in consulted:
        assert f"verdict of {name}" in result.output


@pytest.mark.parametrize("args", [(), ("--models", "frontier")])
def test_cli_defaults_to_the_frontier_panel(args):
    result, consulted = _run_cli(*args)
    assert result.exit_code == 0, result.output
    assert consulted == CONFTEST_PANEL
    assert "Consensus Complete" in result.output


def test_cli_json_lists_every_step():
    result, consulted = _run_cli("--models", "gpt-5.5,flash", "--json")
    assert result.exit_code == 0, result.output
    steps = json.loads(result.output)
    assert [step["model_consulted"] for step in steps] == ["gpt-5.5", "flash"]
    assert steps[-1]["consensus_complete"] is True


@pytest.mark.asyncio
async def test_every_cli_step_carries_step_one_files(tmp_path):
    from zen_cli.main import _run_consensus

    notes = tmp_path / "notes.md"
    notes.write_text("# Notes\n")
    seen = []

    async def record(self, model_config, request):
        seen.append((model_config["model"], list(request.relevant_files)))
        return await _fake_consult(self, model_config, request)

    with patch.object(ConsensusTool, "_consult_model", record):
        steps = await _run_consensus(
            _step(1, models=[{"model": "gpt-5.5"}, {"model": "flash"}], relevant_files=[str(notes)])
        )
    assert seen == [("gpt-5.5", [str(notes)]), ("flash", [str(notes)])]
    assert len(steps) == 2 and steps[-1]["consensus_complete"] is True
