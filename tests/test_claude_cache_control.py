"""Claude gets a prompt-cache breakpoint at the end of the attached media, on media requests only.

- Native Anthropic: ``cache_control: {"type": "ephemeral"}`` on the last document block, so the system prompt and
  the PDFs are cached and the changing text after them is not.
- OpenRouter ``anthropic/*``: the chat schema takes ``cache_control`` on text parts only, so a short fixed text part
  right after the last file part carries it, and the prompt text follows in its own part.
- No marker on media-free requests or on other models.
"""

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from providers.anthropic import AnthropicProvider
from providers.openrouter import CLAUDE_CACHE_BREAKPOINT_TEXT, OpenRouterProvider
from utils.media import classify_media

FIXTURES = Path(__file__).parent / "fixtures" / "media"
PDF = str(FIXTURES / "zebra.pdf")
EPHEMERAL = {"type": "ephemeral"}
IMAGE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _pdf_copy(tmp_path, name, marker):
    path = tmp_path / name
    path.write_bytes(Path(PDF).read_bytes().replace(b"ZEBRA", marker))
    return str(path)


def _document_block(path):
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}


# --- native Anthropic -----------------------------------------------------------------------------------------------


def _anthropic():
    client = MagicMock()
    stream = MagicMock()
    stream.text_stream = ["ok"]
    stream.get_final_message.return_value = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=10, output_tokens=2), stop_reason="end_turn"
    )
    client.messages.stream.return_value.__enter__.return_value = stream
    provider = AnthropicProvider(api_key="test-key")
    provider._client = client
    return provider


def _anthropic_content(provider):
    messages = provider._client.messages.stream.call_args.kwargs["messages"]
    assert len(messages) == 1
    return messages[0]["content"]


def test_native_pdf_only_marks_the_document_block():
    provider = _anthropic()
    provider.generate_content("What code?", "sonnet", system_prompt="Be terse.", media=classify_media([PDF])[1])
    assert _anthropic_content(provider) == [
        {**_document_block(PDF), "cache_control": EPHEMERAL},
        {"type": "text", "text": "What code?"},
    ]
    assert provider._client.messages.stream.call_args.kwargs["system"] == "Be terse."


def test_native_two_pdfs_mark_only_the_last(tmp_path):
    first, second = _pdf_copy(tmp_path, "a.pdf", b"HORSE"), _pdf_copy(tmp_path, "b.pdf", b"TIGER")
    provider = _anthropic()
    provider.generate_content("Compare", "sonnet", media=classify_media([first, second])[1])
    assert _anthropic_content(provider) == [
        _document_block(first),
        {**_document_block(second), "cache_control": EPHEMERAL},
        {"type": "text", "text": "Compare"},
    ]


def test_native_pdf_plus_image_marks_the_document_not_the_image():
    provider = _anthropic()
    provider.generate_content("Compare", "sonnet", images=[IMAGE], media=classify_media([PDF])[1])
    content = _anthropic_content(provider)
    assert content[0] == {**_document_block(PDF), "cache_control": EPHEMERAL}
    assert content[1] == {"type": "text", "text": "Compare"}
    assert content[2]["type"] == "image" and "cache_control" not in content[2]
    assert len(content) == 3


def test_native_media_free_request_has_no_marker():
    provider = _anthropic()
    provider.generate_content("hello", "sonnet", system_prompt="Be terse.")
    assert _anthropic_content(provider) == [{"type": "text", "text": "hello"}]


def test_native_image_only_request_has_no_marker():
    provider = _anthropic()
    provider.generate_content("What is this?", "sonnet", images=[IMAGE])
    assert all("cache_control" not in block for block in _anthropic_content(provider))


# --- OpenRouter -----------------------------------------------------------------------------------------------------


def _openrouter():
    provider = OpenRouterProvider("test-key")
    provider._client = MagicMock()
    provider._client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", annotations=None), finish_reason="stop")],
        model="m",
        id="gen-1",
        created=0,
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2, total_tokens=12),
    )
    return provider


def _openrouter_content(provider):
    messages = provider._client.chat.completions.create.call_args.kwargs["messages"]
    return messages[-1]["content"]


def _file_part(path):
    data = base64.b64encode(Path(path).read_bytes()).decode()
    name = Path(path).name
    return {"type": "file", "file": {"filename": name, "file_data": f"data:application/pdf;base64,{data}"}}


def test_breakpoint_text_is_short_and_fixed():
    assert CLAUDE_CACHE_BREAKPOINT_TEXT.strip() and len(CLAUDE_CACHE_BREAKPOINT_TEXT) <= 60


def test_openrouter_anthropic_gets_a_marked_text_part_after_the_last_file(tmp_path):
    first, second = _pdf_copy(tmp_path, "a.pdf", b"HORSE"), _pdf_copy(tmp_path, "b.pdf", b"TIGER")
    provider = _openrouter()
    provider.generate_content("Compare", "anthropic/claude-sonnet-5.5", media=classify_media([first, second])[1])
    assert _openrouter_content(provider) == [
        _file_part(first),
        _file_part(second),
        {"type": "text", "text": CLAUDE_CACHE_BREAKPOINT_TEXT, "cache_control": EPHEMERAL},
        {"type": "text", "text": "Compare"},
    ]


def test_openrouter_anthropic_marker_is_the_same_on_every_turn():
    provider = _openrouter()
    provider.generate_content("Turn one", "anthropic/claude-sonnet-5.5", media=classify_media([PDF])[1])
    first = _openrouter_content(provider)
    provider.generate_content("Turn two, longer", "anthropic/claude-sonnet-5.5", media=classify_media([PDF])[1])
    second = _openrouter_content(provider)
    assert first[:2] == second[:2]  # the file part and the marked text part
    assert first[2] != second[2]


def test_openrouter_other_models_get_no_marker():
    provider = _openrouter()
    provider.generate_content("What code?", "google/gemini-3.8-flash", media=classify_media([PDF])[1])
    assert _openrouter_content(provider) == [_file_part(PDF), {"type": "text", "text": "What code?"}]


def test_openrouter_anthropic_media_free_request_is_unchanged():
    provider = _openrouter()
    provider.generate_content("hello", "anthropic/claude-sonnet-5.5", system_prompt="Be terse.")
    messages = provider._client.chat.completions.create.call_args.kwargs["messages"]
    assert messages == [{"role": "system", "content": "Be terse."}, {"role": "user", "content": "hello"}]
