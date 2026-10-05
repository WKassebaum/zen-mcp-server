"""Cached input tokens reach ModelResponse.usage and the tool output, read from each endpoint's own usage field.

- Chat Completions (OpenAI, xAI, OpenRouter): usage.prompt_tokens_details.cached_tokens
- Responses API (OpenAI, xAI, OpenRouter): usage.input_tokens_details.cached_tokens
- Gemini: usage_metadata.cached_content_token_count
- Claude: usage.cache_read_input_tokens, and cache_creation_input_tokens as cache_write_input_tokens

A field the endpoint does not report leaves the key out (never a made-up 0).
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from anthropic.types import Usage as AnthropicUsage
from google.genai import types as genai_types
from openai.types import CompletionUsage
from openai.types.completion_usage import PromptTokensDetails
from openai.types.responses import ResponseUsage
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from providers.anthropic import AnthropicProvider
from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.openrouter import OpenRouterProvider
from providers.shared import ModelResponse, ProviderType
from providers.xai import XAIModelProvider
from tools.chat import ChatTool
from utils.media import response_media_metadata
from utils.model_context import ModelContext

OPENAI_COMPATIBLE = [OpenAIModelProvider, XAIModelProvider, OpenRouterProvider]


def _chat_usage(details):
    return CompletionUsage(prompt_tokens=5_000, completion_tokens=12, total_tokens=5_012, prompt_tokens_details=details)


def _responses_usage(cached, **extra):
    return ResponseUsage.model_validate(
        {
            "input_tokens": 5_000,
            "input_tokens_details": InputTokensDetails(cached_tokens=cached).model_dump(),
            "output_tokens": 12,
            "output_tokens_details": OutputTokensDetails(reasoning_tokens=0).model_dump(),
            "total_tokens": 5_012,
            **extra,
        }
    )


# --- Chat Completions -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("provider_class", OPENAI_COMPATIBLE)
def test_chat_completions_cached_tokens(provider_class):
    usage = provider_class("test-key")._extract_usage(
        SimpleNamespace(usage=_chat_usage(PromptTokensDetails(cached_tokens=4_096)))
    )
    assert usage == {"input_tokens": 5_000, "output_tokens": 12, "total_tokens": 5_012, "cached_input_tokens": 4_096}


@pytest.mark.parametrize("provider_class", OPENAI_COMPATIBLE)
@pytest.mark.parametrize(
    "details", [None, PromptTokensDetails(), PromptTokensDetails(audio_tokens=3)], ids=["no-details", "empty", "audio"]
)
def test_chat_completions_without_cached_tokens_leaves_the_key_out(provider_class, details):
    usage = provider_class("test-key")._extract_usage(SimpleNamespace(usage=_chat_usage(details)))
    assert "cached_input_tokens" not in usage
    assert usage["input_tokens"] == 5_000


def test_chat_completions_reported_zero_stays_zero():
    usage = OpenAIModelProvider("test-key")._extract_usage(
        SimpleNamespace(usage=_chat_usage(PromptTokensDetails(cached_tokens=0)))
    )
    assert usage["cached_input_tokens"] == 0


def test_mock_usage_never_reports_cached_tokens():
    # Many tests build usage from Mock objects: an attribute that is not a real int is not a count
    usage = OpenAIModelProvider("test-key")._extract_usage(
        SimpleNamespace(usage=MagicMock(prompt_tokens=10, completion_tokens=2, total_tokens=12))
    )
    assert "cached_input_tokens" not in usage


# --- Responses API --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("provider_class", OPENAI_COMPATIBLE)
def test_responses_api_cached_tokens(provider_class):
    usage = provider_class("test-key")._extract_usage(SimpleNamespace(usage=_responses_usage(2_048)))
    assert usage == {"input_tokens": 5_000, "output_tokens": 12, "total_tokens": 5_012, "cached_input_tokens": 2_048}


def test_xai_responses_usage_with_its_extra_fields():
    usage = XAIModelProvider("test-key")._extract_usage(
        SimpleNamespace(usage=_responses_usage(1_024, num_server_side_tools_used=0, num_sources_used=0))
    )
    assert usage["cached_input_tokens"] == 1_024


def test_responses_api_without_details_leaves_the_key_out():
    usage = OpenAIModelProvider("test-key")._extract_usage(
        SimpleNamespace(usage=SimpleNamespace(input_tokens=5_000, output_tokens=12, total_tokens=5_012))
    )
    assert usage == {"input_tokens": 5_000, "output_tokens": 12, "total_tokens": 5_012}


def test_responses_endpoint_response_carries_cached_tokens():
    provider = OpenAIModelProvider("test-key")
    response = SimpleNamespace(
        output_text="ok", usage=_responses_usage(3_000), model="gpt-5.5", id="resp_1", created_at=0
    )
    client = MagicMock()
    client.responses.create.return_value = response
    with patch.object(OpenAIModelProvider, "client", new=client):
        result = provider._generate_with_responses_endpoint(
            "gpt-5.5", [{"role": "user", "content": "hi"}], temperature=1.0
        )
    assert result.usage["cached_input_tokens"] == 3_000


# --- Gemini ---------------------------------------------------------------------------------------------------------


def test_gemini_cached_content_token_count():
    metadata = genai_types.GenerateContentResponseUsageMetadata(
        prompt_token_count=5_000, candidates_token_count=12, cached_content_token_count=4_096
    )
    usage = GeminiModelProvider("test-key")._extract_usage(SimpleNamespace(usage_metadata=metadata))
    assert usage == {"input_tokens": 5_000, "output_tokens": 12, "total_tokens": 5_012, "cached_input_tokens": 4_096}


def test_gemini_without_cached_count_leaves_the_key_out():
    metadata = genai_types.GenerateContentResponseUsageMetadata(prompt_token_count=5_000, candidates_token_count=12)
    usage = GeminiModelProvider("test-key")._extract_usage(SimpleNamespace(usage_metadata=metadata))
    assert "cached_input_tokens" not in usage


# --- Claude ---------------------------------------------------------------------------------------------------------


def _anthropic_provider(usage):
    client = MagicMock()
    stream = MagicMock()
    stream.text_stream = ["ok"]
    stream.get_final_message.return_value = SimpleNamespace(usage=usage, stop_reason="end_turn")
    client.messages.stream.return_value.__enter__.return_value = stream
    provider = AnthropicProvider(api_key="test-key")
    provider._client = client
    return provider


def test_claude_cache_read_and_write_tokens():
    usage = AnthropicUsage(
        input_tokens=40, output_tokens=12, cache_read_input_tokens=4_000, cache_creation_input_tokens=300
    )
    response = _anthropic_provider(usage).generate_content("hi", "sonnet")
    assert response.usage == {
        "input_tokens": 40,
        "output_tokens": 12,
        "total_tokens": 52,
        "cached_input_tokens": 4_000,
        "cache_write_input_tokens": 300,
    }


def test_claude_without_cache_fields_leaves_the_keys_out():
    response = _anthropic_provider(AnthropicUsage(input_tokens=40, output_tokens=12)).generate_content("hi", "sonnet")
    assert response.usage == {"input_tokens": 40, "output_tokens": 12, "total_tokens": 52}


# --- tool output ----------------------------------------------------------------------------------------------------


def test_tool_metadata_shows_cached_input_tokens():
    reply = ModelResponse(content="ok", usage={"input_tokens": 9, "cached_input_tokens": 4_096})
    assert response_media_metadata(reply) == {"cached_input_tokens": 4_096}


def test_tool_metadata_without_cached_input_tokens():
    assert response_media_metadata(ModelResponse(content="ok", usage={"input_tokens": 9})) == {}


@pytest.mark.asyncio
async def test_chat_output_metadata_shows_cached_input_tokens(tmp_path):
    reply = ModelResponse(
        content="ok",
        usage={"input_tokens": 5_000, "cached_input_tokens": 4_096},
        model_name="gemini-3.8-flash",
        provider=ProviderType.GOOGLE,
    )
    with patch.object(GeminiModelProvider, "generate_content", return_value=reply):
        result = await ChatTool().execute(
            {
                "prompt": "hello",
                "working_directory_absolute_path": str(tmp_path),
                "model": "gemini-3.8-flash",
                "_model_context": ModelContext("gemini-3.8-flash"),
                "_resolved_model_name": "gemini-3.8-flash",
            }
        )
    assert json.loads(result[0].text)["metadata"]["cached_input_tokens"] == 4_096


def test_cache_write_tokens_from_openai_and_openrouter_usage():
    # Live 2026-10-04: gpt-6-luna on the Responses API reported input_tokens_details.cache_write_tokens on every file
    # request; OpenRouter reports prompt_tokens_details.cache_write_tokens. Both become cache_write_input_tokens.
    responses = ResponseUsage.model_validate(
        {
            "input_tokens": 22_847,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 22_844},
            "output_tokens": 8,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 22_855,
        }
    )
    usage = OpenAIModelProvider(api_key="test-key")._extract_usage(SimpleNamespace(usage=responses))
    assert usage["cached_input_tokens"] == 0 and usage["cache_write_input_tokens"] == 22_844

    chat = CompletionUsage.model_validate(
        {
            "prompt_tokens": 12_492,
            "completion_tokens": 9,
            "total_tokens": 12_501,
            "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 12_470},
        }
    )
    usage = OpenRouterProvider(api_key="test-key")._extract_usage(SimpleNamespace(usage=chat))
    assert usage["cache_write_input_tokens"] == 12_470


def test_cache_write_tokens_absent_leaves_the_key_out():
    usage = OpenAIModelProvider(api_key="test-key")._extract_usage(SimpleNamespace(usage=_responses_usage(cached=5)))
    assert "cache_write_input_tokens" not in usage


def test_tool_metadata_shows_cache_writes_too():
    response = ModelResponse(
        content="ok",
        usage={"input_tokens": 9, "cached_input_tokens": 0, "cache_write_input_tokens": 12_470},
        model_name="claude-sonnet-5-5",
        provider=ProviderType.ANTHROPIC,
    )
    assert response_media_metadata(response) == {"cached_input_tokens": 0, "cache_write_input_tokens": 12_470}
