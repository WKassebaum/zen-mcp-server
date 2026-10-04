# Media phase 2 follow-ups, test hermeticity, routing and ranking: implementation plan

**Goal:** Clear the BACKLOG items "Media input phase 2 follow-ups" (code parts), "Unit suite is not hermetic in CI", and the four "Routing and ranking" entries.

**Process:**
- Two batches run in parallel, in separate worktrees.
- Each batch has one implementer working test-first: write the failing test, watch it fail, fix, then watch it pass.
- The controller reviews each diff, and one time-boxed reviewer reads the whole branch before the merge.

**Batches:**
- Batch A: worktree `/Users/wrk/WorkDev/MCP-Dev/zen-followups`, branch `fix/followups-routing`. Covers media follow-ups and hermeticity.
- Batch B: worktree `/Users/wrk/WorkDev/MCP-Dev/zen-routing`, branch `fix/routing-ranking`. Covers routing and ranking.

**Commands (run from the worktree root):**
- Python: `/Users/wrk/WorkDev/MCP-Dev/zen-cli/.zen_venv/bin/python`.
- Unit tests: `<python> -m pytest tests/ -q -m "not integration" -p no:cacheprovider`. Do not use `-x`. Three failures in `tests/test_alias_target_restrictions.py` are known and pre-existing.
- Lint (on PATH, not in the venv): `ruff check . --fix && black . && isort .`
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

**Rules:**
- No live API calls. Every provider client is mocked.
- Never read, print or source `~/.zen/.env`.
- Commit each task separately.

---

## Batch A: media follow-ups and hermeticity

### A1. Per-model media token rates

**Why:** PDF page cost differs about 9x between OpenAI families, and video cost about 4x between Gemini generations. One rate per provider over-reserves text budget on most models. Measurements are in `docs/plans/2026-10-03-media-input-phase2-status.md` ("Scanned pages") and in BACKLOG "Token estimates per model family".

**Files:**
- `providers/shared/model_capabilities.py`
- `utils/media.py`
- `tools/shared/base_tool.py` (around line 1093)
- `tools/workflow/workflow_mixin.py` (around line 394)
- `conf/openai_models.json`, `conf/gemini_models.json`
- `tests/test_media_live.py`
- tests

**Behaviour:**
- **New fields.** `ModelCapabilities` gets two new optional fields, both defaulting to `None`:
  - `pdf_tokens_per_page: Optional[int]`
  - `video_tokens_per_second: Optional[int]`

  The catalog loader already passes through any key in `CAPABILITY_FIELD_NAMES`; confirm this. Add `_README` description lines for both fields in every `conf/*_models.json` that carries the `supports_pdf` description line. The wording: "Estimated input tokens per PDF page / per second of video, reserved from the text budget; set only from measured usage; unset uses the provider default."
- **Lookup order.** `utils.media.pdf_tokens_per_page(model_context)` resolves in this order:
  1. `model_context.capabilities.pdf_tokens_per_page`
  2. the provider's `PDF_TOKENS_PER_PAGE`
  3. the global `PDF_TOKENS_PER_PAGE`

  Add `video_tokens_per_second(model_context)` with the same order: capability field, then the provider's `VIDEO_TOKENS_PER_SECOND` class attribute (add it to `providers/base.py` as `ClassVar[Optional[int]] = None`), then the global constant.
- **Lookup guard.** At every step, only a real positive `int` counts (not a `bool`, not a mock).
  - Reading `model_context.capabilities` can raise, because the property resolves through the registry. Treat any exception as "no value".
  - Existing tests pass `SimpleNamespace` or `MagicMock` contexts; keep them working.
- **Estimate API.** `estimate_media_tokens(media, page_rate=PDF_TOKENS_PER_PAGE, video_rate=VIDEO_TOKENS_PER_SECOND)`. Audio stays at 32 tokens per second.
- **One helper for callers.** Add `estimate_media_tokens_for(media, model_context)` in `utils.media`, which applies both lookups. Use it from both call sites so the lookup logic lives in one place. The existing "no media, no rate lookup" guard (`tests/test_media_provider_limits.py:152`) must still hold.
- **Catalog values.** Set rates only where usage was measured. Measured figures are per letter-size scanned page, with roughly 45% margin added:
  - **OpenAI, `pdf_tokens_per_page: 1500`** (measured about 1,025; raised to 2500 after the final review, to add the 1,000-token text allowance): `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, `gpt-5.4`, `gpt-5.2`, `o4-mini`.
  - **OpenAI, `pdf_tokens_per_page: 500`** (measured 323; raised to 1500 after the final review): `gpt-5`, `gpt-5.1`, `o3`, `gpt-4.1`.
  - **OpenAI, no field:** the gpt-6 models (measured 2,902, so the provider's 4,000 stands) and the three `-pro` models (unmeasured).
  - **Gemini, `video_tokens_per_second: 160`** (measured about 100–127 per second with audio): every `gemini-3*` model flagged `supports_video`. Gemini 2.5 models keep the global 400.
  - **Anthropic:** unchanged, at 3,000 per page.

  Record the source of each figure in a comment-like `_README` note or the phase 2 status doc. JSON has no comments, so don't invent a comment key per model.
- **`tests/test_media_live.py`.** Each case's estimate must use the model's own rates (`estimate_media_tokens_for` with a real `ModelContext`, or the capability values directly). Keep the "estimate ≥ actual usage" assertions.

**Tests (new, unit):**
- **Lookup order:** the capability field wins over the provider attribute, which wins over the global constant. This applies to both lookups.
- **Real values:**
  - `gpt-5.5` resolves to 1500 through a real `ModelContext`.
  - `gpt-6-luna` falls back to the OpenAI provider's 4000.
  - `gemini-3.8-flash` has a video rate of 160.
  - `gemini-2.5-pro` has a video rate of 400.
- **Guard:** a mock or `bool` capability value is ignored.
- **Call sites:** a 3-page PDF reserves 4,500 tokens on `gpt-5.5` (7,500 after the final review's rate change), and a 3 s video reserves 480 on `gemini-3.8-flash`.

### A2. The Anthropic body-size check counts images

**File:** `providers/anthropic.py`, `generate_content` and `_check_request_size`.

**Behaviour:**
- Run the 32 MB whole-body check after the image blocks are built. Include each image block's base64 `data` length.
- Run it whenever the request carries PDFs or images.
- The error says "with its PDFs and images base64-encoded" (or just PDFs, or just images, whichever applies).
- Over the limit, raise `MediaNotSupportedError` before any client call.

**Tests:**
- One PDF plus images that push the body over a lowered limit raises, and the client is never called. Patch `MEDIA_REQUEST_MAX_BYTES` on the instance or class.
- Images alone over the limit also raise.
- Under the limit, the request is sent.

### A3. The auto-mode restriction error names every allow-list

**File:** `server.py` (around line 674, "Please check your OPENAI_ALLOWED_MODELS and GOOGLE_ALLOWED_MODELS settings.").

**Behaviour:** build the list from `utils.model_restrictions` (its `ENV_VARS` mapping) so it cannot drift again. Name each variable once, in a stable order.

**Test:** the message contains `ANTHROPIC_ALLOWED_MODELS`, `XAI_ALLOWED_MODELS` and `OPENROUTER_ALLOWED_MODELS`.

### A4. The CLI's `~/.zen/.env` load stays out of unit tests

**Files:**
- `src/zen_cli/main.py` (lines 26-45)
- `tests/conftest.py`
- `tests/test_large_prompt_handling.py`
- `tests/test_zen_storage_backends.py`
- `docs/plans/BACKLOG.md`

**Behaviour:**
- **Opt-out switch.** `main.py` skips the import-time `~/.zen/.env` load when `os.environ.get("ZEN_NO_USER_ENV")` is truthy (`"1"`, `"true"` or `"yes"`, case-insensitive).
- **Test setup.** `tests/conftest.py` sets `os.environ["ZEN_NO_USER_ENV"] = "1"` at the very top, before anything imports `zen_cli`. Add a comment saying why.
- **Existing tests.** Any test that checks the CLI's env loading must still pass: monkeypatch the variable off and reload, or test with a temporary HOME.
- **Paid Gemini call.** Mock the real Gemini request in `tests/test_large_prompt_handling.py::test_large_file_context_does_not_trigger_mcp_prompt_limit`. The test's point is the MCP prompt-size check; keep that assertion.
- **Storage backend test.** Isolate `tests/test_zen_storage_backends.py::test_default_backend` from leftover state and environment: monkeypatch the env vars it depends on and reset the storage singleton.

**Verification:** run the suite twice, both from the worktree root and expecting only the 3 known failures:
- normally;
- under `env -u GEMINI_API_KEY -u OPENAI_API_KEY -u XAI_API_KEY -u ANTHROPIC_API_KEY -u OPENROUTER_API_KEY <python> -m pytest ...` (CI conditions).

Also show that no real key is present during collection: a temporary test, not committed, asserting `os.environ.get("ANTHROPIC_API_KEY")` is unset or a dummy. The real Anthropic key lives only in `~/.zen/.env`. Delete that test afterwards.

**BACKLOG:** update "Unit suite is not hermetic in CI". Keep a note that exported shell keys (GEMINI and OPENAI) still reach local unit runs, so unmocked calls remain possible locally.

---

## Batch B: routing and ranking

Read BACKLOG "Routing and ranking" (`docs/plans/BACKLOG.md`) first: each entry has the bug, line references and a fix direction.

### B1. Rank clamp

**Files:**
- `providers/shared/model_capabilities.py` (`get_effective_capability_rank`)
- `conf/anthropic_models.json`, `conf/openrouter_models.json`
- `docs/model_ranking.md`
- `providers/registry.py` (`find_media_capable_models`)

**Behaviour:**
- **Remove the clamp.** Drop the upper clamp: `return max(0, score)`.
- **Media bonus.** Remove the +1 per media kind from the general rank. In `find_media_capable_models`, sort by `(-rank, -len(supported_media_kinds), name)`, so media breadth only breaks ties among media-capable models.
- **Spread the Anthropic scores.** `intelligence_score` is a human 1–20 score capped at 20. Today every Opus is 19. Keep fable-5-1 at 20, and opus-5-5, fable-5 and sonnet-5-5 at 19. Then:
  - opus-5 and sonnet-5: 18.
  - opus-4-8 and opus-4-7: 17.
  - opus-4-6, opus-4-5 and sonnet-4-6: 16.
  - sonnet-4-5: 15.
  - haiku-4-5: 14, as now.

  Mirror the same relative ordering in the `anthropic/*` entries of `conf/openrouter_models.json`.
- **Docs.** Fix `docs/model_ranking.md`: no clamp, the media bonus is a tie-break only, and remove the "Custom endpoints: -1" penalty, which no code applies.

**Tests:**
- An `intelligence_score` of 20 outranks 19 when everything else is equal.
- The top 5 of `listmodels`-style ranking across all native catalogs starts with 20-score flagships (fable-5.1, gpt-6-astra, gemini-3.1-pro, gpt-6-sol, grok-4.7, in rank order). Assert membership and that no Opus 4.x entry is in the top 5.
- A PDF refusal hint built with keys for Anthropic, OpenAI and Gemini (mocked) lists no `claude-opus-4-*` model. Find the hint builder in `utils/media.py` (`providers_hint` and the capable-model lister).
- Media breadth breaks ties only within `find_media_capable_models`.

Update any existing tests that hardcode clamped values. Show each such change in the commit message.

### B2. Gemini `find_best` ranks by reverse string order

**File:** `providers/gemini.py:560`.

**Behaviour:**
- Resolve candidates through `_resolve_model_name` and dedupe to canonical names. Rank by `(intelligence_score, name)`, highest first.
- An alias-only allow-list must still work: keep the original allowed spelling if the caller expects it, or return the canonical name if the callers resolve again. Check what the callers do.
- FAST_RESPONSE may keep preferring flash-lite if that is the current intent; read the code.

**Test:** with `GOOGLE_ALLOWED_MODELS=gemini-3.5-flash,gemini-3.5-flash-lite`, auto mode and no xAI key, EXTENDED_REASONING and BALANCED pick `gemini-3.5-flash`.

### B3. OpenAI/xAI FAST_RESPONSE fallback

**Files:** `providers/openai.py:155`, `providers/xai.py:95`, plus a shared helper (for example in `providers/shared/` or `providers/base.py`).

**Behaviour:**
- When no allowed model is on the FAST list, return the lowest-rank allowed canonical model. Walk the allowed list from the end and skip aliases, since `allowed_models` contains aliases.
- Add `gpt-5-nano` to the end of the OpenAI FAST list, and `gpt-5.6-terra` and `gpt-4.1` to BALANCED.

**Test:** `OPENAI_ALLOWED_MODELS=gpt-5-nano,gpt-6-astra` routes FAST_RESPONSE to `gpt-5-nano`. Add an equivalent xAI case.

### B4. Auto mode for setups with only OpenRouter, Azure, DIAL or Custom keys

**File:** `providers/registry.py` (`get_preferred_fallback_model`, around line 420).

**Behaviour:**
- **First provider decides.** Stop at the first provider in priority order that has allowed models. If its `get_preferred_model` returns `None`, pick among that provider's allowed canonical names; never fall through to a later provider or to `sorted(allowed_models)[0]`. Do not add an `OpenRouterProvider.get_preferred_model`; BACKLOG explains why.
- **Pick by rank.** Rank canonical names (resolve aliases and dedupe) by `get_effective_capability_rank()`, with the name as tie-break:
  - EXTENDED_REASONING and BALANCED: the highest-ranked.
  - FAST_RESPONSE (it backs `chat`, so quality still matters): the lowest-ranked model with `intelligence_score >= 15`, or the lowest-ranked overall if none qualifies.
- **Shared helper.** Put the rank logic in a helper shared with B3 if that is natural.

**Tests:**
- Strengthen `tests/test_auto_mode_comprehensive.py::test_openrouter_fallback_when_no_native_apis` to assert the exact model per category.
- Add an `OPENROUTER_ALLOWED_MODELS=opus,sonnet,mistral` case (adjust it to aliases that exist in `conf/openrouter_models.json`).
- Add a Custom+OpenRouter case: FAST_RESPONSE stays on the Custom model.

---

## Controller steps (not for implementers)

- Live re-probe of gpt-5-mini and gpt-5-nano: `scripts/probe_media_support.py --provider openai --repeat 3 gpt-5-mini gpt-5-nano`. Flag only on 3/3.
- Live media tests after batch A: Gemini, Anthropic and OpenAI estimates must be at least the actual usage.
- Final whole-branch review, then rebase onto `origin/zen-cli-v2`, fast-forward and push.
- Update BACKLOG: remove the fixed entries and record what remains.
