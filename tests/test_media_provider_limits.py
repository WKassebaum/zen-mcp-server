"""Per-provider inline request caps and PDF token rates (media input phase 2)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import utils.media
from providers.gemini import GeminiModelProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ModelResponse, ProviderType
from providers.xai import XAIModelProvider
from tools.chat import ChatTool
from utils.media import (
    PDF_TOKENS_PER_PAGE,
    MediaKind,
    MediaNotSupportedError,
    base64_size,
    check_inline_media_size,
    classify_media,
    estimate_media_tokens,
    pdf_tokens_per_page,
)
from utils.model_context import ModelContext

PDF = str(Path(__file__).parent / "fixtures" / "media" / "zebra.pdf")  # 587 bytes, one page
MODEL = "gemini-3.8-flash"


@pytest.fixture
def gemini_available(monkeypatch):
    # Earlier tests in the suite can leave the registry without a usable Gemini provider
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key-for-tests")
    ModelProviderRegistry.reset_for_testing()
    ModelProviderRegistry.register_provider(ProviderType.GOOGLE, GeminiModelProvider)


def _pdf():
    return classify_media([PDF])[1]


def test_base64_size_rounds_up_to_whole_quads():
    assert [base64_size(n) for n in (0, 1, 3, 4, 587)] == [0, 4, 4, 8, 784]


def test_inline_cap_counts_encoded_bytes_and_points_to_gemini():
    with pytest.raises(MediaNotSupportedError) as exc:
        check_inline_media_size(_pdf(), 700, "anthropic")  # 587 raw bytes fit, 784 encoded do not
    message = str(exc.value)
    assert "zebra.pdf" in message and "anthropic" in message and "Gemini" in message


def test_inline_cap_allows_media_that_fits():
    check_inline_media_size(_pdf(), 784, "anthropic")


def test_provider_with_a_cap_refuses_media_over_it():
    with (
        patch.object(XAIModelProvider, "MEDIA_KINDS", frozenset({MediaKind.PDF})),
        patch.object(XAIModelProvider, "MEDIA_REQUEST_MAX_BYTES", 700),
    ):
        with pytest.raises(MediaNotSupportedError, match="zebra.pdf"):
            XAIModelProvider(api_key="test-key").ensure_media_encodable(_pdf())


def test_provider_with_a_cap_accepts_media_under_it():
    with (
        patch.object(XAIModelProvider, "MEDIA_KINDS", frozenset({MediaKind.PDF})),
        patch.object(XAIModelProvider, "MEDIA_REQUEST_MAX_BYTES", 784),
    ):
        XAIModelProvider(api_key="test-key").ensure_media_encodable(_pdf())


def test_unsupported_kind_is_reported_before_the_cap():
    with patch.object(XAIModelProvider, "MEDIA_REQUEST_MAX_BYTES", 1):
        with pytest.raises(MediaNotSupportedError, match="cannot send"):
            XAIModelProvider(api_key="test-key").ensure_media_encodable(_pdf())


def test_provider_without_a_cap_skips_the_inline_check():
    assert GeminiModelProvider.MEDIA_REQUEST_MAX_BYTES is None  # Gemini uploads to its Files API instead


def test_estimate_uses_the_given_pdf_rate():
    assert estimate_media_tokens(_pdf()) == PDF_TOKENS_PER_PAGE
    assert estimate_media_tokens(_pdf(), page_rate=3_000) == 3_000


def test_pdf_rate_comes_from_the_model_contexts_provider():
    context = SimpleNamespace(provider=SimpleNamespace(PDF_TOKENS_PER_PAGE=3_000))
    assert pdf_tokens_per_page(context) == 3_000


def test_pdf_rate_defaults_when_provider_sets_none_or_context_is_missing():
    assert pdf_tokens_per_page(None) == PDF_TOKENS_PER_PAGE
    assert (
        pdf_tokens_per_page(SimpleNamespace(provider=SimpleNamespace(PDF_TOKENS_PER_PAGE=None))) == PDF_TOKENS_PER_PAGE
    )


@pytest.mark.asyncio
async def test_text_budget_reserve_uses_the_providers_pdf_rate(tmp_path, gemini_available):
    reply = ModelResponse(content="ok", usage={}, model_name=MODEL, provider=ProviderType.GOOGLE)
    with (
        patch.object(GeminiModelProvider, "MEDIA_KINDS", frozenset(MediaKind)),
        patch.object(GeminiModelProvider, "PDF_TOKENS_PER_PAGE", 1_234),
        patch.object(GeminiModelProvider, "generate_content", return_value=reply),
        patch.object(utils.media, "estimate_media_tokens", wraps=utils.media.estimate_media_tokens) as spy,
    ):
        await ChatTool().execute(
            {
                "prompt": "What code is in the PDF?",
                "absolute_file_paths": [PDF],
                "working_directory_absolute_path": str(tmp_path),
                "model": MODEL,
                "_model_context": ModelContext(MODEL),
                "_resolved_model_name": MODEL,
            }
        )
    assert spy.called
    assert spy.call_args.args[1] == 1_234


def test_expert_analysis_reserve_uses_the_providers_pdf_rate():
    from tools.debug import DebugIssueTool

    tool = DebugIssueTool()
    tool._model_context = SimpleNamespace(
        provider=SimpleNamespace(PDF_TOKENS_PER_PAGE=1_234),
        calculate_token_allocation=lambda: SimpleNamespace(file_tokens=50_000),
    )
    with patch.object(utils.media, "estimate_media_tokens", wraps=utils.media.estimate_media_tokens) as spy:
        tool._force_embed_files_for_expert_analysis([PDF])
    assert spy.call_args.args[1] == 1_234
