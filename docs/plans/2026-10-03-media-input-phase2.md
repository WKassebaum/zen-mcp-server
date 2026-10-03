# Media Input Phase 2 (Claude and OpenAI) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** PDF files passed through `--files` / `absolute_file_paths` / `relevant_files` reach Claude models (native Anthropic API) and OpenAI models (Chat Completions and Responses API) as native documents, and the MCP server registers the native Anthropic provider.

**Architecture:** Phase 1 built the provider-agnostic pipeline: classification (`utils/media.py`), capability flags, routing, validation and the tool call sites that pass `media=` to `generate_content`. This phase adds two encoders (Anthropic `document` blocks; OpenAI `file` parts on Chat Completions and `input_file` parts on the Responses API), a per-provider inline request cap and PDF token rate on the provider contract, provider hints for the new keys, and live probes that set the catalog flags. Design: `docs/plans/2026-09-26-media-input-design.md` (phase list in section 5). Audio and video stay Gemini-only: the design's capability matrix records that Anthropic and OpenAI catalog models take neither.

**Tech Stack:** Python 3.12, pytest, `anthropic` SDK (already a dependency), `openai` SDK, the MCP server in `server.py`.

---

## Ground rules for the engineer

- **Work in the worktree:** `/Users/wrk/WorkDev/MCP-Dev/zen-media-phase2`, branch `feat/media-input-phase2`. Never edit `/Users/wrk/WorkDev/MCP-Dev/zen-cli`: that checkout backs the user's live zen MCP server and CLI.
- **Python:** `/Users/wrk/WorkDev/MCP-Dev/zen-cli/.zen_venv/bin/python` (the worktree has no venv of its own; run it from the worktree root so the worktree's modules load first). Do not `pip install` anything.
- **Test command:** `/Users/wrk/WorkDev/MCP-Dev/zen-cli/.zen_venv/bin/python -m pytest tests/ -q -m "not integration" -p no:cacheprovider` (no `-x`).
- **Baseline:** 1215 passed, 6 skipped, 3 failed. The 3 failures are pre-existing: `tests/test_alias_target_restrictions.py::…gemini…`. Any other failure is yours.
- **Lint before each commit:** `ruff check . --fix && black . && isort .` (from `PATH`; not in the venv). `ruff` targets py39 with `UP` rules: in files with `from __future__ import annotations` write `X | None`.
- **No network in unit tests.** Mock clients by assigning `provider._client = MagicMock()` (both providers create their SDK client lazily through `_client`).
- **Keys:** never print, log or `source` an API key or a `.env` file. Live steps (Tasks 8–9) are run by the controller, not by implementers.
- **No silent drops:** media must reach the model or fail with an error naming the file. If you find a path where it could be ignored, stop and report it.
- **Media-free requests stay byte for byte the same** on every provider. Every encoder task has a test for it.
- **Commit trailer:** every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Batches

| Batch | Tasks | Network |
|---|---|---|
| A | 1 provider contract (cap, PDF rate) · 2 native Anthropic in the MCP server · 3 Responses API content parts and usage | none |
| B | 4 Anthropic encoder · 5 OpenAI encoder · 6 provider hints | none |
| C | 7 probe script for Anthropic/OpenAI · 8 live probes and catalog flags (controller) · 9 live tests, docs, smoke test (controller) | live |

---

### Task 1: Provider contract — inline request cap and PDF token rate

**Why:** Anthropic and OpenAI take media inline only, inside a request-size limit, and media travels base64-encoded (4/3 of the file size). Phase 1's only size check is Gemini's per-file 2 GB limit. Separately, `estimate_media_tokens` uses Gemini's 560 tokens per PDF page; Claude and OpenAI turn each page into extracted text plus a page image (design: about 1.5k tokens per page or more), so the text-file budget must use the provider's own rate.

**Files:**
- Modify: `providers/base.py` (class attributes next to `MEDIA_KINDS`; `ensure_media_encodable`)
- Modify: `utils/media.py` (`base64_size`, `check_inline_media_size`, `pdf_tokens_per_page`; `estimate_media_tokens` signature)
- Modify: `tools/shared/base_tool.py:1092-1095`, `tools/workflow/workflow_mixin.py:394-414` (pass the provider's rate)
- Test: `tests/test_media_provider_limits.py` (new)

**Step 1: Write the failing tests**

```python
"""Per-provider inline request caps and PDF token rates (media input phase 2)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.xai import XAIModelProvider
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

PDF = str(Path(__file__).parent / "fixtures" / "media" / "zebra.pdf")  # 587 bytes, one page


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


def test_provider_without_a_cap_skips_the_inline_check():
    assert GeminiModelProvider.MEDIA_REQUEST_MAX_BYTES is None  # Gemini uploads to its Files API instead


def test_estimate_uses_the_given_pdf_rate():
    assert estimate_media_tokens(_pdf()) == PDF_TOKENS_PER_PAGE
    assert estimate_media_tokens(_pdf(), pdf_tokens_per_page=3_000) == 3_000


def test_pdf_rate_comes_from_the_model_contexts_provider():
    context = SimpleNamespace(provider=SimpleNamespace(PDF_TOKENS_PER_PAGE=3_000))
    assert pdf_tokens_per_page(context) == 3_000


def test_pdf_rate_defaults_when_provider_sets_none_or_context_is_missing():
    assert pdf_tokens_per_page(None) == PDF_TOKENS_PER_PAGE
    assert pdf_tokens_per_page(SimpleNamespace(provider=SimpleNamespace(PDF_TOKENS_PER_PAGE=None))) == PDF_TOKENS_PER_PAGE
```

Add one call-site test (same file) proving the simple-tool reserve uses the provider's rate. Spy on `utils.media.estimate_media_tokens` (the call sites import it at call time, so patching the module attribute works):

```python
import utils.media
from tools.chat import ChatTool
from utils.model_context import ModelContext


@pytest.mark.asyncio
async def test_text_budget_reserve_uses_the_providers_pdf_rate(tmp_path):
    from providers.shared import ModelResponse, ProviderType

    reply = ModelResponse(content="ok", usage={}, model_name="gemini-3.8-flash", provider=ProviderType.GOOGLE)
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
                "model": "gemini-3.8-flash",
                "_model_context": ModelContext("gemini-3.8-flash"),
                "_resolved_model_name": "gemini-3.8-flash",
            }
        )
    assert spy.call_args.args[1] == 1_234
```

If `GeminiModelProvider` turns out to be awkward for the spy test, any provider whose `MEDIA_KINDS` you patch to include PDF works; keep the assertion on the rate.

**Step 2: Run them — expect ImportError / AttributeError** (`base64_size`, `MEDIA_REQUEST_MAX_BYTES`, … do not exist yet).

**Step 3: Implement**

`providers/base.py`, under `MEDIA_KINDS`:

```python
    # Largest total of base64-encoded media one request may carry inline (None: not checked here; Gemini
    # uploads larger media to its Files API). Checked by ensure_media_encodable before any API call.
    MEDIA_REQUEST_MAX_BYTES: ClassVar[Optional[int]] = None
    # Estimated input tokens per PDF page, reserved from the text budget (None: utils.media.PDF_TOKENS_PER_PAGE).
    PDF_TOKENS_PER_PAGE: ClassVar[Optional[int]] = None
```

In `ensure_media_encodable`, after the `unsupported` check (so an unsupported kind is reported first):

```python
        if self.MEDIA_REQUEST_MAX_BYTES is not None:
            check_inline_media_size(media, self.MEDIA_REQUEST_MAX_BYTES, self.get_provider_type().value)
```

(and add `check_inline_media_size` to that method's local import).

`utils/media.py`, near `check_media_sizes`:

```python
def base64_size(size_bytes: int) -> int:
    """Length of the base64 encoding of ``size_bytes`` raw bytes: inline media travels encoded."""
    return 4 * math.ceil(size_bytes / 3)


def check_inline_media_size(media: Iterable[MediaAttachment], max_request_bytes: int, provider_name: str) -> None:
    """Fail fast when the media, base64-encoded, would not fit in one request to a provider that only takes it inline."""
    media = list(media)
    encoded = sum(base64_size(a.size_bytes) for a in media)
    if encoded > max_request_bytes:
        names = ", ".join(f"{a.name} ({format_size(a.size_bytes)})" for a in media)
        raise MediaNotSupportedError(
            f"{provider_name} takes media inline, in requests of at most {format_size(max_request_bytes)}; "
            f"these files take {format_size(encoded)} once base64-encoded: {names}. "
            f"Gemini models take larger media (up to {format_size(MEDIA_MAX_BYTES)} per file)."
        )


def pdf_tokens_per_page(model_context: Any) -> int:
    """The PDF page rate of the model context's provider, or PDF_TOKENS_PER_PAGE when it sets none."""
    provider = getattr(model_context, "provider", None) if model_context is not None else None
    rate = getattr(provider, "PDF_TOKENS_PER_PAGE", None)
    # MagicMock contexts in older tests return mocks here: only a real positive int counts
    return rate if isinstance(rate, int) and not isinstance(rate, bool) and rate > 0 else PDF_TOKENS_PER_PAGE
```

`estimate_media_tokens(media, pdf_tokens_per_page: int = PDF_TOKENS_PER_PAGE)` uses the parameter in place of the constant. Name the parameter differently from the helper function if it shadows it inside the module (e.g. `page_rate`), and update the test call accordingly.

Call sites:

```python
# tools/shared/base_tool.py (_prepare_file_content_for_prompt)
        from utils.media import classify_media, estimate_media_tokens, media_prompt_section, pdf_tokens_per_page

        request_files, media = classify_media(request_files)
        if media:
            rate = pdf_tokens_per_page(model_context or getattr(self, "_model_context", None))
            effective_max_tokens -= estimate_media_tokens(media, rate)
```

```python
# tools/workflow/workflow_mixin.py (_force_embed_files_for_expert_analysis)
        max_tokens = max(2_000, max_tokens - estimate_media_tokens(media, pdf_tokens_per_page(current_model_context)))
```

**Step 4: Run the new tests, then the full suite.** Expected: new tests pass; suite at baseline + new tests.

**Step 5: Commit** — `feat(media): per-provider inline request cap and PDF token rate`

---

### Task 2: Register the native Anthropic provider in the MCP server

**Why (user decision, 2026-10-03):** `server.configure_providers()` never registers `AnthropicProvider` (only the CLI does, `src/zen_cli/main.py:167-170`), so in MCP Claude resolves only through OpenRouter and the dash-form native IDs (`claude-opus-5-5`, …) are "not available". The user chose native registration: `opus` / `fable` / `sonnet` move from OpenRouter to native Anthropic billing in MCP. Auto-mode text routing does not change: `PROVIDER_PRIORITY_ORDER` puts xAI and Google before Anthropic.

**Files:**
- Modify: `server.py` (`configure_providers`)
- Modify: `.env.example` (document `ANTHROPIC_API_KEY` next to the other native keys)
- Modify: `docs/plans/BACKLOG.md` (delete the entry "MCP server does not register the native Anthropic provider")
- Test: `tests/test_server_anthropic_provider.py` (new)

**Step 1: Write the failing tests**

Isolate the environment and registry the way `tests/test_listmodels.py` does (`_clear_providers()` unregisters every `ProviderType` and resets `utils.model_restrictions._restriction_service`), and use `patch.dict(os.environ, {...}, clear=True)`. Cover:

1. Only `ANTHROPIC_API_KEY` set → `configure_providers()` does not raise; `ProviderType.ANTHROPIC in ModelProviderRegistry.get_available_providers()`; `ModelProviderRegistry.get_provider_for_model("claude-opus-5-5")` is an `AnthropicProvider`.
2. `ANTHROPIC_API_KEY` and `OPENROUTER_API_KEY` set → `get_provider_for_model("opus")` is an `AnthropicProvider` (native wins over OpenRouter).
3. Auto-mode routing is unchanged for the usual key set: with `XAI_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY` set, record `ModelProviderRegistry.get_preferred_fallback_model(category)` for every `ToolModelCategory`; then add `ANTHROPIC_API_KEY`, reconfigure, and assert the same three picks.
4. No keys at all → the `ValueError` message lists `ANTHROPIC_API_KEY`.

Restore the registry after each test (re-run the module's `_clear_providers()`); `tests/conftest.py`'s autouse fixture re-registers Google/OpenAI/xAI for later tests.

**Step 2: Run — expect failures** (1, 2 and 4 fail; 3 passes today and must keep passing).

**Step 3: Implement** in `configure_providers()`, mirroring the OpenAI key block:

```python
    # Check for Anthropic API key
    anthropic_key = get_env("ANTHROPIC_API_KEY")
    if anthropic_key and anthropic_key != "your_anthropic_api_key_here":
        valid_providers.append("Anthropic")
        has_native_apis = True
        logger.info("Anthropic API key found - Claude models available natively")
```

register it in the native block (after Gemini, before OpenAI, matching `PROVIDER_PRIORITY_ORDER`):

```python
        if anthropic_key and anthropic_key != "your_anthropic_api_key_here":
            ModelProviderRegistry.register_provider(ProviderType.ANTHROPIC, AnthropicProvider)
            registered_providers.append(ProviderType.ANTHROPIC.value)
```

import `AnthropicProvider` with the other provider imports at the top of the function, add `"ANTHROPIC_API_KEY"` to `api_keys_to_check`, and add `"- ANTHROPIC_API_KEY for Claude models\n"` to the no-keys `ValueError`. In `.env.example`, add a commented `ANTHROPIC_API_KEY=your_anthropic_api_key_here` line in the native-keys section, in the style of its neighbours.

**Step 4: Run the new tests and the full suite.** Watch `tests/test_listmodels.py` and `tests/test_auto_mode*`: conftest gives every test dummy keys; if a test now sees Anthropic models it did not expect, check whether it sets `ANTHROPIC_API_KEY` itself before changing any assertion, and report rather than loosen an assertion you do not understand.

**Step 5: Commit** — `feat(server): register the native Anthropic provider in the MCP server`

---

### Task 3: Responses API — content parts, usage, output cap

**Why:** the Responses path (`providers/openai_compatible.py:_generate_with_responses_endpoint`) carries the default OpenAI traffic (gpt-6-astra/sol/luna and the `-pro` models). It wraps every message's `content` in one `input_text` part, so a list (text plus images today, plus files in Task 5) becomes `{"type": "input_text", "text": [...]}`, which the API rejects: images on gpt-6 are broken today. It also reports input/output usage as 0 (it reads Chat field names) and would crash on a non-empty output cap (`max_completion_tokens` is not a `Responses.create` parameter). The live PDF probes in Task 8 need real usage numbers. All three are listed under "Responses API path gaps" in `docs/plans/BACKLOG.md`.

**Files:**
- Modify: `providers/openai_compatible.py` (`_generate_with_responses_endpoint`, `_extract_usage`)
- Modify: `docs/plans/BACKLOG.md` ("Responses API path gaps": drop the usage and output-cap bullets; keep the system-role and multi-turn bullets)
- Test: `tests/test_responses_api_content.py` (new)

**Step 1: Write the failing tests** using `OpenAIModelProvider("test-key")` with `provider._client = MagicMock()` and model `gpt-6-luna` (`use_openai_response_api: true`). Make `client.responses.create` return an object with `output_text="ok"` and a `usage` built from `types.SimpleNamespace(input_tokens=12, output_tokens=5, total_tokens=17)` (a SimpleNamespace, not a MagicMock, so missing Chat field names really are missing).

1. Images: `generate_content("Describe", "gpt-6-luna", images=["data:image/png;base64,iVBORw0KGgo="])` → the user input's `content` is `[{"type": "input_text", "text": "Describe"}, {"type": "input_image", "image_url": "data:image/png;base64,iVBORw0KGgo="}]`. (Check how `_process_image` treats a data URL first; if it validates the bytes, use a real tiny PNG, e.g. one written by the test.)
2. A Chat `file` part converts to `input_file` with the same `filename` / `file_data`: call the conversion helper directly with `[{"type": "file", "file": {"filename": "a.pdf", "file_data": "data:application/pdf;base64,JVBE"}}, {"type": "text", "text": "q"}]`.
3. An unknown part type raises `ValueError` naming it (never dropped).
4. Usage: `response.usage == {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17}`.
5. Output cap: `generate_content(..., max_output_tokens=100)` → `responses.create` got `max_output_tokens=100` and no `max_completion_tokens`.
6. Text-only requests are unchanged: the system and user inputs are still single `input_text` parts with the same text as before.

**Step 2: Run — expect 1, 4 and 5 to fail.**

**Step 3: Implement**

```python
    @staticmethod
    def _responses_content(content, text_type: str) -> list[dict]:
        """Chat Completions message content as Responses API parts (text, images and files)."""
        if isinstance(content, str):
            return [{"type": text_type, "text": content}]
        parts = []
        for part in content:
            part_type = part.get("type")
            if part_type == "text":
                parts.append({"type": text_type, "text": part["text"]})
            elif part_type == "image_url":
                parts.append({"type": "input_image", "image_url": part["image_url"]["url"]})
            elif part_type == "file":
                parts.append({"type": "input_file", **part["file"]})
            else:
                raise ValueError(f"Responses API request: unsupported content part type {part_type!r}")
        return parts
```

Use it in the message loop: system and user messages → `self._responses_content(content, "input_text")`; assistant → `self._responses_content(content, "output_text")`. Replace `completion_params["max_completion_tokens"]` with `completion_params["max_output_tokens"]`. In `_extract_usage`, read the Chat names and fall back to the Responses names:

```python
        if hasattr(response, "usage") and response.usage:
            u = response.usage
            input_tokens = getattr(u, "prompt_tokens", None)
            if input_tokens is None:
                input_tokens = getattr(u, "input_tokens", 0)
            output_tokens = getattr(u, "completion_tokens", None)
            if output_tokens is None:
                output_tokens = getattr(u, "output_tokens", 0)
            usage["input_tokens"] = input_tokens or 0
            usage["output_tokens"] = output_tokens or 0
            usage["total_tokens"] = getattr(u, "total_tokens", 0) or 0
```

**Step 4: Run the new tests and the full suite** (watch `tests/test_responses_api_output_text.py` and `tests/test_openai_provider.py`; cassette replays must still pass).

**Step 5: Commit** — `fix(openai): send images and files on the Responses API; read its usage fields`

---

### Task 4: Anthropic PDF encoder

**Files:**
- Modify: `providers/anthropic.py`
- Test: `tests/test_media_anthropic.py` (new)

**Request shape** (Anthropic Messages API): one user message whose content is the PDF `document` blocks first, then the prompt text, then any images (as today). The system prompt stays in `params["system"]`. No `cache_control` in this phase (it costs 1.25x on the cached prefix and pays off only with continuation re-attach, which is phase 5).

```python
{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "<base64>"}}
```

**Step 1: Write the failing tests.** Build the stream mock once:

```python
def _client(text="ZEBRA-42"):
    client = MagicMock()
    stream = MagicMock()
    stream.text_stream = [text]
    stream.get_final_message.return_value = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=1500, output_tokens=4), stop_reason="end_turn"
    )
    client.messages.stream.return_value.__enter__.return_value = stream
    return client
```

1. `provider.generate_content("What code?", "sonnet", system_prompt="Be terse.", media=classify_media([PDF])[1])` → `client.messages.stream.call_args.kwargs`: `messages[0]["content"]` is `[document_block, {"type": "text", "text": "What code?"}]` with `data == base64.b64encode(Path(PDF).read_bytes()).decode()`; `system == "Be terse."`.
2. Two PDFs keep their input order (copy the fixture to `tmp_path` under two names).
3. `response.metadata["media_attached"] == [{"name": "zebra.pdf", "kind": "pdf", "bytes": 587, "transport": "inline"}]`.
4. Media-free request: `messages[0]["content"] == [{"type": "text", "text": "hi"}]` and no `media_attached` key in metadata.
5. A video is refused with `MediaNotSupportedError` naming `otter.mp4`, and `client.messages.stream` is not called.
6. Full request over the cap: patch `AnthropicProvider.MEDIA_REQUEST_MAX_BYTES` to `base64_size(587) + 10`, send a prompt of 100 characters → `MediaNotSupportedError` before any call (the media alone fits; media plus prompt does not).

**Step 2: Run — expect failures** (`MEDIA_KINDS` is empty, so `ensure_media_encodable` refuses the PDF).

**Step 3: Implement**

```python
from utils.media import MediaKind, MediaNotSupportedError, format_size

class AnthropicProvider(RegistryBackedProviderMixin, ModelProvider):
    MEDIA_KINDS = frozenset({MediaKind.PDF})
    # Anthropic limits the whole request body to 32 MB, base64 media included.
    MEDIA_REQUEST_MAX_BYTES = 32_000_000
    # Anthropic documents 1,500-3,000 tokens per PDF page (text plus a page image); Task 8 checks it live.
    PDF_TOKENS_PER_PAGE = 3_000
```

`generate_content(..., images=None, media: Optional[list] = None, **kwargs)`:

```python
        media = list(media) if media else []  # read more than once below
        media_attached: list[dict] = []
        user_content = []
        if media:
            self.ensure_media_encodable(media)
            document_blocks, media_attached = self._build_document_blocks(media)
            self._check_request_size(document_blocks, prompt, system_prompt)
            user_content.extend(document_blocks)
        user_content.append({"type": "text", "text": prompt})
        # ... images appended exactly as today ...
```

```python
    def _build_document_blocks(self, media) -> tuple[list[dict], list[dict]]:
        """Base64 document blocks in input order, and the media_attached records for the response metadata."""
        blocks, attached = [], []
        for attachment in media:
            data = base64.b64encode(Path(attachment.source_path).read_bytes()).decode()
            blocks.append({"type": "document", "source": {"type": "base64", "media_type": attachment.mime_type, "data": data}})
            attached.append(
                {"name": attachment.name, "kind": attachment.kind.value, "bytes": attachment.size_bytes, "transport": "inline"}
            )
        return blocks, attached

    def _check_request_size(self, document_blocks, prompt: str, system_prompt: Optional[str]) -> None:
        """The 32 MB limit covers the whole body: fail before sending rather than surface an HTTP 413."""
        total = sum(len(block["source"]["data"]) for block in document_blocks)
        total += len(prompt.encode()) + len((system_prompt or "").encode())
        if total > self.MEDIA_REQUEST_MAX_BYTES:
            raise MediaNotSupportedError(
                f"anthropic requests are limited to {format_size(self.MEDIA_REQUEST_MAX_BYTES)}; this one would be "
                f"{format_size(total)} with its PDFs base64-encoded. Gemini models take larger media."
            )
```

Add `"media_attached": media_attached` to the response metadata only when `media` is non-empty. Read bytes from `attachment.source_path` (validated), never `attachment.path`.

**Step 4: Run the new tests, `tests/test_media_provider_contract.py`, and the full suite.** The contract test `test_providers_without_encoder_reject_media` uses a video, so Anthropic must still refuse it.

**Step 5: Commit** — `feat(anthropic): send PDFs as native document blocks`

---

### Task 5: OpenAI PDF encoder (Chat Completions and Responses API)

**Files:**
- Modify: `providers/openai_compatible.py` (`generate_content`: `media` parameter, file parts, metadata; `_generate_with_responses_endpoint`: `media_attached` passthrough)
- Modify: `providers/openai.py` (`MEDIA_KINDS`, cap, rate)
- Test: `tests/test_media_openai.py` (new)

**Request shapes:** Chat Completions — user content `[{"type": "file", "file": {"filename": "zebra.pdf", "file_data": "data:application/pdf;base64,<b64>"}}, ..., {"type": "text", "text": prompt}, images...]`. Responses API — Task 3's conversion turns each `file` part into `{"type": "input_file", "filename": ..., "file_data": ...}`. The system message stays first in both. Only `OpenAIModelProvider` declares `MEDIA_KINDS`; the encoder lives in the shared base, so xAI (phase 3) can reuse it, and every other subclass (xAI, OpenRouter, Azure, DIAL, Custom) keeps refusing media through `ensure_media_encodable`.

**Step 1: Write the failing tests** (`provider._client = MagicMock()`; Chat models: `gpt-5.5`; Responses models: `gpt-6-luna`):

1. Chat: `messages[1]["content"]` is `[file_part, text_part]`; `file_data` is the data URL of the fixture; `messages[0]` is the system message.
2. Responses: the user input's `content` is `[input_file_part, input_text_part]`.
3. `media_attached` metadata on both paths (same record shape as Task 4).
4. Media-free Chat request: the user message `content` is still the plain string `prompt` (byte-for-byte rule); media-free Responses request unchanged.
5. `XAIModelProvider("k").generate_content(..., media=pdf)` raises `MediaNotSupportedError` before any client call (the shared base calls `ensure_media_encodable`).
6. Azure capability clones: build an `AzureOpenAIProvider` the way `tests/test_azure_openai_provider.py` does, with capabilities whose `supports_pdf` is `True` (patch or construct them), and assert `ModelProviderRegistry._filter_models_for_media(provider, [name], frozenset({MediaKind.PDF})) == []` and that `ensure_media_encodable` raises. This pins the "Azure clones OpenAI capabilities with `dataclasses.replace`" caveat from phase 1.
7. A request whose encoded media exceeds `OpenAIModelProvider.MEDIA_REQUEST_MAX_BYTES` (patch it small) is refused before any call.

**Step 2: Run — expect failures.**

**Step 3: Implement**

`providers/openai.py`:

```python
from utils.media import MediaKind

class OpenAIModelProvider(RegistryBackedProviderMixin, OpenAICompatibleProvider):
    MEDIA_KINDS = frozenset({MediaKind.PDF})
    # OpenAI accepts up to 50 MB of file input per request; counted base64-encoded to stay on the safe side.
    MEDIA_REQUEST_MAX_BYTES = 50_000_000
    # Extracted text plus a page image per page; Task 8 sets this from live usage.
    PDF_TOKENS_PER_PAGE = 1_500
```

`providers/openai_compatible.py` `generate_content(..., images=None, media: Optional[list] = None, **kwargs)`:

```python
        media = list(media) if media else []
        media_attached: list[dict] = []
        file_parts: list[dict] = []
        if media:
            self.ensure_media_encodable(media)  # every provider without an encoder refuses here
            file_parts, media_attached = self._build_file_parts(media)

        user_content = [*file_parts, {"type": "text", "text": prompt}]
        # ... images appended as today ...
        if len(user_content) == 1:
            messages.append({"role": "user", "content": prompt})
        else:
            messages.append({"role": "user", "content": user_content})
```

```python
    def _build_file_parts(self, media) -> tuple[list[dict], list[dict]]:
        """Chat Completions `file` parts (base64 data URLs) in input order, and the media_attached records."""
        parts, attached = [], []
        for attachment in media:
            data = base64.b64encode(Path(attachment.source_path).read_bytes()).decode()
            parts.append(
                {"type": "file", "file": {"filename": attachment.name, "file_data": f"data:{attachment.mime_type};base64,{data}"}}
            )
            attached.append(
                {"name": attachment.name, "kind": attachment.kind.value, "bytes": attachment.size_bytes, "transport": "inline"}
            )
        return parts, attached
```

Pass `media_attached=media_attached` to `_generate_with_responses_endpoint` (new keyword parameter, default `None`), and in both `ModelResponse` metadata dicts add `"media_attached": media_attached` only when it is non-empty. Check `AzureOpenAIProvider.generate_content` passes `media` through `**kwargs` to the base (it does today), so Azure reaches the base's `ensure_media_encodable` and refuses.

**Step 4: Run the new tests, the media suites (`tests/test_media_*.py`) and the full suite.**

**Step 5: Commit** — `feat(openai): send PDFs as file parts on Chat Completions and the Responses API`

---

### Task 6: Provider hints name the new keys

**Why:** when no available model can take a PDF, `utils.media.providers_hint` tells the user which key to configure. `MEDIA_PROVIDERS` lists only Gemini.

**Files:**
- Modify: `utils/media.py` (`MEDIA_PROVIDERS`, `providers_hint`)
- Test: `tests/test_media_hints.py` (extend)

**Step 1: Write the failing tests**

1. With no Google, Anthropic or OpenAI provider available (unregister them, as the existing hint tests do for Gemini), `providers_hint(frozenset({MediaKind.PDF}))` is `"configure GEMINI_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY"`.
2. `providers_hint(VIDEO)` and `providers_hint(AUDIO)` still name only `GEMINI_API_KEY` (the existing tests cover this; keep them green).
3. Guard: for every `MEDIA_PROVIDERS` entry, `supported == <provider class>.MEDIA_KINDS` (Google → `GeminiModelProvider`, Anthropic → `AnthropicProvider`, OpenAI → `OpenAIModelProvider`), so the hint can never promise a kind the encoder refuses.

**Step 2: Run — expect 1 and 3 to fail.**

**Step 3: Implement.** Entries in `PROVIDER_PRIORITY_ORDER` order. Anthropic has no `*_ALLOWED_MODELS` variable (`utils/model_restrictions.py` `ENV_VARS`), so the allow-list field becomes optional:

```python
MEDIA_PROVIDERS: tuple[tuple[str, str, str | None, frozenset[MediaKind]], ...] = (
    ("google", "GEMINI_API_KEY", "GOOGLE_ALLOWED_MODELS", frozenset(MediaKind)),
    ("anthropic", "ANTHROPIC_API_KEY", None, frozenset({MediaKind.PDF})),
    ("openai", "OPENAI_API_KEY", "OPENAI_ALLOWED_MODELS", frozenset({MediaKind.PDF})),
)
```

and in `providers_hint` the restriction branch becomes `elif allow_env and get_restriction_service().has_restrictions(provider_type):`.

**Step 4: Run `tests/test_media_hints.py`, the media suites and the full suite.** Any test asserting the exact PDF hint text elsewhere must now expect the three keys; check each failing assertion is about the hint before updating it.

**Step 5: Commit** — `feat(media): provider hints name the Anthropic and OpenAI keys for PDF`

---

### Task 7: Probe script for Anthropic and OpenAI

**Why:** a catalog flag is set only after a live probe passes (`tests/media_probe_matrix.py`, enforced by `tests/test_media_catalog_guard.py`). The Gemini probe calls the SDK directly; the Anthropic and OpenAI probes go through zen's own provider classes, so they verify the encoders from Tasks 4–5 as shipped. Provider classes check only their encoder kinds, not the model flags (those are checked by the tools), so unflagged models can be probed.

**Files:**
- Create: `tests/live_keys.py`
- Modify: `scripts/probe_media_support.py`
- Test: `tests/test_probe_media_support.py` (extend)

**Step 1: `tests/live_keys.py`** (the user approved this on 2026-10-03: the key comes from zen's own config when the environment lacks it; the value stays inside the process):

```python
"""API keys for live probes and tests: the environment first, then zen's own config file (~/.zen/.env).

The value is returned to the caller only. Never print, log or export it.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

ZEN_ENV_FILE = Path.home() / ".zen" / ".env"


def api_key(env_name: str) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value
    if ZEN_ENV_FILE.is_file():
        return dotenv_values(ZEN_ENV_FILE).get(env_name) or None
    return None
```

Unit-test it with `monkeypatch` on `os.environ` and a `ZEN_ENV_FILE` pointed at a file in `tmp_path` (never the real one).

**Step 2: Script changes**

- `--provider {google,anthropic,openai}` (default `google`, so today's invocations keep working). For `anthropic` / `openai`: default models are every `model_name` in `conf/anthropic_models.json` / `conf/openai_models.json`; default kinds are the provider class's `MEDIA_KINDS` (PDF only); asking for a kind the encoder lacks is an argument error.
- Probing goes through `AnthropicProvider(api_key=...)` / `OpenAIModelProvider(api_key=...)`: `provider.generate_content(question, model, media=classify_media([fixture])[1])`. Put the repo root on `sys.path` at the top of the script so `providers`, `utils` and `tests.live_keys` import.
- Each try line also prints `input_tokens` from `response.usage` (the Gemini path keeps its current output). The summary adds the largest `input_tokens` seen per (model, kind), which Task 8 uses to set `PDF_TOKENS_PER_PAGE`.
- A missing key stops the run with `"<ENV_NAME> is not set and not in ~/.zen/.env"` (never the value).
- Keep `main(argv, client=None)` testable: add a `provider_factory` parameter (or similar) so tests inject a fake provider whose `generate_content` returns a `ModelResponse` with scripted text/usage or raises.

**Step 3: Tests** (fake providers, no network): an Anthropic run over two models prints PASS/MISS lines with input tokens and a JSON matrix of verified kinds; an exception counts as an error (exit 1); `--provider openai --kinds audio` is rejected; Gemini behaviour is unchanged (existing tests stay green).

**Step 4: Full suite, lint, commit** — `feat(scripts): probe Anthropic and OpenAI PDF input through zen's providers`

---

### Task 8 (controller): Live probes, catalog flags, PDF rates

Run from the worktree root. Cost: one 1-page PDF request per model (about 33 models; the user approved probing the three `-pro` models too).

```bash
P=/Users/wrk/WorkDev/MCP-Dev/zen-cli/.zen_venv/bin/python
$P scripts/probe_media_support.py --provider anthropic
$P scripts/probe_media_support.py --provider openai
```

Then:

1. For every model the probe verified, set `"supports_pdf": true` in its catalog entry (`conf/anthropic_models.json`, `conf/openai_models.json`) and add `("anthropic" | "openai", "<model_name>"): frozenset({"pdf"})` to `PROBED`, with a provenance note in the module docstring (date, script, model count, misses).
2. A miss is re-probed with `--repeat 3`; flag only on 3/3. An API error (e.g. a model that rejects files) is recorded in the docstring and left unflagged.
3. Set `PDF_TOKENS_PER_PAGE` from the measured usage: the zebra page has almost no text, so its `input_tokens` (minus about 30 for the question) is the page-image cost. Anthropic: keep 3,000 if the measured page cost is at most 2,000 (room for a dense page's text), otherwise measured + 1,000. OpenAI: measured + 1,000, rounded up to the next 500. Record the measurements in a comment next to each constant.
4. `tests/test_media_catalog_guard.py` and the full suite pass.

Commit — `feat(media): flag Claude and OpenAI PDF input from live probes`

### Task 9 (controller): Live tests, docs, smoke test

1. `tests/test_media_live.py`: parametrize Anthropic and OpenAI PDF cases from `PROBED` (as the Gemini cases are), keyed by `tests.live_keys.api_key`, skipping when it returns `None`. Keep the token-estimate assertion, using the provider's `PDF_TOKENS_PER_PAGE`. Run `-m integration` for the new cases only.
2. Docs: mark phase 2 done in `docs/plans/2026-09-26-media-input-design.md` (status line) and the BACKLOG "Media input" entry; write `docs/plans/2026-10-03-media-input-phase2-status.md` (task → commit table, probe results, test counts); add any unflagged models to BACKLOG with the reason.
3. CLI smoke test from the worktree (the installed `zen` runs the live checkout, so use the worktree's sources): `PYTHONPATH=$PWD/src:$PWD $P -m zen_cli.main chat --model sonnet -f tests/fixtures/media/zebra.pdf "What code is written in this PDF? Reply with only the code."`, and the same with `--model gpt-5.5` and `--model gpt-6-luna`. Each must answer `ZEBRA-42`.
4. Final whole-branch review (one time-boxed reviewer), then fast-forward `zen-cli-v2`, push, and tell the user which sessions need `/mcp`.

## Done when

- A PDF reaches every flagged Claude and OpenAI model natively through chat, workflow and consensus tools, and every unflagged model or other provider fails fast naming the file and capable models.
- Media-free requests are byte-for-byte unchanged on Anthropic and both OpenAI endpoints.
- The MCP server registers native Anthropic; auto-mode text routing for the usual key set is unchanged.
- Images work on the Responses API; its usage is reported.
- Catalog flags match `PROBED`; live tests and the CLI smoke test pass; unit suite at baseline plus the new tests.
