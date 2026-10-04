# zen-cli Feature Backlog

Future work that has been scoped or discovered but deliberately not started. Add the date an item was recorded and what would unblock it. Move an item into a `docs/plans/YYYY-MM-DD-<topic>-design.md` when it is picked up.

## Planned

### Media input (PDF, audio, video)
- **Recorded:** 2026-09-26
- **Status:** Phase 1 (core + Gemini) merged 2026-10-01. Phase 2 (Claude and OpenAI, PDF only) done 2026-10-03: `docs/plans/2026-10-03-media-input-phase2-status.md`. Phases 3–5 pending. Design: `docs/plans/2026-09-26-media-input-design.md`.

### Media input phase 1 follow-ups
Found by the phase 1 task reviews (2026-09-28 to 09-30); none blocks phase 1.
- **Duplicate attachments on case-insensitive disks and hard links:** `CLIP.mp4` and `clip.mp4`, or a hard link, attach twice. Dedupe on `(st_dev, st_ino)`.
- **FIFO swap window:** a small gap between `is_file()` and `open()` in media detection. Open with `O_NONBLOCK` and `fstat` the handle.
- **Exact audio durations:** MP3 (Xing/Info or CBR frames), FLAC (STREAMINFO) and Ogg (last page granule) fall back to a size-based estimate that undercounts voice-bitrate audio (the response reserve absorbs it).
- **Gemini Files API limit on paid tiers:** the video docs table says 20 GB paid / 2 GB free; zen caps at 2,000,000,000 bytes. Verify and raise if paid accounts allow more.
- **Token estimates per model family:** video is 400 tokens/s since B4 because Gemini 2.5 models measured 383/s on the 3 s fixture (321/s at 10 s, 304/s at 30 s with audio; `count_tokens`, 2026-10-01), while Gemini 3 models charge about 100–127/s, so Gemini 3 requests reserve roughly 3–4x too much text budget. A per-family rate (capabilities or provider) would fix it. Audio stays 32/s (Gemini 3 docs say 25/s). If zen ever sets `media_resolution` explicitly, the "+ native text" PDF rows make 560/page low.
- **PDF page overcount:** incremental saves are counted again (errs high); the largest `/Count` among `/Type /Pages` nodes would be exact.
- **Prompt-file markers:** `handle_prompt_file` still uses `FILE NOT FOUND` / `NOT A FILE` / `FILE TOO LARGE` marker text as the prompt; only `--- ERROR` markers are skipped (pre-existing).
- **Binaries that start with a UTF-16/32 BOM:** the U+0000 check after BOM decoding catches few of them (about 8% of random UTF-16 payloads, 0% UTF-32). An incremental decoder with `errors="replace"` treating U+0000 or U+FFFD as binary caught all of them with no false positives in review probes; MPEG-1 Layer I audio with CRC additionally needs a C1-control check.
- **Gemini 2.5 Flash / Flash-Lite audio is flaky:** in the 2026-09-30 live probe both misheard the spoken number ("Pelican 5", "Pelican") and passed on a single retry, so audio is left unflagged for them. Re-probe (several runs) before flagging. `gemini-2.5-pro` (flagged) misheard once in the B4 live run through zen ("Pelican 002") and passed on rerun; its raw probe was 3/3. Separately, `gemini-2.5-flash-lite` is catalogued `supports_images: false` yet read the PDF and video frames; check its image support and fix the flag.
- **Files API upload names are not shown to users:** `media_attached` (with each upload's `files/...` name) is in `ModelResponse.metadata` and is persisted on simple-tool conversation turns, but it is not in `--json` or MCP output, and workflow and consensus tools do not persist it. Surface it so a user can delete an upload before Google's 48 h expiry.
- **Re-upload on a tool-level retry:** the simple tool's empty-response retry calls `generate_content` again, which uploads above-cap media a second time (the provider's own retry loop reuses uploads). The design's upload cache (`~/.zen/media_uploads.json`) would remove the duplicate.
- **Unusual but valid media headers become a placeholder:** QuickTime files whose first box is `skip`/`pnot`/`uuid`, RF64 WAV, and MP3 with stray bytes after the ID3 tag fail `_magic_matches`, so they get the BINARY FILE placeholder and only the model is told. When a requested path has a media extension, looks binary and fails the signature check, return an error to the user instead (final review, 2026-10-01).
- **Large media re-uploads on every follow-up and per consensus model:** first-turn media returns through `initial_context` and is uploaded again on each follow-up when above the inline cap; consensus uploads it once per model. The design's upload cache (`~/.zen/media_uploads.json`) would fix both, along with the tool-level retry case above.
- **Upload polling blocks the MCP server:** `_upload_media` sleeps up to 600 s inside synchronous `generate_content`, which tools call directly from async `execute`, so zen serves no other call (including parallel calls from Claude Code) while a large video processes. Normal API calls already block this way; wrap provider calls in `asyncio.to_thread`.
- **Binary sniff on symlinks:** `read_file_content` sniffs the resolved path's extension while media detection checks both names, so `notes.txt -> blob` with NUL bytes reports binary (read_files already resolves paths, so rare).

### Media input phase 2 follow-ups
Found while building and probing phase 2 (2026-10-03); none blocks it.
- **gpt-5-mini and gpt-5-nano are unflagged for PDF:** with the PDF attached (241 input tokens, like every other Chat model) they mostly answered "I can't access the PDF": 1/3 and 1/3 without a system prompt, 1/3 and 0/3 with one. Re-probe with `scripts/probe_media_support.py --provider openai --repeat 3 gpt-5-mini gpt-5-nano` after model updates; flag only on 3/3.
- **o3-mini is unflagged for PDF:** it has no vision, so it gets only the PDF's text layer and misread a scanned page. Text PDFs work (2/2); flag it only if zen ever distinguishes text-layer PDF support.
- **The three `-pro` models were probed once** (cost); every other flagged model passed twice (probe plus live test). The live tests skip them unless `ZEN_LIVE_PRO=1`.
- **Responses API `detail` is left to the default:** OpenAI's guide says `auto` means `high` page images on GPT-5.6 and later, `low` before. Set `detail` on `input_file` explicitly if PDF token cost on gpt-6 matters.
- **Auto-mode restriction error text:** `server.py`'s auto-mode error still names only the OpenAI and Google allow-lists; `ANTHROPIC_ALLOWED_MODELS` (and the others) are not mentioned.
- **PDF page rate per model family:** a letter-size scanned page cost 2,902 input tokens on gpt-6-luna/astra (Responses API), 1,025 on gpt-5.5 (Chat Completions) and 1,611 on claude-sonnet-5-5. OpenAI's rate (4,000) is sized for gpt-6, so it reserves about 4x too much on gpt-5.x; a text PDF on the Responses API cost far less (zebra.pdf: about 45 tokens against 240 on Chat). Solve with the per-family video rate above.
- **Anthropic size check ignores images:** `_check_request_size` counts the PDFs, prompt and system prompt against the 32 MB body limit but not images, so a request near the limit with images gets the API's HTTP 413 (reported as an error, not dropped).
- **Claude `cache_control` deferred to phase 5:** the design puts a cache marker on the last media block. A cache write costs 1.25x and only pays off when the same PDF is re-sent, which needs phase 5's continuation re-attach, so phase 2 sends none.

## Future features

### Gemini Omni video generation (`zen videogen`)
- **Recorded:** 2026-05-23 (deferred); contract established 2026-09-26.
- **What:** Prompt, optional reference images or a ≤10 s video → MP4 saved to disk, via `gemini-omni-1.1-flash`.
- **Contract:** Interactions API only (`client.interactions.create` / `POST /v1beta/interactions`), not `generateContent`. One MP4 per call, 3–10 s, 24 fps, 360p/720p/1080p/4k (1080p and 4k upscaled), 16:9 or 9:16, SynthID watermark. Base64 inline or `delivery: "uri"` then poll `files.get` until `ACTIVE`. No audio input. `gemini-omni-flash-preview` is deprecated 2026-09-30.
- **Cost and latency:** ~$0.10/s of output at 720p (5,792 tokens/s at $17.50/M), 360p about a third of that; third-party median ~42 s per clip.
- **Blocker to decide:** `client.interactions` exists from `google-genai` 1.55.0, but the video config types the contract above needs first appear in 2.10.0. No 1.x release (latest 1.75.0) has them or the interaction `steps` field (checked 2026-09-27). Using the SDK therefore means lifting the `google-genai<2` cap added in 2707f5d, a separate 1.x → 2.x migration (installed: 1.46.0). The alternative is calling `POST /v1beta/interactions` directly with httpx and keeping the cap.
- **Needs:** a new tool output contract (a file path rather than text) and a storage decision (default `~/.zen/media/`).

### Gemini explicit context caches
- **Recorded:** 2026-09-26
- **What:** `caches.create` with a TTL for large Gemini media reused across many turns.
- **Unblock:** the `cached_input_tokens` metrics from media-input v1. Build only if implicit prefix caching leaves meaningful savings on the table.

### TypeSafe Jev (structured-output decision maker)
- **Recorded:** 2026-09-26
- **What:** `typesafe/jev-router` on OpenRouter (listed 2026-09-25) picks the best model and reasoning effort per request, balancing quality, speed and cost. It runs on Jev (`~typesafe/jev-latest`), TypeSafe's first "System One" model. Accepts text, image, file, audio and video. Pricing is dynamic (OpenRouter reports `-1`, i.e. the price of whatever it routes to). No endpoints were published at time of recording.
- **Why it matters for zen:** zen's auto mode is itself a model-and-effort router built from hardcoded preference lists (`providers/*.py:get_preferred_model`) and catalog scores. Jev is a different kind of model — a decision maker with structured output rather than a text generator.
- **Possible uses:**
  1. Delegate auto-mode selection: ask Jev for `{model, reasoning_effort}` given the tool category, prompt size, attached media and allowed models, falling back to the current lists on error.
  2. Add `typesafe/jev-router` as an OpenRouter pseudo-model so `--model jev` lets it route end to end.
  3. Use Jev as the arbiter in `consensus` or as a structured judge in workflow tools.
- **Open questions:** Is `jev-latest` callable directly, and what is its structured-output schema? Latency and cost of a routing decision per call? How does it see zen's allowed-model restrictions? Does routing through it bypass zen's own capability checks?
- **Unblock:** endpoints published on OpenRouter plus the TypeSafe API/schema docs.

### OpenAI audio input
- **Recorded:** 2026-09-26
- **What:** Audio input to OpenAI via the `gpt-audio` / `gpt-audio-1.5` models (Chat Completions only, wav/mp3). GPT-5.x and GPT-6 models do not accept audio.
- **Needs:** catalog entries for the `gpt-audio` models plus a live probe.

### Media page and duration pre-checks
- **Recorded:** 2026-09-26
- **What:** Pre-check PDF page counts (Claude: 600 pages, 100 on 200k-context models) and video/audio duration before sending, instead of surfacing the provider's error.
- **Cost:** a PDF parser and ffprobe dependency.

### Unify images into the media pipeline
- **Recorded:** 2026-09-26
- **What:** Fold the separate `images` field into the media attachment path. Related finding: images are stored per turn but never re-sent on continuation (`utils/conversation_memory.get_conversation_image_list` has no callers), unlike the planned media behaviour.

## Maintenance and known issues

### Pre-existing Gemini alias-restriction test failures
- **Recorded:** 2026-09-26 (present since at least the 2026-09-10 commits)
- **What:** Three tests in `tests/test_alias_target_restrictions.py` fail on a clean tree. `./code_quality_checks.sh` runs pytest with `-x`, so these stop the script before later tests run.

### Account identifiers in committed cassettes
- **Recorded:** 2026-09-26
- **What:** Older cassettes in `tests/openai_cassettes/` (and git history) contain the OpenAI organization ID, the OpenAI project ID (`openai-project` header) and Cloudflare `set-cookie` values. The sanitizer now blanks these for new recordings (`tests/pii_sanitizer.py`). Decide whether to re-record or scrub the existing files.

### Stale model lists in docs
- **Recorded:** 2026-09-26
- **What:** The `model` option lists in `docs/tools/*.md` and `docs/advanced-usage.md` predate the GPT-6, Opus 5.5 and Grok 4.7 catalog. Regenerate them from `conf/*_models.json`.

### Responses API path gaps
- **Recorded:** 2026-09-27
- **Context:** `providers/openai_compatible.py:_generate_with_responses_endpoint` now carries the default OpenAI traffic: gpt-6-astra/sol/luna and the `sol`/`luna` aliases, natively and via OpenRouter. Before GPT-6 it carried only o3-pro, and it was only ever tested with one-shot prompts. `store` has been `false` since 2026-09-27.
- **System prompt role:** the system prompt is sent as a `user` message instead of `instructions` or a `developer` message. `Responses.create` accepts `instructions` from openai 1.66.0 onwards.
- **Multi-turn continuation never run live:** earlier assistant turns are replayed as `output_text` parts. The `responses_api_endpoint` simulator test covers one turn only and is not in `TEST_REGISTRY`.

### Unit tests still reach the network with dummy keys
- **Recorded:** 2026-09-28; narrowed 2026-10-03.
- **Fixed 2026-10-03:**
  - `tests/conftest.py` gives every test not marked integration dummy Gemini, OpenAI and xAI keys and no other provider key (`unit_tests_use_dummy_keys`). Real keys from the shell, the checkout's `.env` (loaded by `utils/env.py`) and `~/.zen/.env` no longer reach unit runs; `ZEN_NO_USER_ENV=1` stops `zen_cli.main` loading the last one. `tests/test_unit_suite_keys.py` guards both.
  - The suite went from 37 s to 13 s with the developer's keys exported, because `tests/test_large_prompt_handling.py` had been making paid Gemini calls on every local run.
  - The checkout's own `src/` comes first on `sys.path`, since a worktree's editable install otherwise imports the main checkout's `zen_cli`.
- **Still open:** 9 unit tests open real connections, now with a dummy key, so they fail fast and cost nothing. A socket-blocking run on 2026-10-03 found them:
  - **Gemini API:** 5 in `test_large_prompt_handling.py` (chat, prompt-file, boundary and empty-prompt cases) and 3 in `test_collaboration.py::TestDynamicContextRequests`. The `test_collaboration.py` ones reach Google despite mocking `get_provider`.
  - **GitHub:** `test_server.py::test_handle_version`, through the version check.

  Mock them, or block sockets for unit tests, to make the suite offline.

### Simulator tests omit `working_directory_absolute_path`
- **Recorded:** 2026-09-28
- **What:** `chat` requires `working_directory_absolute_path`, but no simulator test except `responses_api_endpoint` passes it, so their chat calls likely fail validation. The Responses endpoint test used to report exactly that validation error as a pass (fixed in b271101). Audit the others the same way: pass a temp directory and make every test fail on a tool error.

## Routing and ranking

### Auto mode ignores the tool category for OpenRouter/Azure/DIAL/Custom-only setups
- **Recorded:** 2026-09-27 (behaviour dates from upstream 1a8ec2e, 2025-08)
- **What:** these providers inherit `get_preferred_model`, which returns `None` (`providers/base.py:343`). `ModelProviderRegistry.get_preferred_fallback_model` then returns `sorted(allowed_models)[0]` (`providers/registry.py:417`), an alphabetical pick across canonical names and aliases. In OpenRouter-only auto mode every category resolves to alias `5.1` (openai/gpt-5.2). With the docstring example `OPENROUTER_ALLOWED_MODELS=opus,sonnet,mistral`, chat goes to Opus 5.5, the most expensive allowed model. Requests still succeed. The default setup is unaffected because xAI is first in priority.
- **Fix direction:** fix this in the registry: stop at the first provider that has allowed models, and when it returns no preference, rank its canonical names (not aliases) by capability for the category.
- **Warning:** do not add an `OpenRouterProvider.get_preferred_model` override. A verifier showed it lets a lower-priority OpenRouter preference beat Custom, Azure and DIAL: with Custom+OpenRouter, FAST_RESPONSE moved from `llama3.2` to `openai/gpt-6-luna`.
- **Tests:** strengthen `tests/test_auto_mode_comprehensive.py::test_openrouter_fallback_when_no_native_apis`, which only asserts "not None", and add a Custom+OpenRouter case.

### Gemini `find_best` ranks by reverse string order
- **Recorded:** 2026-09-27 (code dates from 2025-08)
- **What:** `sorted(candidates, reverse=True)[0]` (`providers/gemini.py:482`) ranks gemini-3.5-flash-lite above gemini-3.5-flash, and the alias `gemini3.5-flash` above gemini-3.8-flash. With `GOOGLE_ALLOWED_MODELS=gemini-3.5-flash,gemini-3.5-flash-lite`, EXTENDED_REASONING and BALANCED run on flash-lite (score 13) instead of flash (19). This needs a restriction, auto mode and no xAI key. Unrestricted routing is correct.
- **Fix direction:** resolve candidates through `_resolve_model_name` and dedupe; a canonical-only filter would empty an alias-only allowlist. Rank by `(intelligence_score, name)`, optionally keep FAST_RESPONSE preferring flash-lite, and add a regression test for the flash/flash-lite restriction.

### OpenAI/xAI FAST_RESPONSE fallback returns the most capable model
- **Recorded:** 2026-09-27 (code predates the GPT-6 work)
- **What:** when no allowed model is on the FAST list, `providers/openai.py:155` and `providers/xai.py:95` return `allowed_models[0]`. That list is sorted by rank, highest first, so `OPENAI_ALLOWED_MODELS=gpt-5-nano,gpt-6-astra` routes chat to gpt-6-astra. gpt-5-nano, gpt-5.6-terra and gpt-4.1 are in no OpenAI route list. This needs an OpenAI restriction with OpenAI as the first provider that has allowed models; none of the documented examples trigger it.
- **Fix direction:** in the FAST_RESPONSE branch, fall back to the lowest-rank allowed canonical model: walk the list from the end and skip aliases, because `allowed_models` contains aliases. Put this in a shared helper used by both providers. Add gpt-5-nano to the end of the FAST list, and gpt-5.6-terra and gpt-4.1 to BALANCED.

## Watchlist (not addable yet)

- **xAI Grok 4.6 / 4.7 fast variants:** announced at 2× speed and 2× price; no public slug in `/v1/models`.
- **xAI Grok Imagine Image 2.0:** image generation; zen has no image-output path.
