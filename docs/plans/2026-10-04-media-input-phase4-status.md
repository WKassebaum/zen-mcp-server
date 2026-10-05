# Media Input Phase 4 — Status

**Date:** 2026-10-04
**Plan:** `docs/plans/2026-10-04-media-input-phase4-openrouter.md`
**Branch:** `feat/media-phase4-openrouter` (worktree `zen-media-phase4`)
**Outcome:** OpenRouter can send PDF, audio and video, and only to models that read the file themselves: zen asks for OpenRouter's native PDF engine and refuses any answer that OpenRouter built from a parsed file. No model is flagged yet. The controller flags models after the live probe.

## Tasks

| Task | Commit | Notes |
|---|---|---|
| Plan | `ef518ab` | Policy: candidates from `architecture.input_modalities`, a flag only after a live probe through `OpenRouterProvider`, no `x-ai/*` model flagged. |
| P4.1 Encoder | `d3421ea` | `OpenRouterProvider.MEDIA_KINDS` = PDF, audio, video; 32 MB base64-encoded cap; 4,000 tokens per PDF page. Shared hooks in `OpenAICompatibleProvider`: `_build_media_parts`, `_media_request_options`, `_check_media_response`; `_responses_content` maps audio and video. `MEDIA_PROVIDERS` gains OpenRouter, last. |
| P4.2 Probe script | `f1b3cf7` | `--provider openrouter` probes each model only for its candidate kinds. `--candidates` lists them without a key or a probe. A parse refusal counts as a miss, not an API error. |
| P4.3 Catalog plumbing | this commit | `_README` lines for the five media fields and `media_token_rates`; mirrored rates on 8 OpenAI and 6 Gemini 3 entries; user docs; this file. |

## Behaviour

- **Chat Completions parts**, media first, then the prompt text, then any images:
  - PDF: `{"type": "file", "file": {"filename", "file_data": "data:application/pdf;base64,..."}}`.
  - Audio: `{"type": "input_audio", "input_audio": {"data": <raw base64>, "format": ...}}`. The format comes from the MIME type: mp3, wav, flac, ogg, m4a or aac. An unmapped MIME type is refused before any call.
  - Video: `{"type": "video_url", "video_url": {"url": "data:video/...;base64,..."}}`.
- **Responses API** (OpenRouter models with `use_openai_response_api`): `input_file`, `input_audio` (mp3 or wav only, anything else refused before any call) and `input_video` parts.
- **Request extras, only with media:**
  - `extra_headers`: `X-OpenRouter-Metadata: enabled`.
  - `extra_body`: `plugins: [{"id": "file-parser", "pdf": {"engine": "native"}}]`, only when a PDF is attached.
  - The client's attribution headers (`HTTP-Referer`, `X-Title`) are still sent; a test checks the real SDK request.
- **Parse check:** a response that carries a `type: "file"` annotation, or an `openrouter_metadata.pipeline` stage whose name contains "parser", raises `OpenRouterParsedMediaError`. The message reads: "OpenRouter parsed <file> into text instead of passing it to <model> natively; zen only sends media to models that read it themselves."
  - Both fields are read from dicts, attributes or the SDK's `model_extra`; absent means native.
  - The error is never retried, and the prompt is never resent without the file.
- **No provider pinning:** requests carry no `provider.order`. The parse check guards correctness, and pinning would cut availability.
- **Grok:** `MEDIA_AUTO_ROUTING` stays True. No `x-ai/*` model is flagged, and a test fails if one ever is, so Grok gets no media through OpenRouter.
- **Media-free requests:** unchanged.
  - Exact `create()` kwargs are asserted for Chat and Responses.
  - Through the real SDK (httpx mock transport), the request carries no metadata header and no `plugins`.
  - The HTTP bytes and headers of four media-free requests (Chat and Responses, with and without an image) were compared against the base commit: identical.
- **Hints:** `MEDIA_PROVIDERS` lists OpenRouter last, so a hint now also names `OPENROUTER_API_KEY` for every kind. Until the controller flags models, a configured OpenRouter key reports "none of its models takes ... input".

## Candidates (`--candidates`, 2026-10-04)

Among the 56 catalog models: pdf 44, audio 8, video 9. Four catalog ids are not in OpenRouter's models list.

- **PDF (44):** 10 listed Claude models, 19 OpenAI (all but the two codex models), 8 Gemini, 2 Mistral and 5 Grok. The five `x-ai/*` models are policy-excluded.
- **Audio:** the 8 Gemini models.
- **Video:** the 8 Gemini models and `moonshotai/kimi-k3`.
- **None:** the DeepSeek models, `moonshotai/kimi-k2.6`, `openai/gpt-5.1-codex` and `-codex-mini`.
- **Not listed:** `anthropic/claude-sonnet-4-6`, `anthropic/claude-opus-4-8`, `-4-7` and `-4-6`. OpenRouter lists them with dots.

## Live results

Pending: the controller runs the probe (plan, "Controller steps").

## Verification

- Unit suite: 1525 passed, 6 skipped, 3 failed (the 3 pre-existing `tests/test_alias_target_restrictions.py` Gemini failures), up from 1464 on the base branch.
- No live API calls were made while implementing; every client is mocked. The new tests ran with outbound sockets blocked. The one network call was the `--candidates` fetch of the public models list, which needs no key.

## Follow-ups

Recorded in `docs/plans/BACKLOG.md` under "Media input phase 4 follow-ups".
