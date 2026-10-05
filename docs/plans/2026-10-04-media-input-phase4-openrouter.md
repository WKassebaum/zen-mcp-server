# Media input phase 4 (OpenRouter): implementation plan

**Goal:** OpenRouter models take PDF, audio and video natively. A model reading the file itself is the only accepted outcome. If OpenRouter parses or OCRs the file instead, the request fails loudly rather than answering from extracted text.

**Policy (controller, 2026-10-04; the user said to proceed):**
- **Candidates** come from OpenRouter's `architecture.input_modalities` (`file`, `audio`, `video`).
- **A flag is set only after a live probe** through zen's own `OpenRouterProvider`, as for every other provider. The catalog guard enforces that (`tests/media_probe_matrix.py`).
- **`x-ai/*` models are not flagged:** xAI reads files with a paid server-side search tool (phase 3). Grok PDFs stay native-xAI and named-model only.

**Process:** the same as `docs/plans/2026-10-03-followups-and-routing.md` (header).
- Worktree: `/Users/wrk/WorkDev/MCP-Dev/zen-media-phase4`.
- Branch: `feat/media-phase4-openrouter`.
- No live calls by the implementer; the controller probes.

**Facts** (OpenRouter docs read 2026-10-04 by a research agent; docs and the public models list are saved in the session scratchpad):
- **PDF on Chat Completions:** `{"type": "file", "file": {"filename", "file_data": "data:application/pdf;base64,..."}}`. This is the part `OpenAICompatibleProvider._build_file_parts` already builds.
- **PDF on Responses:** `{"type": "input_file", "filename", "file_data"}`.
- **PDF engine:** chosen by `plugins: [{"id": "file-parser", "pdf": {"engine": "native"}}]`. With no plugin entry, a model without native support is silently parsed (`mistral-ocr`). Account-level plugin defaults may also apply.
- **How to detect parsing:**
  - Parsed responses carry `message.annotations` entries with `type: "file"`; native responses carry none.
  - With the request header `X-OpenRouter-Metadata: enabled`, the response's `openrouter_metadata.pipeline` includes a `file-parser` stage when parsing ran.
  - In the openai SDK these arrive through `model_extra` and the message's extra fields.
- **Audio:** `{"type": "input_audio", "input_audio": {"data": "<raw base64, no data: prefix>", "format": "wav"|"mp3"|"flac"|"ogg"|"m4a"|"aac"|"aiff"}}`. On Responses the format is `mp3|wav` only.
- **Video:** `{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,..."}}` on Chat, and `{"type": "input_video", "video_url": "..."}` on Responses. Formats: mp4, mpeg, mov, webm.
- **Usage:**
  - Chat: `prompt_tokens` and `prompt_tokens_details.cached_tokens`.
  - Responses: `input_tokens_details.cached_tokens`.
  - Plus `cost`, which is in `model_extra`.
- **Size limits:** not documented for inline data.

---

## Batch P4

### P4.1 The OpenRouter encoder

**Files:**
- `providers/openrouter.py`
- `providers/openai_compatible.py` (shared encoder hooks only)
- `utils/media.py` (`MEDIA_PROVIDERS`)
- tests

**Behaviour:**
- **`OpenRouterProvider.MEDIA_KINDS`** = PDF, AUDIO, VIDEO.
- **`MEDIA_REQUEST_MAX_BYTES = 32_000_000`, base64-encoded.** Comment: OpenRouter documents no inline limit; 32 MB is the smallest upstream body limit (Anthropic), so it holds whichever upstream serves the request.
- **`PDF_TOKENS_PER_PAGE = 4_000`**, the highest native provider rate. Per-model rates come from the catalog (P4.3).
- **Chat Completions parts**, built in a new shared helper next to `_build_file_parts` (reuse it for PDF):
  - PDF: the `file` part above.
  - Audio: an `input_audio` part with raw base64, and `format` from the MIME type (map `audio/mpeg`→`mp3`, `audio/wav`/`audio/x-wav`→`wav`, `audio/flac`→`flac`, `audio/ogg`→`ogg`, `audio/mp4`/`audio/aac`→`m4a`/`aac`). An unmapped MIME type raises `MediaNotSupportedError` before any call.
  - Video: a `video_url` part with a data URL.
- **Order:** media parts first, then text, as for OpenAI.
- **Responses API** (OpenRouter models with `use_openai_response_api`): `_responses_content` maps the new part types to `input_file`, `input_audio` (mp3/wav only, otherwise `MediaNotSupportedError` before any call) and `input_video`.
- **Request extras, only when media is present** (media-free requests stay byte for byte as today):
  - `extra_body["plugins"] = [{"id": "file-parser", "pdf": {"engine": "native"}}]` when a PDF is attached.
  - `extra_headers["X-OpenRouter-Metadata"] = "enabled"`.
  - Merge with any existing `extra_body` / `extra_headers` the provider already sends (OpenRouter sets attribution headers; check `providers/openrouter.py`).
- **Fail loudly.** After the response arrives and before returning, raise a `RuntimeError` if:
  - any message annotation has `type == "file"`, or
  - `openrouter_metadata.pipeline` names a `file-parser` / parser stage.

  The error says: "OpenRouter parsed <file> into text instead of passing it to <model> natively; zen only sends media to models that read it themselves." It must not retry without the media. Read both fields defensively (dict or object, may be absent). Absent means native.
- **No provider pinning.** Do not send `provider.order`. The parse check guards correctness; pinning would cut availability. Record this in the status doc.
- **`MEDIA_AUTO_ROUTING` stays True.** No `x-ai/*` model is flagged (P4.3), so Grok cannot get media through OpenRouter.
- **Hints.** Add `("openrouter", "OPENROUTER_API_KEY", "OPENROUTER_ALLOWED_MODELS", frozenset(MediaKind))` to `utils.media.MEDIA_PROVIDERS`, in priority order (OpenRouter is last). `tests/test_media_hints.py` checks the kinds against the class.

**Tests** (mocked client; assert the exact `chat.completions.create` / `responses.create` kwargs):
- PDF, WAV, MP3 and MP4 part shapes and order.
- `plugins` only with a PDF.
- The header only with media.
- A media-free request is unchanged.
- Annotations of type file raise.
- A metadata pipeline with file-parser raises.
- A clean response passes and `media_attached` is in its metadata.
- An unmapped audio MIME type raises before the call.
- The size cap raises before the call.
- The Responses path for a `use_openai_response_api` OpenRouter model.

### P4.2 Probe script

**Files:** `scripts/probe_media_support.py`, `tests/test_probe_media_support.py`.

**Behaviour:**
- `--provider openrouter` probes through `OpenRouterProvider`, reading `OPENROUTER_API_KEY` via `tests.live_keys`.
- Kinds: pdf, audio, video, limited to each model's candidate kinds from `input_modalities`.
- Add a `--candidates` flag that fetches `https://openrouter.ai/api/v1/models` (public, no key) and prints, for each catalog model, the kinds its `input_modalities` lists, without probing.
- A unit test with a fake provider factory covers the new path, as for the others.

### P4.3 Catalog plumbing

**Files:** `conf/openrouter_models.json`, `tests/media_probe_matrix.py` (docstring only), `docs/configuration.md`, `docs/plans/BACKLOG.md`, the design doc status line, `docs/plans/2026-10-04-media-input-phase4-status.md` (new).

**Behaviour:**
- **README lines.** Add `_README` field-description lines for `supports_pdf`, `supports_audio`, `supports_video`, `pdf_tokens_per_page` and `video_tokens_per_second`, matching the other catalogs. Flags are set by the controller after the probe, not by the implementer.
- **Rates.** Copy the measured per-model rates of the native twins onto the OpenRouter entries:
  - OpenAI 2500/1500 `pdf_tokens_per_page` on the same models;
  - Gemini 3 `video_tokens_per_second` 160.

  Add a `_README.media_token_rates` note saying they mirror the native catalogs.
- **Docs.** "Media Input" in `docs/configuration.md` gains OpenRouter:
  - it reads files natively only, and refuses when OpenRouter would parse;
  - no Grok media through OpenRouter.

---

## Controller steps

1. `--candidates`, then probe every candidate with `--repeat 2`:
   - text and scanned PDFs;
   - the pelican WAV and otter MP4 fixtures for audio/video candidates.

   Skip premium models except one try each.
2. Flag what passes every try, and add `("openrouter", id)` entries to `PROBED`.
3. Probe `native` on a model without native PDF support (e.g. `deepseek/deepseek-v4-pro`), to confirm the refusal path: OpenRouter's own error or zen's parse check.
4. Run the final review, merge and push.
