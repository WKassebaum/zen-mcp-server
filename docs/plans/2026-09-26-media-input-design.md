# Media Input (PDF, Audio, Video) — Design

**Date:** 2026-09-26
**Status:** Phase 1 (core + Gemini) merged 2026-10-01; phase 2 (Claude and OpenAI, PDF) done 2026-10-03; phase 3 (xAI, PDF only, named Grok models only; `docs/plans/2026-10-03-media-input-phase3-xai.md`) implemented 2026-10-03, flags pending the live probe; phases 4–5 pending
**Branch for implementation:** `feat/media-input` (merged to `zen-cli-v2` via PR)

## Goal

Let every zen tool that takes `files` send PDF, audio and video to models that can read them natively, and fail loudly — never silently — when the chosen model cannot.

Today a video or PDF passed with `--files` goes through the text reader (`utils/file_utils.read_file_content`, `max_size=1_000_000`). Files of up to 1,000,000 bytes are decoded as UTF-8 with replacement characters, so the model receives garbage tokens. Larger files are replaced by a `--- FILE TOO LARGE: ... ---` marker, so the model sees none of the content. Only images have a media path, and only through a separate `images` field.

## Background: why this is not "Gemini Omni"

The deferred plan was to wire up Gemini Omni. Research on 2026-09-26 showed Omni is the wrong model for this:

- `gemini-omni-1.1-flash` (GA 2026-08-27) is a **video generator**. It is served only through the Interactions API (`client.interactions.create`), returns one MP4 per call, rejects audio input, and has no text-only output mode. `generateContent` is listed but rejected.
- Video and audio **understanding** is already available on models zen routes to: `gemini-3.8-flash` and `gemini-3.1-pro-preview` accept video, audio and PDF and return text.

Omni video generation is recorded as a separate future feature (see `docs/plans/BACKLOG.md`).

## Decisions

| Question | Decision |
|---|---|
| Scope | Media **input** for existing text tools. Omni generation deferred. |
| Interface | Auto-route media found in the existing `files` / `--files`. No new flag. |
| Providers | Every provider whose API accepts the media type (matrix below). |
| Routing | Capability-aware: auto mode only considers capable models; an explicit incapable `--model` fails fast and names capable models. Media is never dropped. |
| Transport | Inline base64 under each provider's cap; Gemini uploads to its Files API above its cap. |
| Approach | Per-model capability flags plus provider-owned native encoding. Image pipeline untouched. |
| xAI | Native, all three kinds. Audio and video marked experimental (undocumented but verified). |
| Continuation | Re-attach earlier media on every turn, newest first, within the token budget. |
| Caching (v1) | Stable-prefix layout for all providers, a Claude `cache_control` marker, and cached-token metrics. Gemini explicit caches deferred. |

## Capability matrix (verified 2026-09-26)

| Provider | PDF | Audio | Video | Request shape |
|---|---|---|---|---|
| Gemini (native) | yes | yes | yes | `inline_data` parts; Files API `file_data` above the inline cap |
| Anthropic (native) | yes | no | no | `document` block, base64 |
| OpenAI (native) | yes | only `gpt-audio*` (not in catalog) | no | Chat: `{"type":"file","file":{...}}`; Responses: `input_file` |
| xAI (native) | yes | yes (experimental) | yes (experimental) | `/v1/responses` with `input_file`. Chat Completions rejects files: "use /v1/responses instead". |
| OpenRouter | per model | per model | per model | `file` / `input_audio` / `video_url` parts; flags from `architecture.input_modalities` |
| Custom, DIAL, Azure | no | no | no | — |

Evidence for xAI: live `/v1/responses` calls to `grok-4.7` with `input_file` returned the correct marker for a PDF (`ZEBRA-42`), a spoken WAV (`Pelican seven`) and an MP4 frame (`OTTER-9`), with `num_server_side_tools_used: 0` and roughly $0.002–0.003 per call. xAI's docs state audio and video input are unsupported, so these are flagged experimental and pinned by live probes.

OpenRouter note: for models without native file support OpenRouter defaults to paid OCR (`mistral-ocr`, $2 per 1,000 pages). zen pins `engine: native` and relies on capability routing so that path is never taken.

## 1. Architecture and data model

- `ModelCapabilities` gains `supports_pdf`, `supports_audio`, `supports_video` (default `false`). A flag is set only after a live probe passes. Rank bonus: +1 per media kind.
- New `utils/media.py`:
  - `MediaKind` enum: `PDF`, `AUDIO`, `VIDEO`.
  - `MediaAttachment` dataclass: `path`, `kind`, `mime_type`, `size_bytes`.
  - `classify_media(paths) -> (text_paths, attachments)` by extension plus a magic-byte check.
  - `MEDIA_LIMITS`: per-provider inline caps.
- `_prepare_file_content_for_prompt` (simple and workflow variants) classifies first; media leaves the text pipeline, is stored on the request as `media`, and the prompt gets one manifest line per attachment (`[attached video: demo.mp4, 42 MB]`).
- `ModelProvider.generate_content(..., media=None)`. The base implementation rejects non-empty media. Overrides:
  - Gemini: inline parts or Files API upload.
  - Anthropic: base64 `document` block.
  - OpenAI Chat Completions: `file` part.
  - OpenAI and xAI Responses API: shared `input_file` encoder. xAI switches to `/v1/responses` only when media is present.
  - OpenRouter: `file` / `input_audio` / `video_url` with PDF engine pinned to `native`.
- The four `generate_content` call sites (`tools/simple/base.py` ×2, `tools/consensus.py`, `tools/workflow/workflow_mixin.py`) pass `media=`.

## 2. Routing and validation

All checks run before any upload or API call.

- **Explicit model:** `_validate_media_support` compares required kinds with the model's flags and raises `ToolExecutionError` naming the missing kind and up to five capable models available with the current keys.
- **Auto mode:** `get_preferred_fallback_model(category, required_media=frozenset())`. `_get_allowed_models_for_provider` drops incapable models before each provider's `get_preferred_model` runs, so the existing route lists keep working. If nothing can serve the request, the error names the blocking kind and the provider keys that would enable it.
- **Size:** inline caps — Anthropic 32 MB, OpenAI 50 MB, xAI 50 MB, Gemini 100 MB per request. Gemini uploads above its cap; others fail fast with size, cap and a pointer to Gemini.
  - Anthropic's 32 MB limit applies to the whole request, and media travels base64-encoded (4/3 inflation), so raw media tops out at roughly 23-24 MB once the prompt is included. Check the encoded size, not the file size.
  - Gemini: phase 1 keeps raw inline media under 60 MB (`INLINE_MEDIA_MAX_BYTES`, sized for base64 inflation against the 100 MB request cap with room for the prompt text and inline images; lowered from 70 MiB in the final review) and uploads the rest to the Files API. Live tests on 2026-09-26 accepted 57-71 MB PDFs inline, so the provider may allow more; 60 MB stays as the safe bound.
- **Page and duration limits** are not pre-checked; the provider's error is surfaced verbatim.
- **consensus** pre-flights every model and fails before the first call if any cannot take the media.
- **clink** is unchanged; CLI agents read paths themselves. `zen clink --cli-name grok` already handles PDF (Read tool), audio (local `whisper-cli`) and video (`ffmpeg` frames) and is the documented agentic fallback.

## 3. Continuation and upload lifecycle

- `ConversationTurn.media: list[str] | None`, written by `add_turn`. `get_conversation_media_list(context)` walks turns newest first and dedupes.
- On continuation, earlier media is re-attached (newest first) and the capability check re-runs on the combined set.
- Budget: estimate media tokens (Gemini ~258 tokens/s video, ~32 tokens/s audio; ~1.5k tokens per PDF page elsewhere). Drop oldest first and record it in the manifest: `[omitted: older recording.mp4 — over budget]`.
- Gemini upload cache `~/.zen/media_uploads.json`, keyed by `sha256(file) + model family`, storing `{file_uri, mime, expires_at}`. Reuse within Google's 48 h retention (expire 1 h early). A 404 on reuse evicts and re-uploads once. Uploads poll `files.get` until `ACTIVE` with a 10-minute timeout. zen never deletes uploads; Google's 48 h expiry does.
- Privacy note for docs: media above Gemini's inline cap is stored on Google's servers for up to 48 hours.
- xAI: inline only in v1.
- Metadata per response: `media_attached: [{name, kind, bytes, transport: inline|uploaded|cached}]`; xAI also `num_server_side_tools_used` and `num_sources_used` (usage fields on xAI `/v1/responses`; Chat Completions reports only `num_sources_used`).

Note: images are stored per turn but never re-sent on continuation (`get_conversation_image_list` has no callers). Media deliberately differs; aligning images is a separate backlog item.

## 4. Prompt layout, caching and error handling

**Layout for media requests only:** system prompt as its own element → media parts in first-seen order across the thread → changing text (history plus new request). Media-free requests keep today's layout byte for byte.

**Caching:**
- OpenAI, xAI and Gemini get automatic prefix caching from the layout.
- Claude: `cache_control: {type: "ephemeral"}` on the last media block.
- Each provider reports `cached_input_tokens` into `ModelResponse.usage`, read from the field its endpoint returns (checked 2026-09-27):
  - Chat Completions (OpenAI, xAI, OpenRouter): `usage.prompt_tokens_details.cached_tokens`
  - Responses API (OpenAI, xAI): `usage.input_tokens_details.cached_tokens`
  - Gemini: `usage_metadata.cached_content_token_count` in the Python SDK (`cachedContentTokenCount` over REST)
  - Claude: `usage.cache_read_input_tokens`

  xAI's server-side tool counters (`num_server_side_tools_used`, `num_sources_used`) are separate usage fields, not cache metrics. Visible in `--json`.

**Errors:**

| Condition | Behaviour |
|---|---|
| Unknown extension | Treated as text as today; a NUL-byte sniff turns binaries into "binary file, not a supported media type". |
| Model lacks capability | Fail fast before any call, listing capable models. |
| Over inline cap (non-Gemini) | Fail fast with size, cap and a pointer to Gemini. |
| Gemini upload timeout / `FAILED` | Error with the Files API state; nothing half-cached. |
| Cached URI 404 | Evict, re-upload once, then error. |
| Provider rejects media | Provider error verbatim plus model name. No silent retry without the media. |
| xAI `num_server_side_tools_used > 0` | Succeeds; logged warning that paid retrieval mode was used. |

## 5. Testing and rollout

**Fixtures** in `tests/fixtures/media/` with their generator script: `zebra.pdf` (marker `ZEBRA-42`), `pelican.wav` (spoken "pelican seven"), `otter.mp4` (frame text `OTTER-9`).

**Unit tests (no network):** classification; routing (explicit, auto, consensus, "which key" message); per-provider payload shapes on mocked clients; prefix byte-stability across two turns; size caps; upload cache hit/miss/expiry/404; continuation re-attach and budget trimming; `cached_input_tokens` parsing; a catalog guard that every media-flagged model has a live probe.

**Live probes (`-m integration`, ~$0.10 total):** one marker probe per flagged (model family, kind), plus a second-turn probe per provider asserting `cached_input_tokens > 0`.

**Phases** (each lands with tests and a live probe):
1. Capability flags, `utils/media.py`, routing and validation, Gemini provider.
2. Claude and OpenAI.
3. xAI Responses media path.
4. OpenRouter.
5. Continuation, upload cache, prefix caching and metrics; docs (zen-skill media section, clink grok fallback, privacy note).

No new dependencies (`google-genai` 1.46 has `files.upload`). No new CLI flags; the `files` field description is updated to mention media.

## Out of scope

Omni video generation, OpenAI audio input, Gemini explicit context caches, page/duration pre-checks, unifying the image pipeline. All tracked in `docs/plans/BACKLOG.md`.
