# Media Input Phase 3 — Status

**Date:** 2026-10-03
**Plan:** `docs/plans/2026-10-03-media-input-phase3-xai.md`
**Branch:** `feat/media-phase3-xai` (worktree `zen-media-phase3`)
**Outcome:** A named Grok model takes PDFs through xAI's `/v1/responses` endpoint. Auto mode and the capability hints never route media to Grok. No Grok model is flagged `supports_pdf` yet: the controller sets the flags and the `PROBED` entries after the live probe.

## Tasks

| Task | Commit | Notes |
|---|---|---|
| Plan | `f533d50` | User decision: explicit models only, because xAI searches documents past one page with its billed `attachment_search` tool. |
| C1 Explicit-only providers | `94ef48c` | `ModelProvider.MEDIA_AUTO_ROUTING` (default True). `ModelProviderRegistry._filter_models_for_media` keeps no model of a provider that sets it False, so auto mode and `find_media_capable_models` skip it; a named model is still checked by `_validate_media_support` against its own flags. `XAIModelProvider` sets it False here rather than in C2, so C1's tests run against the real class. `MEDIA_PROVIDERS` leaves xAI out. |
| C2 xAI encoder | `f23a0fe` | `MEDIA_KINDS` {PDF}, 50 MB base64-encoded cap, 2,500 tokens per page. `OpenAICompatibleProvider._use_responses_endpoint(capabilities, media)` picks the endpoint (base: `use_openai_response_api`; xAI: also any media). `_responses_reasoning(capabilities)` returns the `reasoning` dict or None (base: always the dict; xAI: always None, matching Grok's text requests, which send no effort; changed by the controller after review). Responses usage `num_server_side_tools_used` lands in `metadata["server_side_tool_calls"]`. |
| C3 Probe script and docs | (this commit) | `--provider xai` probes through `XAIModelProvider` with `XAI_API_KEY` (`tests/live_keys.py`). `conf/xai_models.json` `_README` gains the `supports_pdf` and token-rate field descriptions. User docs: `docs/configuration.md` "Media Input". The zen-skill has no media section, so it is unchanged. |

## Behaviour

- **Grok with a PDF:** `responses.create` with `input_file` parts (`data:application/pdf;base64,...`), `store: False`, and no `reasoning` key for any Grok model, so xAI's default effort applies as it does for text requests. Images in the same request become `input_image` parts.
- **Grok without media:** Chat Completions, byte for byte as before.
- **OpenAI and OpenRouter:** unchanged. A test sends a text request to every Responses model of both catalogs and checks `reasoning` and the key order (`model`, `input`, `reasoning`, `store`).
- **Auto mode:** with Gemini, OpenAI and xAI keys and every Grok model flagged (patched in the test), a PDF never goes to Grok in any category, although xAI comes first in priority. With only an xAI key, auto mode refuses the PDF: "configure GEMINI_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY".

## Open before merge (controller)

1. Live probe: `scripts/probe_media_support.py --provider xai --repeat 2` over all 7 models, plus the 4-page scanned PDF through `XAIModelProvider`.
2. Resolved: Grok requests send no `reasoning` (grok-4.7 accepts it, grok-build-0.1 and grok-4.20-0309-non-reasoning reject it; text requests never sent it).
3. Flag the models that pass every try in `conf/xai_models.json` and record them in `tests/media_probe_matrix.py` (`PROBED`), with the date and token figures. `tests/test_media_catalog_guard.py` passes now with no xAI flags.
4. CLI smoke tests: `--model grok-4.7` with `zebra.pdf`, and auto mode with the same file (must answer from a non-Grok model).

## Verification

- Unit suite: 1443 passed, 6 skipped, 3 failed (the 3 pre-existing `tests/test_alias_target_restrictions.py` Gemini failures), up from 1400 at the start of the phase.
- No live API calls were made while implementing; every client is mocked.

## Follow-ups

Recorded in `docs/plans/BACKLOG.md` under "Media input phase 3 follow-ups".
