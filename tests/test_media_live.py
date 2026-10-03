"""Live media probes through zen's providers. Costs a few cents. Run with -m integration."""

import os
from pathlib import Path

import pytest

from providers.anthropic import AnthropicProvider
from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from tests.live_keys import api_key
from tests.media_probe_matrix import PROBED
from utils.media import classify_media, estimate_media_tokens

FIXTURES = Path(__file__).parent / "fixtures" / "media"
CASES = {
    "pdf": ("zebra.pdf", "What code is written in this PDF? Reply with only the code.", ("ZEBRA-42",)),
    "audio": (
        "pelican.wav",
        "What code word and number are spoken? Reply with only them.",
        ("PELICAN", ("7", "SEVEN")),
    ),
    "video": ("otter.mp4", "What text is shown in this video? Reply with only that text.", ("OTTER-9",)),
}
GEMINI = [
    (model, kind) for (provider, model), kinds in PROBED.items() if provider == "google" for kind in sorted(kinds)
]
PROMPT_TOKEN_ALLOWANCE = 100  # the question and system prompt


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="needs GEMINI_API_KEY")
@pytest.mark.parametrize("model,kind", GEMINI)
def test_gemini_reads_media(model, kind):
    filename, question, markers = CASES[kind]
    media = classify_media([str(FIXTURES / filename)])[1]
    response = GeminiModelProvider(api_key=os.environ["GEMINI_API_KEY"]).generate_content(
        question, model, system_prompt="Answer tersely.", media=media
    )
    text = response.content.upper().replace(" ", "")
    # A marker is a string, or a tuple of acceptable alternatives. The audio probe must include the number,
    # not just "pelican", which also appears in the fixture's filename.
    assert all(
        any(alt in text for alt in marker) if isinstance(marker, tuple) else marker in text for marker in markers
    ), response.content
    # The estimate reserved from the text budget (utils/media.py) must not undercount real usage.
    input_tokens = response.usage.get("input_tokens")
    estimate = estimate_media_tokens(media)
    assert (
        input_tokens is None or input_tokens <= estimate + PROMPT_TOKEN_ALLOWANCE
    ), f"{model}/{kind}: {input_tokens} input tokens, media estimate {estimate} + {PROMPT_TOKEN_ALLOWANCE}"


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="needs GEMINI_API_KEY")
def test_gemini_reads_media_uploaded_to_the_files_api(monkeypatch):
    # The probes above all go inline; force the Files API path once so upload, polling and file_data are live-tested.
    monkeypatch.setattr(GeminiModelProvider, "INLINE_MEDIA_MAX_BYTES", 0)
    provider = GeminiModelProvider(api_key=os.environ["GEMINI_API_KEY"])
    filename, question, markers = CASES["video"]
    media = classify_media([str(FIXTURES / filename)])[1]
    response = provider.generate_content(question, "gemini-3.8-flash", system_prompt="Answer tersely.", media=media)
    try:
        (record,) = response.metadata["media_attached"]
        assert record["transport"] == "uploaded" and record["file_name"].startswith("files/"), record
        assert all(marker in response.content.upper().replace(" ", "") for marker in markers), response.content
    finally:
        # zen leaves uploads to Google's 48 h expiry; this test removes its own.
        for record in response.metadata["media_attached"]:
            if record.get("file_name"):
                provider.client.files.delete(name=record["file_name"])


# Claude and OpenAI take media inline only (PDF in phase 2). Keys come from the environment or zen's own
# config (tests/live_keys.py), never printed.
INLINE_PROVIDERS = {
    "anthropic": (AnthropicProvider, "ANTHROPIC_API_KEY"),
    "openai": (OpenAIModelProvider, "OPENAI_API_KEY"),
}
INLINE = [
    (provider, model, kind)
    for (provider, model), kinds in PROBED.items()
    if provider in INLINE_PROVIDERS
    for kind in sorted(kinds)
]


@pytest.mark.integration
@pytest.mark.parametrize("provider_name,model,kind", INLINE)
def test_inline_provider_reads_media(provider_name, model, kind):
    provider_cls, key_env = INLINE_PROVIDERS[provider_name]
    key = api_key(key_env)
    if not key:
        pytest.skip(f"needs {key_env}")
    filename, question, markers = CASES[kind]
    media = classify_media([str(FIXTURES / filename)])[1]
    response = provider_cls(api_key=key).generate_content(question, model, system_prompt="Answer tersely.", media=media)
    text = response.content.upper().replace(" ", "")
    assert all(
        any(alt in text for alt in marker) if isinstance(marker, tuple) else marker in text for marker in markers
    ), response.content
    assert response.metadata["media_attached"][0]["transport"] == "inline"
    # The provider's own page rate must not undercount real usage.
    input_tokens = response.usage.get("input_tokens")
    estimate = estimate_media_tokens(media, provider_cls.PDF_TOKENS_PER_PAGE)
    assert (
        input_tokens is None or input_tokens <= estimate + PROMPT_TOKEN_ALLOWANCE
    ), f"{model}/{kind}: {input_tokens} input tokens, media estimate {estimate} + {PROMPT_TOKEN_ALLOWANCE}"
