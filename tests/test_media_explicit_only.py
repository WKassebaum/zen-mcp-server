"""Explicit-only media providers (MEDIA_AUTO_ROUTING False): media reaches them only when the user names a model.

Past one page, xAI reads an attached PDF through a billed server-side search tool that may read it only in part,
so auto mode and the capability hints never send media to Grok. A Grok model the user names still takes its
flagged kinds.
"""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from providers.anthropic import AnthropicProvider
from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.openrouter import OpenRouterProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ProviderType
from providers.xai import XAIModelProvider
from tools.chat import ChatTool
from tools.models import ToolModelCategory
from tools.shared.exceptions import ToolExecutionError
from utils.media import MEDIA_PROVIDERS, MediaKind, MediaNotSupportedError
from utils.model_context import ModelContext

PDF = str(Path(__file__).parent / "fixtures" / "media" / "zebra.pdf")
PDF_ONLY = frozenset({MediaKind.PDF})
ENCODERS = {
    "google": GeminiModelProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIModelProvider,
    "openrouter": OpenRouterProvider,
}


@pytest.fixture
def every_grok_model_takes_pdf(monkeypatch):
    """Every Grok model is flagged supports_pdf, as the catalog has done since the 2026-10-03 probe; patched in
    so these tests keep proving that only MEDIA_AUTO_ROUTING keeps PDFs from Grok if a flag is ever dropped."""
    assert XAIModelProvider.MEDIA_KINDS == PDF_ONLY
    for name, capabilities in list(XAIModelProvider.MODEL_CAPABILITIES.items()):
        monkeypatch.setitem(XAIModelProvider.MODEL_CAPABILITIES, name, replace(capabilities, supports_pdf=True))


def _grok_models(names):
    return [name for name in names if name.startswith("grok")]


def test_xai_takes_media_only_when_named():
    assert XAIModelProvider.MEDIA_AUTO_ROUTING is False
    assert all(cls.MEDIA_AUTO_ROUTING for cls in ENCODERS.values())


@pytest.mark.parametrize("category", list(ToolModelCategory))
def test_auto_mode_never_routes_a_pdf_to_grok(every_grok_model_takes_pdf, category):
    # The conftest registers Gemini, OpenAI and xAI on dummy keys; xAI comes first in priority.
    assert ModelProviderRegistry.PROVIDER_PRIORITY_ORDER[0] == ProviderType.XAI
    assert ModelProviderRegistry.get_provider(ProviderType.XAI) is not None
    model = ModelProviderRegistry.get_preferred_fallback_model(category, required_media=PDF_ONLY)
    provider = ModelProviderRegistry.get_provider_for_model(model)
    assert provider.get_provider_type() != ProviderType.XAI, model
    assert MediaKind.PDF in provider.get_capabilities(model).supported_media_kinds()


def test_the_flag_is_what_keeps_pdfs_from_grok(every_grok_model_takes_pdf):
    # The same setup with the flag on routes the PDF to Grok, so the test above is not passing by accident.
    with patch.object(XAIModelProvider, "MEDIA_AUTO_ROUTING", True):
        model = ModelProviderRegistry.get_preferred_fallback_model(ToolModelCategory.BALANCED, required_media=PDF_ONLY)
    assert ModelProviderRegistry.get_provider_for_model(model).get_provider_type() == ProviderType.XAI


def test_auto_mode_without_media_still_picks_grok(every_grok_model_takes_pdf):
    model = ModelProviderRegistry.get_preferred_fallback_model(ToolModelCategory.BALANCED)
    assert ModelProviderRegistry.get_provider_for_model(model).get_provider_type() == ProviderType.XAI


def test_capable_model_list_names_no_grok_model(every_grok_model_takes_pdf):
    models = ModelProviderRegistry.find_media_capable_models(PDF_ONLY, limit=100)
    assert models  # Gemini and OpenAI models still qualify
    assert _grok_models(models) == []


def test_a_named_grok_model_takes_its_pdf(every_grok_model_takes_pdf):
    # A named model is checked against its own flags and its provider's encoder, never the auto-routing filter.
    tool = ChatTool()
    media = tool._media_from_paths([PDF])
    with patch.object(
        ModelProviderRegistry, "_filter_models_for_media", side_effect=AssertionError("auto-routing filter used")
    ):
        tool._validate_media_support(media, ModelContext("grok-4.7"))


def test_a_refused_named_model_suggests_no_grok_model(every_grok_model_takes_pdf):
    tool = ChatTool()
    media = tool._media_from_paths([PDF])
    with pytest.raises(ToolExecutionError) as exc:
        tool._validate_media_support(media, ModelContext("o3-mini"))  # o3-mini is not flagged for PDF
    payload = json.loads(str(exc.value))
    assert payload["metadata"]["capable_models"]
    assert _grok_models(payload["metadata"]["capable_models"]) == []
    assert "grok" not in payload["content"]


def test_hints_never_name_the_xai_key():
    # MEDIA_PROVIDERS answers "which key would let auto mode serve this"; an xAI key never would.
    assert "xai" not in {entry[0] for entry in MEDIA_PROVIDERS}
    for provider_value, *_ in MEDIA_PROVIDERS:
        assert ENCODERS[provider_value].MEDIA_AUTO_ROUTING, provider_value


def test_xai_alone_cannot_serve_a_pdf_in_auto_mode(every_grok_model_takes_pdf, monkeypatch):
    for key in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    ModelProviderRegistry.clear_cache()
    try:
        assert ModelProviderRegistry.get_provider(ProviderType.XAI) is not None
        with pytest.raises(MediaNotSupportedError) as exc:
            ModelProviderRegistry.get_preferred_fallback_model(ToolModelCategory.BALANCED, required_media=PDF_ONLY)
    finally:
        ModelProviderRegistry.clear_cache()
    assert str(exc.value) == (
        "No available model can take pdf input: "
        "configure GEMINI_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY or OPENROUTER_API_KEY."
    )
