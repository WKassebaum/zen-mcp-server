"""OpenAI encoder: PDFs as `file` parts on Chat Completions and `input_file` parts on the Responses API."""

import base64
import logging
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from providers.azure_openai import AzureOpenAIProvider
from providers.openai import OpenAIModelProvider
from providers.registry import ModelProviderRegistry
from providers.xai import XAIModelProvider
from utils.media import MediaKind, MediaNotSupportedError, classify_media

FIXTURES = Path(__file__).parent / "fixtures" / "media"
PDF = str(FIXTURES / "zebra.pdf")
PDF_B64 = base64.b64encode(Path(PDF).read_bytes()).decode()
DATA_URL = f"data:application/pdf;base64,{PDF_B64}"
CHAT_MODEL = "gpt-5.5"  # Chat Completions
RESPONSES_MODEL = "gpt-6-luna"  # use_openai_response_api: true
ATTACHED = [{"name": "zebra.pdf", "kind": "pdf", "bytes": 587, "transport": "inline"}]


def _media():
    return classify_media([PDF])[1]


def _provider(cls=OpenAIModelProvider):
    provider = cls("test-key")
    provider._client = MagicMock()  # never reach the real SDK client
    provider._client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ZEBRA-42"), finish_reason="stop")],
        model=CHAT_MODEL,
        id="chat-1",
        created=0,
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2, total_tokens=12),
    )
    provider._client.responses.create.return_value = SimpleNamespace(
        output_text="ZEBRA-42",
        usage=SimpleNamespace(input_tokens=10, output_tokens=2, total_tokens=12),
    )
    return provider


def _chat_request(provider):
    return provider._client.chat.completions.create.call_args.kwargs


def _responses_request(provider):
    return provider._client.responses.create.call_args.kwargs


def test_openai_declares_pdf_only():
    assert OpenAIModelProvider.MEDIA_KINDS == frozenset({MediaKind.PDF})


def test_chat_sends_the_pdf_as_a_file_part_before_the_prompt():
    provider = _provider()
    response = provider.generate_content("What code?", CHAT_MODEL, system_prompt="Be terse.", media=_media())
    messages = _chat_request(provider)["messages"]
    assert messages == [
        {"role": "system", "content": "Be terse."},
        {
            "role": "user",
            "content": [
                {"type": "file", "file": {"filename": "zebra.pdf", "file_data": DATA_URL}},
                {"type": "text", "text": "What code?"},
            ],
        },
    ]
    assert response.metadata["media_attached"] == ATTACHED


def test_responses_sends_the_pdf_as_an_input_file_part():
    provider = _provider()
    response = provider.generate_content("What code?", RESPONSES_MODEL, system_prompt="Be terse.", media=_media())
    assert _responses_request(provider)["input"] == [
        {"role": "user", "content": [{"type": "input_text", "text": "Be terse."}]},
        {
            "role": "user",
            "content": [
                {"type": "input_file", "filename": "zebra.pdf", "file_data": DATA_URL},
                {"type": "input_text", "text": "What code?"},
            ],
        },
    ]
    assert response.metadata["media_attached"] == ATTACHED
    assert response.metadata["endpoint"] == "responses"


def test_two_pdfs_keep_their_input_order(tmp_path):
    first, second = tmp_path / "b-first.pdf", tmp_path / "a-second.pdf"
    first.write_bytes(Path(PDF).read_bytes())
    second.write_bytes(Path(PDF).read_bytes().replace(b"ZEBRA", b"HORSE"))
    provider = _provider()
    provider.generate_content("Compare", CHAT_MODEL, media=classify_media([str(first), str(second)])[1])
    content = _chat_request(provider)["messages"][-1]["content"]
    assert [part.get("file", {}).get("filename") for part in content] == ["b-first.pdf", "a-second.pdf", None]
    assert (
        content[1]["file"]["file_data"]
        == "data:application/pdf;base64," + base64.b64encode(second.read_bytes()).decode()
    )


def test_images_follow_the_prompt_text_in_a_media_request():
    png = "data:image/png;base64,iVBORw0KGgo="
    provider = _provider()
    provider.generate_content("Compare", CHAT_MODEL, images=[png], media=_media())
    content = _chat_request(provider)["messages"][-1]["content"]
    assert [part["type"] for part in content] == ["file", "text", "image_url"]


def test_media_free_chat_request_is_unchanged():
    provider = _provider()
    response = provider.generate_content("hi", CHAT_MODEL, system_prompt="SYS")
    assert _chat_request(provider) == {
        "model": CHAT_MODEL,
        "messages": [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}],
        "stream": False,
    }
    assert "media_attached" not in response.metadata


def test_media_free_responses_request_is_unchanged():
    provider = _provider()
    response = provider.generate_content("hi", RESPONSES_MODEL, system_prompt="SYS")
    assert _responses_request(provider) == {
        "model": RESPONSES_MODEL,
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "SYS"}]},
            {"role": "user", "content": [{"type": "input_text", "text": "hi"}]},
        ],
        "reasoning": {"effort": "medium"},
        "store": False,
    }
    assert "media_attached" not in response.metadata


def test_empty_media_list_is_a_media_free_request():
    provider = _provider()
    response = provider.generate_content("hi", CHAT_MODEL, media=[])
    assert _chat_request(provider)["messages"] == [{"role": "user", "content": "hi"}]
    assert "media_attached" not in response.metadata


def test_xai_refuses_media_it_cannot_encode_before_any_call():
    # xAI takes PDFs since phase 3 (tests/test_media_xai.py); video it still cannot send.
    provider = _provider(XAIModelProvider)
    with pytest.raises(MediaNotSupportedError, match="otter.mp4"):
        provider.generate_content("What is shown?", "grok-4.6", media=classify_media([str(FIXTURES / "otter.mp4")])[1])
    provider._client.chat.completions.create.assert_not_called()
    provider._client.responses.create.assert_not_called()


def test_request_over_the_cap_is_refused_before_any_call():
    provider = _provider()
    with patch.object(OpenAIModelProvider, "MEDIA_REQUEST_MAX_BYTES", 100):
        with pytest.raises(MediaNotSupportedError, match="zebra.pdf"):
            provider.generate_content("What code?", CHAT_MODEL, media=_media())
    provider._client.chat.completions.create.assert_not_called()


def test_bytes_are_read_from_the_validated_source_path(tmp_path):
    real = tmp_path / "real.pdf"
    real.write_bytes(Path(PDF).read_bytes())
    (attachment,) = classify_media([str(real)])[1]
    moved = SimpleNamespace(
        path=str(tmp_path / "missing.pdf"),
        name="missing.pdf",
        kind=attachment.kind,
        mime_type=attachment.mime_type,
        size_bytes=attachment.size_bytes,
        source_path=attachment.source_path,
    )
    provider = _provider()
    provider.generate_content("q", CHAT_MODEL, media=[moved])
    part = _chat_request(provider)["messages"][-1]["content"][0]
    assert part == {"type": "file", "file": {"filename": "missing.pdf", "file_data": DATA_URL}}


@pytest.fixture
def azure_with_pdf_flag(monkeypatch):
    """An Azure provider whose cloned OpenAI capabilities claim PDF support (as they will after Task 8)."""
    monkeypatch.delenv("AZURE_OPENAI_ALLOWED_MODELS", raising=False)
    monkeypatch.setattr("providers.azure_openai.AzureOpenAI", MagicMock())
    template = OpenAIModelProvider.MODEL_CAPABILITIES[CHAT_MODEL]
    monkeypatch.setitem(OpenAIModelProvider.MODEL_CAPABILITIES, CHAT_MODEL, replace(template, supports_pdf=True))
    provider = AzureOpenAIProvider(
        api_key="test-key",
        azure_endpoint="https://example.openai.azure.com/",
        deployments={CHAT_MODEL: "prod-gpt55"},
    )
    provider._client = MagicMock()
    assert provider.get_capabilities(CHAT_MODEL).supports_pdf  # the clone really carries the flag
    return provider


def test_azure_clones_of_pdf_capable_models_are_not_routed_media(azure_with_pdf_flag):
    pdf = frozenset({MediaKind.PDF})
    assert ModelProviderRegistry._filter_models_for_media(azure_with_pdf_flag, [CHAT_MODEL], pdf) == []
    with pytest.raises(MediaNotSupportedError, match="zebra.pdf"):
        azure_with_pdf_flag.ensure_media_encodable(_media())


def test_azure_generate_content_refuses_media_before_any_call(azure_with_pdf_flag):
    with pytest.raises(MediaNotSupportedError, match="zebra.pdf"):
        azure_with_pdf_flag.generate_content("What code?", CHAT_MODEL, media=_media())
    azure_with_pdf_flag._client.chat.completions.create.assert_not_called()
    azure_with_pdf_flag._client.responses.create.assert_not_called()


def test_responses_request_log_carries_no_base64_payload(caplog):
    provider = _provider()
    with caplog.at_level(logging.INFO):
        provider.generate_content("What code?", RESPONSES_MODEL, media=_media())
    logged = "\n".join(r.getMessage() for r in caplog.records if "Responses API request" in r.getMessage())
    assert "input_file" in logged  # the request was logged ...
    assert PDF_B64 not in logged  # ... without the file
    assert PDF_B64[:60] in logged and "... [truncated]" in logged
    # The request actually sent still carries the whole file.
    assert _responses_request(provider)["input"][-1]["content"][0]["file_data"] == DATA_URL


def test_sanitizer_shortens_inline_images_and_files():
    long_image = "data:image/png;base64," + "A" * 500
    params = {
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": long_image},
                    {"type": "input_file", "filename": "zebra.pdf", "file_data": DATA_URL},
                    {"type": "input_image", "image_url": "https://example.com/a.png"},
                ],
            }
        ]
    }
    content = OpenAIModelProvider("test-key")._sanitize_for_logging(params)["input"][0]["content"]
    assert content[0]["image_url"] == long_image[:100] + "... [truncated]"
    assert content[1]["file_data"] == DATA_URL[:100] + "... [truncated]"
    assert content[1]["filename"] == "zebra.pdf"
    assert content[2]["image_url"] == "https://example.com/a.png"  # short values are kept
    assert params["input"][0]["content"][1]["file_data"] == DATA_URL  # the request itself is untouched
