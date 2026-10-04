"""xAI encoder: a request with media goes to /v1/responses as input_file parts; text-only requests stay on Chat.

xAI refuses file parts on /v1/chat/completions ("Please use /v1/responses instead"), and its models without
extended thinking reject the Responses ``reasoning`` parameter. OpenAI and OpenRouter requests are unchanged.
"""

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from openai.types.responses import ResponseUsage

from providers.openai import OpenAIModelProvider
from providers.openrouter import OpenRouterProvider
from providers.xai import XAIModelProvider
from utils.media import MediaKind, MediaNotSupportedError, classify_media

FIXTURES = Path(__file__).parent / "fixtures" / "media"
PDF = str(FIXTURES / "zebra.pdf")
DATA_URL = "data:application/pdf;base64," + base64.b64encode(Path(PDF).read_bytes()).decode()
PNG = "data:image/png;base64,iVBORw0KGgo="
ATTACHED = [{"name": "zebra.pdf", "kind": "pdf", "bytes": 587, "transport": "inline"}]
GROK = "grok-4.7"  # supports_extended_thinking: true
NON_REASONING = ["grok-build-0.1", "grok-4.20-0309-non-reasoning"]  # supports_extended_thinking: false


def _media(*paths):
    return classify_media(list(paths or [PDF]))[1]


def _provider(cls=XAIModelProvider, usage=None):
    provider = cls("test-key")
    provider._client = MagicMock()  # never reach the real SDK client
    provider._client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ZEBRA-42"), finish_reason="stop")],
        model=GROK,
        id="chat-1",
        created=0,
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2, total_tokens=12),
    )
    provider._client.responses.create.return_value = SimpleNamespace(
        output_text="ZEBRA-42",
        usage=usage or SimpleNamespace(input_tokens=1_775, output_tokens=2, total_tokens=1_777),
    )
    return provider


def _responses_request(provider):
    provider._client.chat.completions.create.assert_not_called()
    return provider._client.responses.create.call_args.kwargs


def test_xai_declares_pdf_only_explicit_only_and_its_limits():
    assert XAIModelProvider.MEDIA_KINDS == frozenset({MediaKind.PDF})
    assert XAIModelProvider.MEDIA_AUTO_ROUTING is False
    assert XAIModelProvider.MEDIA_REQUEST_MAX_BYTES == 50_000_000
    assert XAIModelProvider.PDF_TOKENS_PER_PAGE == 2_500


def test_grok_with_a_pdf_uses_the_responses_endpoint_with_reasoning():
    provider = _provider()
    response = provider.generate_content("What code?", GROK, system_prompt="Be terse.", media=_media())
    assert _responses_request(provider) == {
        "model": GROK,
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "Be terse."}]},
            {
                "role": "user",
                "content": [
                    {"type": "input_file", "filename": "zebra.pdf", "file_data": DATA_URL},
                    {"type": "input_text", "text": "What code?"},
                ],
            },
        ],
        "reasoning": {"effort": "medium"},
        "store": False,
    }
    assert DATA_URL.startswith("data:application/pdf;base64,")
    assert response.content == "ZEBRA-42"
    assert response.metadata["endpoint"] == "responses"
    assert response.metadata["media_attached"] == ATTACHED
    assert "server_side_tool_calls" not in response.metadata  # this usage carries no such field


@pytest.mark.parametrize("model", NON_REASONING)
def test_grok_without_extended_thinking_gets_no_reasoning_parameter(model):
    assert not XAIModelProvider("test-key").get_capabilities(model).supports_extended_thinking
    provider = _provider()
    provider.generate_content("What code?", model, media=_media())
    request = _responses_request(provider)
    assert "reasoning" not in request
    assert set(request) == {"model", "input", "store"}
    assert request["input"][-1]["content"][0]["type"] == "input_file"


def test_grok_without_media_stays_on_chat_completions():
    provider = _provider()
    response = provider.generate_content("hi", GROK, system_prompt="SYS")
    provider._client.responses.create.assert_not_called()
    assert provider._client.chat.completions.create.call_args.kwargs == {
        "model": GROK,
        "messages": [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}],
        "stream": False,
        "temperature": 0.3,
    }
    assert "endpoint" not in response.metadata


def test_empty_media_list_stays_on_chat_completions():
    provider = _provider()
    provider.generate_content("hi", GROK, media=[])
    provider._client.responses.create.assert_not_called()
    provider._client.chat.completions.create.assert_called_once()


def test_images_ride_the_same_responses_request():
    provider = _provider()
    provider.generate_content("Compare", GROK, images=[PNG], media=_media())
    content = _responses_request(provider)["input"][-1]["content"]
    assert content == [
        {"type": "input_file", "filename": "zebra.pdf", "file_data": DATA_URL},
        {"type": "input_text", "text": "Compare"},
        {"type": "input_image", "image_url": PNG},
    ]


def test_server_side_tool_calls_reach_the_metadata():
    # xAI's Responses usage after a 4-page scanned PDF: one attachment_search call (live, 2026-10-03).
    usage = ResponseUsage.model_validate(
        {
            "input_tokens": 9_997,
            "output_tokens": 20,
            "total_tokens": 10_017,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
            "num_server_side_tools_used": 1,
            "cost_in_usd_ticks": 123_456,
        }
    )
    provider = _provider(usage=usage)
    response = provider.generate_content("What code?", GROK, media=_media())
    assert response.metadata["server_side_tool_calls"] == 1
    assert response.usage == {"input_tokens": 9_997, "output_tokens": 20, "total_tokens": 10_017}


def test_zero_server_side_tool_calls_are_recorded_too():
    usage = SimpleNamespace(input_tokens=1_775, output_tokens=2, total_tokens=1_777, num_server_side_tools_used=0)
    response = _provider(usage=usage).generate_content("What code?", GROK, media=_media())
    assert response.metadata["server_side_tool_calls"] == 0


def _sparse_pdf(tmp_path, size):
    path = tmp_path / "big.pdf"
    with path.open("wb") as handle:
        handle.write(b"%PDF-1.4\n")
        handle.truncate(size)  # sparse: nothing real is written
    return str(path)


def test_pdfs_over_50_mb_encoded_are_refused_before_any_call(tmp_path):
    media = _media(_sparse_pdf(tmp_path, 37_500_001))  # 50,000,004 bytes once base64-encoded
    provider = _provider()
    with pytest.raises(MediaNotSupportedError, match=r"xai takes media inline, in requests of at most .*big\.pdf"):
        provider.generate_content("What code?", GROK, media=media)
    provider._client.chat.completions.create.assert_not_called()
    provider._client.responses.create.assert_not_called()


def test_50_mb_encoded_still_fits(tmp_path):
    XAIModelProvider("test-key").ensure_media_encodable(_media(_sparse_pdf(tmp_path, 37_500_000)))


# --- OpenAI and OpenRouter: the Responses request is unchanged ------------------------------------------------


def test_openai_responses_request_with_a_pdf_is_unchanged():
    provider = _provider(OpenAIModelProvider)
    response = provider.generate_content("What code?", "gpt-6-luna", media=_media())
    assert _responses_request(provider) == {
        "model": "gpt-6-luna",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_file", "filename": "zebra.pdf", "file_data": DATA_URL},
                    {"type": "input_text", "text": "What code?"},
                ],
            }
        ],
        "reasoning": {"effort": "medium"},
        "store": False,
    }
    assert response.metadata["endpoint"] == "responses"


def test_openai_chat_model_with_a_pdf_stays_on_chat_completions():
    provider = _provider(OpenAIModelProvider)
    provider.generate_content("What code?", "gpt-5.5", media=_media())
    provider._client.responses.create.assert_not_called()
    provider._client.chat.completions.create.assert_called_once()


def _responses_models(cls):
    provider = cls("test-key")
    names = [name for name, caps in provider.get_all_model_capabilities().items() if caps.use_openai_response_api]
    assert names, f"{cls.__name__} lists no Responses API model"
    return [(cls, name) for name in sorted(names)]


@pytest.mark.parametrize("cls, model", _responses_models(OpenAIModelProvider) + _responses_models(OpenRouterProvider))
def test_every_openai_and_openrouter_responses_model_still_gets_reasoning(cls, model):
    provider = _provider(cls)
    effort = provider.get_capabilities(model).default_reasoning_effort or "medium"
    provider.generate_content("hi", model)
    request = _responses_request(provider)
    assert request["reasoning"] == {"effort": effort}
    assert list(request) == ["model", "input", "reasoning", "store"]  # same keys, same order as before
