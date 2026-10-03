# Media Input Phase 2 — Status

**Date:** 2026-10-03
**Plan:** `docs/plans/2026-10-03-media-input-phase2.md`
**Branch:** `feat/media-input-phase2` (worktree `zen-media-phase2`)
**Outcome:** PDFs reach Claude models (native Anthropic API) and OpenAI models (Chat Completions and Responses API) as native documents. The MCP server registers the native Anthropic provider. Audio and video stay Gemini-only.

## Tasks

| Task | Commit | Notes |
|---|---|---|
| Plan | `9c6fad5` | |
| 1 Provider contract | `69af77b` | `MEDIA_REQUEST_MAX_BYTES` (base64-encoded media, checked in `ensure_media_encodable`) and `PDF_TOKENS_PER_PAGE` per provider; both text-budget call sites use the provider's rate. |
| 2 Native Anthropic in MCP | `0721175` | User decision: `opus` / `fable` / `sonnet` move from OpenRouter to native Anthropic billing in MCP. Auto-mode picks for the usual key set are unchanged (tested). |
| 3 Responses API | `7e8368f` | Content arrays become `input_text` / `input_image` / `input_file` parts (images on gpt-6 were rejected before), usage reads `input_tokens` / `output_tokens`, the output cap is `max_output_tokens`. |
| 4 Anthropic encoder | `01bfa1c` | Base64 `document` blocks before the prompt text; whole-body 32 MB check. |
| 5 OpenAI encoder | `96dd988` | `file` parts on Chat Completions, `input_file` on the Responses API; only `OpenAIModelProvider` declares PDF. Long `file_data` / `image_url` values are shortened in the Responses request log. |
| 6 Provider hints | `d54b876` | "configure GEMINI_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY" for PDF. |
| Review fixes | `30a09eb` | The openai/anthropic SDK loggers stay at INFO (at DEBUG they logged whole request bodies, base64 included). DIAL refuses media inside its own `generate_content`. |
| 7 Probe script | `be3404b` | `--provider anthropic|openai` probes through zen's encoders; keys from the environment or `~/.zen/.env` via `tests/live_keys.py`, never printed. |
| 8 Flags and rates | `6363f78` | See probe results. |
| 9 Live tests | `e8ddf84` | One integration case per flagged Claude/OpenAI model. |

Found during the batches and fixed here: before Task 4/5, neither `AnthropicProvider` nor the shared OpenAI-compatible `generate_content` checked media at all (`media=` landed in `**kwargs`); only the tool call sites refused it. Both, and DIAL, now refuse it themselves.

## Probe results (2026-10-03)

- **Claude:** 13/13 catalog models read `zebra.pdf`; a near-empty page costs about 1,570 input tokens on every model.
- **OpenAI:** 20/20 on the first probe, the three `-pro` models included. In the live test that followed, gpt-5-mini and gpt-5-nano mostly answered "I can't access the PDF" with it attached; re-probed 1/3 and 1/3 (0/3 for nano with a system prompt), so both are unflagged. The other 18 are flagged.
- **Scanned pages:** an image-only PDF (marker drawn as pixels) was read by gpt-6-luna, gpt-6-astra, gpt-5.5 and claude-sonnet-5-5. A letter-size scanned page costs 2,902 tokens on gpt-6 (Responses API), 1,025 on gpt-5.5 (Chat Completions) and 1,611 on Claude.
- **Rates:** Anthropic 3,000 per page, OpenAI 4,000 (sized for gpt-6; errs high on gpt-5.x).

## Verification

- Unit suite: 1300 passed, 6 skipped, 3 failed (the 3 pre-existing `tests/test_alias_target_restrictions.py` Gemini failures), up from 1215 at the start of the phase.
- Live: 28/28 non-pro Claude/OpenAI cases in `tests/test_media_live.py`; the `-pro` models were probed once and not re-run (cost).
- CLI smoke test from the worktree: `zen chat -f tests/fixtures/media/zebra.pdf` answered `ZEBRA-42` on `sonnet`, `gpt-5.5` and `gpt-6-luna`; `gpt-5-mini` was refused with a list of capable models.

## Follow-ups

Recorded in `docs/plans/BACKLOG.md` under "Media input phase 2 follow-ups", "Unit suite is not hermetic in CI" (real keys from `~/.zen/.env` during local runs) and "Capability rank clamps at 100".
