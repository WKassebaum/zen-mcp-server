"""Per-model media token rates: the model's own rate, else its provider's, else the global default."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import utils.media
import utils.model_restrictions
from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ProviderType
from tools.chat import ChatTool
from tools.debug import DebugIssueTool
from utils.media import (
    PDF_TOKENS_PER_PAGE,
    VIDEO_TOKENS_PER_SECOND,
    classify_media,
    estimate_media_tokens,
    estimate_media_tokens_for,
    pdf_tokens_per_page,
    video_tokens_per_second,
)
from utils.model_context import ModelContext

CONF = Path(__file__).parent.parent / "conf"
MP4 = str(Path(__file__).parent / "fixtures" / "media" / "otter.mp4")  # 3 s
THREE_PAGES = b"%PDF-1.4\n1 0 obj\n<< /Type /Page >><< /Type /Page >><< /Type /Page >>\nendobj\n%%EOF\n"


@pytest.fixture
def real_providers(monkeypatch):
    # Real catalogs behind a real ModelContext; dummy keys, and no client is ever built.
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key-for-tests")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key-for-tests")
    monkeypatch.setattr(utils.model_restrictions, "_restriction_service", None)
    ModelProviderRegistry.reset_for_testing()
    ModelProviderRegistry.register_provider(ProviderType.GOOGLE, GeminiModelProvider)
    ModelProviderRegistry.register_provider(ProviderType.OPENAI, OpenAIModelProvider)


def _context(capability=None, provider=None, field="pdf_tokens_per_page", attribute="PDF_TOKENS_PER_PAGE"):
    return SimpleNamespace(
        capabilities=SimpleNamespace(**{field: capability}),
        provider=SimpleNamespace(**{attribute: provider}),
    )


LOOKUPS = [
    (pdf_tokens_per_page, "pdf_tokens_per_page", "PDF_TOKENS_PER_PAGE", PDF_TOKENS_PER_PAGE),
    (video_tokens_per_second, "video_tokens_per_second", "VIDEO_TOKENS_PER_SECOND", VIDEO_TOKENS_PER_SECOND),
]


@pytest.mark.parametrize("lookup,field,attribute,default", LOOKUPS)
def test_capability_wins_over_provider_which_wins_over_global(lookup, field, attribute, default):
    assert lookup(_context(1_500, 4_000, field, attribute)) == 1_500
    assert lookup(_context(None, 4_000, field, attribute)) == 4_000
    assert lookup(_context(None, None, field, attribute)) == default
    assert lookup(None) == default


@pytest.mark.parametrize("lookup,field,attribute,default", LOOKUPS)
@pytest.mark.parametrize("bad", [True, False, 0, -5, 1.5, "1500", MagicMock()])
def test_only_a_real_positive_int_counts(lookup, field, attribute, default, bad):
    assert lookup(_context(bad, 4_000, field, attribute)) == 4_000
    assert lookup(_context(None, bad, field, attribute)) == default


@pytest.mark.parametrize("lookup,field,attribute,default", LOOKUPS)
def test_a_mock_context_gets_the_global_rate(lookup, field, attribute, default):
    assert lookup(MagicMock()) == default


@pytest.mark.parametrize("lookup,field,attribute,default", LOOKUPS)
def test_a_context_whose_lookups_raise_counts_as_no_value(lookup, field, attribute, default):
    class Unresolvable:
        # ModelContext.capabilities and .provider resolve through the registry and raise when the model is unknown
        @property
        def capabilities(self):
            raise ValueError("Model 'x' is not available with current API keys")

        provider = SimpleNamespace(**{attribute: 4_000})

    class NoProvider:
        capabilities = None

        @property
        def provider(self):
            raise ValueError("Model 'x' is not available with current API keys")

    assert lookup(Unresolvable()) == 4_000
    assert lookup(NoProvider()) == default


def test_estimate_uses_the_given_video_rate():
    video = classify_media([MP4])[1]
    assert estimate_media_tokens(video) == 3 * VIDEO_TOKENS_PER_SECOND
    assert estimate_media_tokens(video, video_rate=160) == 480


def test_estimate_for_a_context_applies_both_rates(tmp_path):
    pdf = tmp_path / "three.pdf"
    pdf.write_bytes(THREE_PAGES)
    media = classify_media([str(pdf), MP4])[1]
    context = SimpleNamespace(
        capabilities=SimpleNamespace(pdf_tokens_per_page=1_500, video_tokens_per_second=160), provider=None
    )
    assert estimate_media_tokens_for(media, context) == 3 * 1_500 + 3 * 160


def test_estimate_for_no_media_looks_up_no_rate():
    with (
        patch.object(utils.media, "pdf_tokens_per_page", side_effect=AssertionError("no media, no PDF rate")),
        patch.object(utils.media, "video_tokens_per_second", side_effect=AssertionError("no media, no video rate")),
    ):
        assert estimate_media_tokens_for([], MagicMock()) == 0


@pytest.mark.parametrize(
    "model,pdf_rate,video_rate",
    [
        ("gpt-5.5", 2_500, VIDEO_TOKENS_PER_SECOND),
        ("gpt-6-luna", 4_000, VIDEO_TOKENS_PER_SECOND),  # measured 2,902: keeps the OpenAI provider rate
        ("gemini-3.8-flash", PDF_TOKENS_PER_PAGE, 160),
        ("gemini-2.5-pro", PDF_TOKENS_PER_PAGE, VIDEO_TOKENS_PER_SECOND),
    ],
)
def test_real_model_contexts_resolve_their_own_rates(real_providers, model, pdf_rate, video_rate):
    context = ModelContext(model)
    assert pdf_tokens_per_page(context) == pdf_rate
    assert video_tokens_per_second(context) == video_rate


def _catalog(name):
    return {entry["model_name"]: entry for entry in json.loads((CONF / name).read_text())["models"]}


def test_openai_page_rates_are_set_only_where_measured():
    rates = {model: entry.get("pdf_tokens_per_page") for model, entry in _catalog("openai_models.json").items()}
    measured_1025 = ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.4", "gpt-5.2", "o4-mini"]
    measured_323 = ["gpt-5", "gpt-5.1", "o3", "gpt-4.1"]
    assert {model: rates[model] for model in measured_1025} == dict.fromkeys(measured_1025, 2_500)
    assert {model: rates[model] for model in measured_323} == dict.fromkeys(measured_323, 1_500)
    unset = sorted(model for model, rate in rates.items() if rate is None)
    assert [model for model in unset if model.startswith("gpt-6") or model.endswith("-pro")] == [
        "gpt-5.2-pro",
        "gpt-5.4-pro",
        "gpt-5.5-pro",
        "gpt-6-astra",
        "gpt-6-luna",
        "gpt-6-sol",
    ]
    assert all("video_tokens_per_second" not in entry for entry in _catalog("openai_models.json").values())


def test_gemini_video_rates_are_set_for_gemini_3_only():
    catalog = _catalog("gemini_models.json")
    rates = {model: entry.get("video_tokens_per_second") for model, entry in catalog.items()}
    gemini_3 = [model for model, entry in catalog.items() if model.startswith("gemini-3") and entry["supports_video"]]
    assert gemini_3 and {model: rates[model] for model in gemini_3} == dict.fromkeys(gemini_3, 160)
    assert {model: rate for model, rate in rates.items() if model.startswith("gemini-2.5")} == {
        "gemini-2.5-pro": None,
        "gemini-2.5-flash-lite": None,
        "gemini-2.5-flash": None,
    }
    assert all("pdf_tokens_per_page" not in entry for entry in catalog.values())


# (model, attachment, tokens reserved): 3 pages at gpt-5.5's 2,500, and 3 s at gemini-3.8-flash's 160
RESERVES = [("gpt-5.5", "pdf", 7_500), ("gemini-3.8-flash", "video", 480)]


def _attachment(kind, tmp_path):
    if kind == "video":
        return MP4
    pdf = tmp_path / "three.pdf"
    pdf.write_bytes(THREE_PAGES)
    return str(pdf)


@pytest.mark.parametrize("model,kind,reserved", RESERVES)
def test_simple_tool_reserves_the_models_own_rate(real_providers, tmp_path, model, kind, reserved):
    notes = tmp_path / "notes.txt"
    notes.write_text("hello\n")
    with patch("tools.shared.base_tool.read_files", return_value="") as read_files:
        ChatTool()._prepare_file_content_for_prompt(
            [_attachment(kind, tmp_path), str(notes)], None, max_tokens=100_000, model_context=ModelContext(model)
        )
    assert read_files.call_args.kwargs["max_tokens"] == 100_000 - reserved


@pytest.mark.parametrize("model,kind,reserved", RESERVES)
def test_expert_analysis_reserves_the_models_own_rate(real_providers, tmp_path, model, kind, reserved):
    tool = DebugIssueTool()
    tool._model_context = ModelContext(model)
    file_tokens = tool._model_context.calculate_token_allocation().file_tokens
    with patch("utils.file_utils.read_files", return_value="") as read_files:
        tool._force_embed_files_for_expert_analysis([_attachment(kind, tmp_path)])
    assert read_files.call_args.kwargs["max_tokens"] == file_tokens - reserved
