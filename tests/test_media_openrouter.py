"""OpenRouter encoder: PDF, audio and video as Chat Completions parts (or their Responses API twins), read natively.

A request with media asks OpenRouter for its native PDF engine (``plugins``) and for router metadata (a header), and
fails loudly when the response shows OpenRouter parsed a file into text instead. Media-free requests are unchanged.
"""

import base64
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from providers.openrouter import OpenRouterProvider
from utils.media import MediaKind, MediaNotSupportedError, classify_media

FIXTURES = Path(__file__).parent / "fixtures" / "media"
PDF = str(FIXTURES / "zebra.pdf")
WAV = str(FIXTURES / "pelican.wav")
MP4 = str(FIXTURES / "otter.mp4")
PDF_B64 = base64.b64encode(Path(PDF).read_bytes()).decode()
WAV_B64 = base64.b64encode(Path(WAV).read_bytes()).decode()
MP4_B64 = base64.b64encode(Path(MP4).read_bytes()).decode()
PDF_PART = {"type": "file", "file": {"filename": "zebra.pdf", "file_data": f"data:application/pdf;base64,{PDF_B64}"}}
WAV_PART = {"type": "input_audio", "input_audio": {"data": WAV_B64, "format": "wav"}}
MP4_PART = {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{MP4_B64}"}}
PLUGINS = {"plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}]}
METADATA_HEADER = {"X-OpenRouter-Metadata": "enabled"}
CHAT_MODEL = "google/gemini-3.8-flash"  # Chat Completions
RESPONSES_MODEL = "openai/gpt-6-luna"  # use_openai_response_api: true
PARSED = (
    r"OpenRouter parsed zebra\.pdf into text instead of passing it to {model} natively; "
    r"zen only sends media to models that read it themselves"
)


def _media(*paths):
    return classify_media(list(paths or [PDF]))[1]


def _chat_response(annotations=None, **extra):
    message = SimpleNamespace(content="ZEBRA-42", annotations=annotations)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        model=CHAT_MODEL,
        id="gen-1",
        created=0,
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2, total_tokens=12),
        **extra,
    )


def _responses_response(annotations=(), **extra):
    output = [SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", annotations=annotations)])]
    return SimpleNamespace(
        output_text="ZEBRA-42",
        output=output,
        usage=SimpleNamespace(input_tokens=10, output_tokens=2, total_tokens=12),
        **extra,
    )


def _provider(chat=None, responses=None):
    provider = OpenRouterProvider("test-key")
    provider._client = MagicMock()  # never reach the real SDK client
    provider._client.chat.completions.create.return_value = chat or _chat_response()
    provider._client.responses.create.return_value = responses or _responses_response()
    return provider


def _chat_request(provider):
    provider._client.responses.create.assert_not_called()
    return provider._client.chat.completions.create.call_args.kwargs


def _responses_request(provider):
    provider._client.chat.completions.create.assert_not_called()
    return provider._client.responses.create.call_args.kwargs


def _no_call(provider):
    provider._client.chat.completions.create.assert_not_called()
    provider._client.responses.create.assert_not_called()


def _temperature(model):
    return OpenRouterProvider("test-key").get_capabilities(model).get_effective_temperature(0.3)


def _attachment(path, mime, kind=MediaKind.AUDIO, name=None):
    """An attachment with a chosen MIME type (classify_media only yields the MIME types of utils.media.MEDIA_TYPES)."""
    return SimpleNamespace(
        path=path,
        name=name or Path(path).name,
        kind=kind,
        mime_type=mime,
        size_bytes=Path(path).stat().st_size,
        source_path=path,
    )


def _mp3(tmp_path):
    path = tmp_path / "heron.mp3"
    path.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 400)  # an MPEG audio frame header, as _magic_matches expects
    return str(path)


def test_openrouter_declares_every_kind_and_its_limits():
    assert OpenRouterProvider.MEDIA_KINDS == frozenset(MediaKind)
    assert OpenRouterProvider.MEDIA_AUTO_ROUTING is True
    assert OpenRouterProvider.MEDIA_REQUEST_MAX_BYTES == 32_000_000
    assert OpenRouterProvider.PDF_TOKENS_PER_PAGE == 4_000


# --- Chat Completions: part shapes, order and request extras --------------------------------------------------


def test_pdf_is_a_file_part_before_the_prompt_with_the_native_engine_and_metadata_header():
    provider = _provider()
    response = provider.generate_content("What code?", CHAT_MODEL, system_prompt="Be terse.", media=_media())
    assert _chat_request(provider) == {
        "model": CHAT_MODEL,
        "messages": [
            {"role": "system", "content": "Be terse."},
            {"role": "user", "content": [PDF_PART, {"type": "text", "text": "What code?"}]},
        ],
        "stream": False,
        "temperature": _temperature(CHAT_MODEL),
        "extra_body": PLUGINS,
        "extra_headers": METADATA_HEADER,
    }
    assert response.content == "ZEBRA-42"
    assert response.metadata["media_attached"] == [
        {"name": "zebra.pdf", "kind": "pdf", "bytes": 587, "transport": "inline"}
    ]


def test_wav_is_an_input_audio_part_with_raw_base64_and_no_plugins():
    provider = _provider()
    response = provider.generate_content("What is said?", CHAT_MODEL, media=_media(WAV))
    request = _chat_request(provider)
    assert request["messages"] == [{"role": "user", "content": [WAV_PART, {"type": "text", "text": "What is said?"}]}]
    assert not WAV_PART["input_audio"]["data"].startswith("data:")
    assert request["extra_headers"] == METADATA_HEADER
    assert "extra_body" not in request  # the file-parser plugin is for PDFs only
    assert response.metadata["media_attached"] == [
        {"name": "pelican.wav", "kind": "audio", "bytes": Path(WAV).stat().st_size, "transport": "inline"}
    ]


def test_mp3_is_an_input_audio_part_in_mp3_format(tmp_path):
    mp3 = _mp3(tmp_path)
    provider = _provider()
    provider.generate_content("What is said?", CHAT_MODEL, media=_media(mp3))
    [part, _text] = _chat_request(provider)["messages"][-1]["content"]
    assert part == {
        "type": "input_audio",
        "input_audio": {"data": base64.b64encode(Path(mp3).read_bytes()).decode(), "format": "mp3"},
    }


def test_mp4_is_a_video_url_part_with_a_data_url_and_no_plugins():
    provider = _provider()
    provider.generate_content("What is shown?", CHAT_MODEL, media=_media(MP4))
    request = _chat_request(provider)
    assert request["messages"][-1]["content"] == [MP4_PART, {"type": "text", "text": "What is shown?"}]
    assert request["extra_headers"] == METADATA_HEADER
    assert "extra_body" not in request


def test_mixed_media_keeps_input_order_before_the_prompt_and_images_follow():
    png = "data:image/png;base64,iVBORw0KGgo="
    provider = _provider()
    provider.generate_content("Compare", CHAT_MODEL, images=[png], media=_media(MP4, PDF, WAV))
    request = _chat_request(provider)
    assert request["messages"][-1]["content"] == [
        MP4_PART,
        PDF_PART,
        WAV_PART,
        {"type": "text", "text": "Compare"},
        {"type": "image_url", "image_url": {"url": png}},
    ]
    assert request["extra_body"] == PLUGINS  # a PDF is among them
    assert request["extra_headers"] == METADATA_HEADER


@pytest.mark.parametrize(
    "mime, audio_format",
    [
        ("audio/mpeg", "mp3"),
        ("audio/wav", "wav"),
        ("audio/x-wav", "wav"),
        ("audio/flac", "flac"),
        ("audio/ogg", "ogg"),
        ("audio/mp4", "m4a"),
        ("audio/aac", "aac"),
    ],
)
def test_audio_format_comes_from_the_mime_type(mime, audio_format):
    provider = _provider()
    provider.generate_content("What is said?", CHAT_MODEL, media=[_attachment(WAV, mime)])
    part = _chat_request(provider)["messages"][-1]["content"][0]
    assert part == {"type": "input_audio", "input_audio": {"data": WAV_B64, "format": audio_format}}


def test_every_audio_mime_type_zen_detects_has_a_chat_format():
    from providers.openai_compatible import CHAT_AUDIO_FORMATS
    from utils.media import MEDIA_TYPES

    audio_mimes = {mime for kind, mime in MEDIA_TYPES.values() if kind is MediaKind.AUDIO}
    assert audio_mimes <= set(CHAT_AUDIO_FORMATS)


def test_unmapped_audio_mime_type_is_refused_before_any_call():
    provider = _provider()
    with pytest.raises(MediaNotSupportedError, match=r"crane\.aiff.*audio/x-aiff"):
        provider.generate_content(
            "What is said?", CHAT_MODEL, media=[_attachment(WAV, "audio/x-aiff", name="crane.aiff")]
        )
    _no_call(provider)


def _sparse_pdf(tmp_path, size):
    path = tmp_path / "big.pdf"
    with path.open("wb") as handle:
        handle.write(b"%PDF-1.4\n")
        handle.truncate(size)  # sparse: nothing real is written
    return str(path)


def test_media_over_32_mb_encoded_is_refused_before_any_call(tmp_path):
    media = _media(_sparse_pdf(tmp_path, 24_000_001))  # 32,000,004 bytes once base64-encoded
    provider = _provider()
    with pytest.raises(
        MediaNotSupportedError, match=r"openrouter takes media inline, in requests of at most .*big\.pdf"
    ):
        provider.generate_content("What code?", CHAT_MODEL, media=media)
    _no_call(provider)


def test_32_mb_encoded_still_fits(tmp_path):
    OpenRouterProvider("test-key").ensure_media_encodable(_media(_sparse_pdf(tmp_path, 24_000_000)))


# --- Media-free requests are unchanged ------------------------------------------------------------------------


def test_media_free_chat_request_is_unchanged():
    provider = _provider()
    response = provider.generate_content("hi", CHAT_MODEL, system_prompt="SYS")
    assert _chat_request(provider) == {
        "model": CHAT_MODEL,
        "messages": [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}],
        "stream": False,
        "temperature": _temperature(CHAT_MODEL),
    }
    assert "media_attached" not in response.metadata


def test_media_free_chat_request_with_an_image_is_unchanged():
    png = "data:image/png;base64,iVBORw0KGgo="
    provider = _provider()
    provider.generate_content("hi", CHAT_MODEL, images=[png], media=[])
    request = _chat_request(provider)
    assert set(request) == {"model", "messages", "stream", "temperature"}
    assert request["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "hi"}, {"type": "image_url", "image_url": {"url": png}}]}
    ]


def test_media_free_responses_request_is_unchanged():
    provider = _provider()
    effort = provider.get_capabilities(RESPONSES_MODEL).default_reasoning_effort or "medium"
    response = provider.generate_content("hi", RESPONSES_MODEL, system_prompt="SYS")
    assert _responses_request(provider) == {
        "model": RESPONSES_MODEL,
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "SYS"}]},
            {"role": "user", "content": [{"type": "input_text", "text": "hi"}]},
        ],
        "reasoning": {"effort": effort},
        "store": False,
    }
    assert "media_attached" not in response.metadata


# --- Fail loudly when OpenRouter parsed a file instead of passing it natively ----------------------------------

FILE_ANNOTATION = {"type": "file", "file": {"hash": "abc", "name": "zebra.pdf", "content": [{"type": "text"}]}}
PARSER_METADATA = {"pipeline": [{"type": "plugin", "name": "file-parser", "data": {"pages": 1}}]}


@pytest.mark.parametrize(
    "annotation",
    [FILE_ANNOTATION, SimpleNamespace(type="file", file=SimpleNamespace(hash="abc", name="zebra.pdf"))],
    ids=["dict", "object"],
)
def test_file_annotations_raise_without_a_retry(annotation):
    provider = _provider(chat=_chat_response(annotations=[annotation]))
    with pytest.raises(RuntimeError, match=PARSED.format(model=r"google/gemini-3\.8-flash")):
        provider.generate_content("What code?", CHAT_MODEL, media=_media())
    assert provider._client.chat.completions.create.call_count == 1  # neither retried nor resent without the PDF


def test_parser_stage_in_router_metadata_raises():
    provider = _provider(chat=_chat_response(openrouter_metadata=PARSER_METADATA))
    with pytest.raises(RuntimeError, match=PARSED.format(model=r"google/gemini-3\.8-flash")):
        provider.generate_content("What code?", CHAT_MODEL, media=_media())
    assert provider._client.chat.completions.create.call_count == 1


def test_parser_stage_is_read_from_the_sdk_model_extra():
    response = _chat_response()
    response.model_extra = {"openrouter_metadata": {"pipeline": [{"type": "plugin", "name": "file-parser"}]}}
    provider = _provider(chat=response)
    with pytest.raises(RuntimeError, match="OpenRouter parsed zebra.pdf into text"):
        provider.generate_content("What code?", CHAT_MODEL, media=_media())


def test_parse_error_names_every_pdf_when_no_annotation_names_one(tmp_path):
    second = tmp_path / "heron.pdf"
    second.write_bytes(Path(PDF).read_bytes())
    provider = _provider(chat=_chat_response(openrouter_metadata=PARSER_METADATA))
    with pytest.raises(RuntimeError, match=r"OpenRouter parsed zebra\.pdf, heron\.pdf into text"):
        provider.generate_content("Compare", CHAT_MODEL, media=_media(PDF, WAV, str(second)))


def test_clean_response_passes_with_media_attached_in_its_metadata():
    clean_metadata = {"pipeline": [{"type": "context_compression", "name": "context-compression"}]}
    citation = SimpleNamespace(type="url_citation", url_citation=SimpleNamespace(url="https://example.com"))
    provider = _provider(chat=_chat_response(annotations=[citation], openrouter_metadata=clean_metadata))
    response = provider.generate_content("What code?", CHAT_MODEL, media=_media(PDF, WAV))
    assert response.content == "ZEBRA-42"
    assert [record["name"] for record in response.metadata["media_attached"]] == ["zebra.pdf", "pelican.wav"]


def test_absent_annotations_and_metadata_mean_native():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ZEBRA-42"), finish_reason="stop")],
        model=CHAT_MODEL,
        id="gen-1",
        created=0,
        usage=None,
    )
    provider = _provider(chat=response)
    assert provider.generate_content("What code?", CHAT_MODEL, media=_media()).content == "ZEBRA-42"


def test_media_free_response_is_not_checked():
    # Without media there is nothing OpenRouter could have parsed, and no metadata was requested.
    provider = _provider(chat=_chat_response(annotations=[FILE_ANNOTATION], openrouter_metadata=PARSER_METADATA))
    assert provider.generate_content("hi", CHAT_MODEL).content == "ZEBRA-42"


# --- Responses API (OpenRouter models with use_openai_response_api) --------------------------------------------


def test_responses_model_gets_input_file_audio_and_video_parts_with_the_same_extras():
    provider = _provider()
    effort = provider.get_capabilities(RESPONSES_MODEL).default_reasoning_effort or "medium"
    response = provider.generate_content("Compare", RESPONSES_MODEL, media=_media(PDF, WAV, MP4))
    assert _responses_request(provider) == {
        "model": RESPONSES_MODEL,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": "zebra.pdf",
                        "file_data": f"data:application/pdf;base64,{PDF_B64}",
                    },
                    {"type": "input_audio", "input_audio": {"data": WAV_B64, "format": "wav"}},
                    {"type": "input_video", "video_url": f"data:video/mp4;base64,{MP4_B64}"},
                    {"type": "input_text", "text": "Compare"},
                ],
            }
        ],
        "reasoning": {"effort": effort},
        "store": False,
        "extra_body": PLUGINS,
        "extra_headers": METADATA_HEADER,
    }
    assert response.metadata["endpoint"] == "responses"
    assert [record["kind"] for record in response.metadata["media_attached"]] == ["pdf", "audio", "video"]


def test_responses_video_request_has_the_header_but_no_plugins():
    provider = _provider()
    provider.generate_content("What is shown?", RESPONSES_MODEL, media=_media(MP4))
    request = _responses_request(provider)
    assert request["extra_headers"] == METADATA_HEADER
    assert "extra_body" not in request


def test_responses_mp3_is_sent(tmp_path):
    provider = _provider()
    provider.generate_content("What is said?", RESPONSES_MODEL, media=_media(_mp3(tmp_path)))
    part = _responses_request(provider)["input"][-1]["content"][0]
    assert part["type"] == "input_audio" and part["input_audio"]["format"] == "mp3"


@pytest.mark.parametrize("mime", ["audio/flac", "audio/ogg", "audio/mp4", "audio/aac"])
def test_responses_refuses_audio_other_than_mp3_and_wav_before_any_call(mime):
    provider = _provider()
    with pytest.raises(MediaNotSupportedError, match=r"crane\.\w+.*mp3 or wav"):
        provider.generate_content(
            "What is said?", RESPONSES_MODEL, media=[_attachment(WAV, mime, name=f"crane.{mime.split('/')[1]}")]
        )
    _no_call(provider)


def test_responses_file_annotation_raises():
    provider = _provider(responses=_responses_response(annotations=[FILE_ANNOTATION]))
    with pytest.raises(RuntimeError, match=PARSED.format(model=r"openai/gpt-6-luna")):
        provider.generate_content("What code?", RESPONSES_MODEL, media=_media())
    assert provider._client.responses.create.call_count == 1


def test_responses_parser_stage_raises():
    provider = _provider(responses=_responses_response(openrouter_metadata=PARSER_METADATA))
    with pytest.raises(RuntimeError, match=PARSED.format(model=r"openai/gpt-6-luna")):
        provider.generate_content("What code?", RESPONSES_MODEL, media=_media())
    assert provider._client.responses.create.call_count == 1


def test_responses_request_log_carries_no_audio_or_video_payload(caplog):
    provider = _provider()
    with caplog.at_level(logging.INFO):
        provider.generate_content("Compare", RESPONSES_MODEL, media=_media(WAV, MP4))
    logged = "\n".join(r.getMessage() for r in caplog.records if "Responses API request" in r.getMessage())
    assert "input_audio" in logged and "input_video" in logged  # the request was logged ...
    assert WAV_B64 not in logged and MP4_B64 not in logged  # ... without the files
    content = _responses_request(provider)["input"][-1]["content"]
    assert content[0]["input_audio"]["data"] == WAV_B64  # the request actually sent still carries them
    assert content[1]["video_url"] == f"data:video/mp4;base64,{MP4_B64}"


# --- Through the real OpenAI SDK (httpx mock transport, no network) --------------------------------------------

CHAT_BODY = {
    "id": "gen-1",
    "object": "chat.completion",
    "created": 1,
    "model": CHAT_MODEL,
    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ZEBRA-42"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
}


def _http_provider(body):
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json=body)

    provider = OpenRouterProvider("test-key")
    provider._test_transport = httpx.MockTransport(handler)
    return provider, sent


def test_sdk_request_with_a_pdf_carries_plugins_and_both_header_sets():
    provider, sent = _http_provider(CHAT_BODY)
    provider.generate_content("What code?", CHAT_MODEL, media=_media())
    [request] = sent
    assert request.headers["X-OpenRouter-Metadata"] == "enabled"
    assert request.headers["X-Title"] == OpenRouterProvider.DEFAULT_HEADERS["X-Title"]  # attribution kept
    assert request.headers["HTTP-Referer"] == OpenRouterProvider.DEFAULT_HEADERS["HTTP-Referer"]
    body = json.loads(request.content)
    assert body["plugins"] == PLUGINS["plugins"]
    assert body["messages"][-1]["content"][0] == PDF_PART


def test_sdk_media_free_request_has_no_header_and_no_plugins():
    provider, sent = _http_provider(CHAT_BODY)
    provider.generate_content("hi", CHAT_MODEL, system_prompt="SYS")
    [request] = sent
    assert "X-OpenRouter-Metadata" not in request.headers
    assert request.headers["X-Title"] == OpenRouterProvider.DEFAULT_HEADERS["X-Title"]
    assert json.loads(request.content) == {
        "messages": [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}],
        "model": CHAT_MODEL,
        "stream": False,
        "temperature": _temperature(CHAT_MODEL),
    }


def test_sdk_parsed_response_raises():
    body = json.loads(json.dumps(CHAT_BODY))
    body["choices"][0]["message"]["annotations"] = [FILE_ANNOTATION]
    provider, sent = _http_provider(body)
    with pytest.raises(RuntimeError, match="OpenRouter parsed zebra.pdf into text"):
        provider.generate_content("What code?", CHAT_MODEL, media=_media())
    assert len(sent) == 1


def test_sdk_router_metadata_with_a_parser_stage_raises():
    body = {**CHAT_BODY, "openrouter_metadata": PARSER_METADATA}
    provider, sent = _http_provider(body)
    with pytest.raises(RuntimeError, match="OpenRouter parsed zebra.pdf into text"):
        provider.generate_content("What code?", CHAT_MODEL, media=_media())
    assert len(sent) == 1
