# Media Input Phase 3 — Status

**Date:** 2026-10-03
**Plan:** `docs/plans/2026-10-03-media-input-phase3-xai.md`
**Branch:** `feat/media-phase3-xai` (worktree `zen-media-phase3`)
**Outcome:** A named Grok model takes PDFs through xAI's `/v1/responses` endpoint. Auto mode and the capability hints never route media to Grok. All 7 Grok models are flagged `supports_pdf` after a live probe (2026-10-03).

## Tasks

| Task | Commit | Notes |
|---|---|---|
| Plan | `e47355c` | User decision: explicit models only, because xAI searches documents past one page with its billed `attachment_search` tool. |
| C1 Explicit-only providers | `8a7fd51` | `ModelProvider.MEDIA_AUTO_ROUTING` (default True). `ModelProviderRegistry._filter_models_for_media` keeps no model of a provider that sets it False, so auto mode and `find_media_capable_models` skip it; a named model is still checked by `_validate_media_support` against its own flags. `XAIModelProvider` sets it False here rather than in C2, so C1's tests run against the real class. `MEDIA_PROVIDERS` leaves xAI out. |
| C2 xAI encoder | `9a093c4` | `MEDIA_KINDS` {PDF}, 50 MB base64-encoded cap, 2,500 tokens per page. `OpenAICompatibleProvider._use_responses_endpoint(capabilities, media)` picks the endpoint (base: `use_openai_response_api`; xAI: also any media). `_responses_reasoning(capabilities)` returns the `reasoning` dict or None (base: always the dict; xAI: always None, matching Grok's text requests, which send no effort; changed by the controller after review). Responses usage `num_server_side_tools_used` lands in `metadata["server_side_tool_calls"]`. |
| C3 Probe script and docs | `87f6b38` | `--provider xai` probes through `XAIModelProvider` with `XAI_API_KEY` (`tests/live_keys.py`). `conf/xai_models.json` `_README` gains the `supports_pdf` and token-rate field descriptions. User docs: `docs/configuration.md` "Media Input". The zen-skill has no media section, so it is unchanged. |
| Reasoning | `188e6e1` | Controller: no `reasoning` on any Grok Responses request. |
| Flags | `02596a1` | Controller: `supports_pdf` on all 7 Grok models, `PROBED` entries; grok-4.20 models reserve 7500 tokens per page. |

## Behaviour

- **Grok with a PDF:** `responses.create` with `input_file` parts (`data:application/pdf;base64,...`), `store: False`, and no `reasoning` key for any Grok model, so xAI's default effort applies as it does for text requests. Images in the same request become `input_image` parts.
- **Grok without media:** Chat Completions, byte for byte as before.
- **OpenAI and OpenRouter:** unchanged. A test sends a text request to every Responses model of both catalogs and checks `reasoning` and the key order (`model`, `input`, `reasoning`, `store`).
- **Auto mode:** with Gemini, OpenAI and xAI keys and every Grok model flagged (patched in the test), a PDF never goes to Grok in any category, although xAI comes first in priority. With only an xAI key, auto mode refuses the PDF: "configure GEMINI_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY".

## Live results (2026-10-03)

- **Probe:** `scripts/probe_media_support.py --provider xai --repeat 2`: all 7 models read `zebra.pdf` 2/2.
- **Scanned PDFs through `XAIModelProvider` with zen's `CHAT_PROMPT`:** every model read an image-only letter page and an image-only four-page PDF (all four markers, in order).
- **Search behaviour:** `attachment_search` ran unpredictably.
  - grok-4.7, 4.6, 4.5, 4.3 and grok-build-0.1 ran no search: 1,895–2,989 input tokens for one page, 3,475–4,578 for four.
  - The grok-4.20 models ran it 2–3 times even for one page (7,748 and 8,889 input tokens). Their four-page runs took 0 and 2 searches (3,467 and 12,581 tokens).
  - Hence those two reserve 7,500 tokens per page, while the others keep the provider's 2,500.
- **Before zen's encoder (raw SDK, grok-4.7, no system prompt):**
  - one page: 0 searches;
  - four pages: 1 search, 9,997 tokens;
  - no PDF: 1,249 tokens (xAI adds a hidden prompt).
  - Chat Completions answered 400 to a `file` part.
- **CLI smoke tests (worktree code):**
  - `zen chat ... --model grok-4.7 -f zebra.pdf` answered ZEBRA-42 from xAI.
  - Auto mode with the same file answered from `gemini-3.8-flash`, not Grok, although xAI comes first in priority.

## Verification

- Unit suite: 1458 passed, 6 skipped, 3 failed (the 3 pre-existing `tests/test_alias_target_restrictions.py` Gemini failures), up from 1410 on the base branch.
- No live API calls were made while implementing; every client is mocked. Live checks are listed above.

## Follow-ups

Recorded in `docs/plans/BACKLOG.md` under "Media input phase 3 follow-ups".
