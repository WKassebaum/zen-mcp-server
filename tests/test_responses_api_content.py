"""Responses API requests: content parts (text, images, files), usage fields and the output cap."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from providers.openai import OpenAIModelProvider
from providers.openai_compatible import OpenAICompatibleProvider

MODEL = "gpt-6-luna"  # use_openai_response_api: true
PNG = "data:image/png;base64,iVBORw0KGgo="


def _provider():
    provider = OpenAIModelProvider("test-key")
    provider._client = MagicMock()
    provider._client.responses.create.return_value = SimpleNamespace(
        output_text="ok",
        # A SimpleNamespace, not a MagicMock: Chat field names (prompt_tokens, ...) really are missing
        usage=SimpleNamespace(input_tokens=12, output_tokens=5, total_tokens=17),
    )
    return provider


def _request(provider):
    return provider._client.responses.create.call_args.kwargs


def test_images_become_input_image_parts():
    provider = _provider()
    provider.generate_content("Describe", MODEL, images=[PNG])
    user = _request(provider)["input"][-1]
    assert user == {
        "role": "user",
        "content": [{"type": "input_text", "text": "Describe"}, {"type": "input_image", "image_url": PNG}],
    }


def test_chat_file_part_becomes_input_file():
    file_part = {"type": "file", "file": {"filename": "a.pdf", "file_data": "data:application/pdf;base64,JVBE"}}
    parts = OpenAICompatibleProvider._responses_content([file_part, {"type": "text", "text": "q"}], "input_text")
    assert parts == [
        {"type": "input_file", "filename": "a.pdf", "file_data": "data:application/pdf;base64,JVBE"},
        {"type": "input_text", "text": "q"},
    ]


def test_text_content_uses_the_given_text_type():
    assert OpenAICompatibleProvider._responses_content("hi", "output_text") == [{"type": "output_text", "text": "hi"}]
    assert OpenAICompatibleProvider._responses_content([{"type": "text", "text": "hi"}], "output_text") == [
        {"type": "output_text", "text": "hi"}
    ]


def test_unknown_part_type_is_refused_not_dropped():
    # input_audio and video_url became known part types with OpenRouter media (phase 4); audio_url is not one.
    with pytest.raises(ValueError, match="audio_url"):
        OpenAICompatibleProvider._responses_content([{"type": "audio_url", "audio_url": {}}], "input_text")


def test_usage_reads_the_responses_field_names():
    response = _provider().generate_content("Hello", MODEL)
    assert response.usage == {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17}


def test_usage_from_the_sdks_response_usage_object():
    from openai.types.responses import ResponseUsage

    usage = ResponseUsage(
        input_tokens=12,
        output_tokens=5,
        total_tokens=17,
        input_tokens_details={"cached_tokens": 0},
        output_tokens_details={"reasoning_tokens": 0},
    )
    assert _provider()._extract_usage(SimpleNamespace(usage=usage)) == {
        "input_tokens": 12,
        "output_tokens": 5,
        "total_tokens": 17,
        "cached_input_tokens": 0,  # reported as 0, so 0 rather than absent
    }


def test_chat_usage_field_names_still_win():
    usage = SimpleNamespace(prompt_tokens=3, completion_tokens=4, total_tokens=7)
    assert _provider()._extract_usage(SimpleNamespace(usage=usage)) == {
        "input_tokens": 3,
        "output_tokens": 4,
        "total_tokens": 7,
    }


def test_output_cap_is_sent_as_max_output_tokens():
    provider = _provider()
    provider.generate_content("Hello", MODEL, max_output_tokens=100)
    request = _request(provider)
    assert request["max_output_tokens"] == 100
    assert "max_completion_tokens" not in request


def test_text_only_request_is_unchanged():
    provider = _provider()
    provider.generate_content("Hello", MODEL, system_prompt="Be brief")
    request = _request(provider)
    assert request["input"] == [
        {"role": "user", "content": [{"type": "input_text", "text": "Be brief"}]},
        {"role": "user", "content": [{"type": "input_text", "text": "Hello"}]},
    ]
    assert set(request) == {"model", "input", "reasoning", "store"}
