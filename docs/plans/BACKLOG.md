# zen-cli Feature Backlog

Future work that has been scoped or discovered but deliberately not started. Add the date an item was recorded and what would unblock it. Move an item into a `docs/plans/YYYY-MM-DD-<topic>-design.md` when it is picked up.

## Planned

### Media input (PDF, audio, video)
- **Recorded:** 2026-09-26
- **Status:** Phase 1 (core + Gemini) merged 2026-10-01. Phase 2 (Claude and OpenAI, PDF only) done 2026-10-03: `docs/plans/2026-10-03-media-input-phase2-status.md`. Phase 3 (xAI, PDF only, named Grok models only) done 2026-10-03, all 7 Grok models flagged: `docs/plans/2026-10-03-media-input-phase3-status.md`. Phase 5a (upload cache, non-blocking model calls, media metadata in the output) done 2026-10-04: `docs/plans/2026-10-04-media-input-phase5a-status.md`. Phase 4 (OpenRouter, PDF/audio/video, native reading only) done 2026-10-04: `docs/plans/2026-10-04-media-input-phase4-status.md`. Phase 5b (follow-up re-attach, stable prefix, cached-token metrics, Claude `cache_control`) done 2026-10-04: `docs/plans/2026-10-04-media-input-phase5b-status.md`; its live cache probes are pending. Design: `docs/plans/2026-09-26-media-input-design.md`.

### Media input phase 1 follow-ups
Found by the phase 1 task reviews (2026-09-28 to 09-30); none blocks phase 1.
- **Duplicate attachments on case-insensitive disks and hard links:** `CLIP.mp4` and `clip.mp4`, or a hard link, attach twice. Dedupe on `(st_dev, st_ino)`.
- **FIFO swap window:** a small gap between `is_file()` and `open()` in media detection. Open with `O_NONBLOCK` and `fstat` the handle.
- **Exact audio durations:** MP3 (Xing/Info or CBR frames), FLAC (STREAMINFO) and Ogg (last page granule) fall back to a size-based estimate that undercounts voice-bitrate audio (the response reserve absorbs it).
- **Gemini Files API limit on paid tiers:** the video docs table says 20 GB paid / 2 GB free; zen caps at 2,000,000,000 bytes. Verify and raise if paid accounts allow more.
- **Token estimates per model family (mostly fixed 2026-10-03):** catalogs now carry per-model `pdf_tokens_per_page` / `video_tokens_per_second` (model, then provider, then global; `utils.media.estimate_media_tokens_for`). Gemini 3 models reserve 160 tokens/s of video (measured about 100–127/s) instead of 400; OpenAI gpt-5.x families set measured PDF rates. Still open: audio stays 32/s for every model (Gemini 3 docs say 25/s), and if zen ever sets `media_resolution` explicitly, the "+ native text" PDF rows make Gemini's 560/page low.
- **PDF page overcount:** incremental saves are counted again (errs high); the largest `/Count` among `/Type /Pages` nodes would be exact.
- **Prompt-file markers:** `handle_prompt_file` still uses `FILE NOT FOUND` / `NOT A FILE` / `FILE TOO LARGE` marker text as the prompt; only `--- ERROR` markers are skipped (pre-existing).
- **Binaries that start with a UTF-16/32 BOM:** the U+0000 check after BOM decoding catches few of them (about 8% of random UTF-16 payloads, 0% UTF-32). An incremental decoder with `errors="replace"` treating U+0000 or U+FFFD as binary caught all of them with no false positives in review probes; MPEG-1 Layer I audio with CRC additionally needs a C1-control check.
- **Gemini 2.5 Flash / Flash-Lite audio is flaky:** in the 2026-09-30 live probe both misheard the spoken number ("Pelican 5", "Pelican") and passed on a single retry, so audio is left unflagged for them. Re-probe (several runs) before flagging. `gemini-2.5-pro` (flagged) misheard once in the B4 live run through zen ("Pelican 002") and passed on rerun; its raw probe was 3/3. Separately, `gemini-2.5-flash-lite` is catalogued `supports_images: false` yet read the PDF and video frames; check its image support and fix the flag.
- **Unusual but valid media headers become a placeholder:** QuickTime files whose first box is `skip`/`pnot`/`uuid`, RF64 WAV, and MP3 with stray bytes after the ID3 tag fail `_magic_matches`, so they get the BINARY FILE placeholder and only the model is told. When a requested path has a media extension, looks binary and fails the signature check, return an error to the user instead (final review, 2026-10-01).
- **Binary sniff on symlinks:** `read_file_content` sniffs the resolved path's extension while media detection checks both names, so `notes.txt -> blob` with NUL bytes reports binary (read_files already resolves paths, so rare).

### Media input phase 2 follow-ups
Found while building and probing phase 2 (2026-10-03); none blocks it.
- **gpt-5-mini and gpt-5-nano are unflagged for PDF (natively and on OpenRouter):** their results vary from day to day.
  - **2026-10-03, phase 2:** with the PDF attached (241 input tokens) they mostly answered "I can't access the PDF": 1/3 each.
  - **2026-10-03, bare re-probe:** mini 3/3, nano 2/3.
  - **2026-10-04, through zen's provider with `CHAT_PROMPT`:** zebra.pdf 3/3 each, and the image-only letter page 3/3 each. OpenRouter: 2/2 each, plus both checks.
  - **Correction:** a 2026-10-03 note said they failed 0/6 under `CHAT_PROMPT`. That run passed the fixture by a relative path, which zen classifies as a text file, so no PDF was attached. It is retracted.
  - **To do:** flag both after another clean 3/3 day through `tests/test_media_live.py`.
- **o3-mini is unflagged for PDF:** it has no vision, so it gets only the PDF's text layer and misread a scanned page. Text PDFs work (2/2); flag it only if zen ever distinguishes text-layer PDF support.
- **The three `-pro` models were probed once** (cost); every other flagged model passed twice (probe plus live test). The live tests skip them unless `ZEN_LIVE_PRO=1`.
- **Responses API `detail` is left to the default:** OpenAI's guide says `auto` means `high` page images on GPT-5.6 and later, `low` before. Set `detail` on `input_file` explicitly if PDF token cost on gpt-6 matters.

### Media input phase 3 follow-ups
Found while building phase 3 (2026-10-03); none blocks it.
- **xAI's reported cost is not copied:** `server_side_tool_calls` reaches the output with a warning and a `media_notice` line (phase 5a), but the usage's `cost_in_usd_ticks` is not copied.
- **xAI's document search is unpredictable:** on 2026-10-03 the grok-4.20 models ran `attachment_search` 2–3 times even for a one-page PDF (up to 8,889 input tokens), while the other Grok models ran none on four pages. The per-page reserve (2,500; 7,500 on grok-4.20) is set from one run each. Re-probe with longer PDFs (20+ pages) before relying on Grok for long documents. (Phase 5a warns, and notes it in the output, whenever the search runs.)
- **No sampling parameters on the Responses path:** Grok media requests, like every Responses API request, carry no `temperature`; text-only Grok requests do.

### Media input phase 4 follow-ups
Found while building phase 4 (2026-10-04); none blocks it.
- **Four catalog ids are not in OpenRouter's models list:** `anthropic/claude-sonnet-4-6`, `anthropic/claude-opus-4-8`, `-4-7` and `-4-6`. OpenRouter lists them with dots (`anthropic/claude-sonnet-4.6`), so `--candidates` finds no kinds for them and the probe skips them. Check whether OpenRouter still accepts the hyphenated ids; rename them or add aliases if not.
- **Parse check, verified live 2026-10-04:**
  - Forcing a parser engine was refused on both endpoints (`mistral-ocr`; `cloudflare-ai`).
  - Chat Completions marks a parsed file with a `type: "file"` annotation; `/responses` marks it only with `file_citation`.
  - No reply carried an `openrouter_metadata.pipeline`, so the stage-name match is untested and kept only as a fallback.
  - A parsed reply also used far fewer prompt tokens (90 against 553 natively for zebra.pdf).
- **mistralai/mistral-large-2512 is unverified:** upstream 429s on most tries (2026-10-04). Re-probe it later; it read the scanned page once.
- **OpenRouter's `usage.cost` is not surfaced:** it is not copied into the response metadata. (The cached-token counts are, as `cached_input_tokens`, since phase 5b.)
- **The x-ai/* models are PDF candidates:** their `input_modalities` list `file`, so a default `--provider openrouter` probe run sends them PDFs although policy never flags them. Name the models to probe, or skip `x-ai/` in the default list.
- **The 32 MB inline cap is inferred:** OpenRouter documents no limit for inline data; 32 MB is the smallest upstream body limit (Anthropic's). Raise it per model if larger requests prove to work.

### Media input phase 5a follow-ups
Found while building phase 5a (2026-10-04); none blocks it.
- **Two consensus runs at once share one roster between steps (older than 5a):** the per-tool lock covers one call, but `ConsensusTool` keeps `models_to_consult`, `accumulated_responses` and `work_history` on the shared instance across calls. A second consensus started between another's steps resets them. It is easier to hit now that model calls no longer block the server. Fix: rebuild the roster from the thread (`continuation_id`) on every step.
- **Proxy variables during client creation:** `suppress_env_vars` now serializes overlapping suppressions (a lock), but a Gemini or Anthropic client built in another thread at that moment still sees the proxy variables missing. This matters only with proxies set. Passing `trust_env=False` to the httpx clients, instead of editing `os.environ`, would remove the window.
- **Calls of one tool queue behind each other:** `server.handle_call_tool` holds a per-tool lock, because the shared instances in `server.TOOLS` keep per-run state. A chat call waiting on a 600 s Gemini upload makes the next chat call wait too; other tools are unaffected. A fresh tool instance per call (or per-run state moved off the instance) would remove the lock.
- **Workflow and consensus turns do not persist `media_attached`:** the output now shows it, but only simple-tool turns store it in conversation memory; workflow and consensus turns keep no record of their uploads. (Since phase 5b every turn records the media paths it attached, `ConversationTurn.media`, but not how they travelled.)
- **The cache hashes the whole file on every upload-sized call:** up to 2 GB read per attachment above the inline cap (off the event loop since 5a). A memo keyed on `(path, size, mtime_ns, inode)` would skip it.
- **One cache entry per content, not per API key:** a user alternating two Gemini keys overwrites the other key's entry (last writer wins), so each switch uploads again. Keying entries by fingerprint too would keep both.
- **Lazy provider clients can be built twice:** model calls now run in worker threads, so two concurrent first calls on one provider may each create its SDK client; one is discarded. Harmless, but a lock in each `client` property would avoid it.

### Media input phase 5b follow-ups
Found while building phase 5b (2026-10-04); none blocks it.
- **gpt-6 on the Responses API rarely reads its prompt cache for file requests:** on 2026-10-04 the cache was written on 10 of 11 identical-prefix requests (`cache_write_tokens`) and read once. `prompt_cache_key`, dropping `reasoning`, and a 45 s gap made no difference. Re-check after model updates; it may need OpenAI-side changes.
- **Gemini through OpenRouter misses the implicit cache:** OpenRouter spreads requests over two Google endpoints, each with its own cache. Pinning one (`provider.order` plus `allow_fallbacks: false`) would raise the hit rate but cost availability. Decide if Gemini-via-OpenRouter media turns out to be common.
- **Threads stored before 5b lose their first-turn media:** `initial_context` no longer carries media and old turns recorded none, so a follow-up to a thread from before the upgrade (file storage keeps threads 3 hours) re-attaches nothing.
- **Gemini can switch an earlier file to an upload:** above the 60 MB inline cap the largest files upload first, so a follow-up that adds media can move an earlier inline file to the Files API. That turn's prefix changes and misses the cache; later turns are stable again. Uploading the newest files first would keep the prefix.
- **Media a refused call named is not re-attached, and not mentioned:** turns record only what a model call actually attached, and the old "media not attached" note is gone. A follow-up to a refused PDF call does not resend that PDF.
- **In-process (CLI) auto routing skips a workflow's earlier steps' media:** `BaseTool._resolve_model_context` counts the call's files and the thread's recorded media, but not the files earlier workflow steps named, which `server._call_media_kinds` counts. CLI workflow sessions resend their files, so this matters only for in-process callers with `continuation_id`.
- **History sizing on a model fallback ignores earlier media:** `server.reconstruct_thread_context` picks a fallback model for sizing the history from the call's own media kinds; routing then counts the earlier media too and may pick another model.
- **debug trims re-attached media against the file allocation:** re-attach in workflow expert calls uses the model's file allocation; debug's own file embedding uses the remaining budget after history, so the two can differ.
- **Claude's 32 MB body check counts the prompt too:** re-attach drops older media to fit `MEDIA_REQUEST_MAX_BYTES` (media only); a large prompt plus media can still fail Anthropic's whole-body check.
- **Claude's `total_tokens` leaves out cache reads and writes:** `input_tokens` excludes them (Anthropic's usage), so a cached Claude request reports a small total. The counts are in `cached_input_tokens` and `cache_write_input_tokens`.

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
- **Unblock:** the `cached_input_tokens` metrics, reported since phase 5b (2026-10-04). Build only if the live second-turn probes show implicit prefix caching leaving meaningful savings on the table.

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
- **What:** Fold the separate `images` field into the media attachment path. Related finding: images are stored per turn but never re-sent on continuation (`utils/conversation_memory.get_conversation_image_list` has no callers), unlike media, which follow-ups re-attach since phase 5b.

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

### Unit tests reached the network and read machine-local config (fixed)
- **Recorded:** 2026-09-28; narrowed 2026-10-03; fixed 2026-10-05 after John's report.
- **Fixed 2026-10-03:**
  - `tests/conftest.py` gives every test not marked integration dummy Gemini, OpenAI and xAI keys and no other provider key (`unit_tests_use_dummy_keys`). Real keys from the shell, the checkout's `.env` (loaded by `utils/env.py`) and `~/.zen/.env` no longer reach unit runs; `ZEN_NO_USER_ENV=1` stops `zen_cli.main` loading the last one. `tests/test_unit_suite_keys.py` guards both.
  - The suite went from 37 s to 13 s with the developer's keys exported, because `tests/test_large_prompt_handling.py` had been making paid Gemini calls on every local run.
  - The checkout's own `src/` comes first on `sys.path`, since a worktree's editable install otherwise imports the main checkout's `zen_cli`.
- **Fixed 2026-10-05:**
  - **Offline:** 9 unit tests still called the Gemini API (with the dummy key) or GitHub. The 2026-10-03 note assumed they failed fast; on John's network the Gemini call stalled and the run never finished. They mocked `BaseTool.get_model_provider`, but tools take their provider from the registry (`ModelContext.provider`); they now patch `ModelProviderRegistry.get_provider_for_model` (and the version check). An autouse fixture (`unit_tests_stay_offline`, `tests/network_guard.py`) refuses non-loopback lookups and connections and fails any unit test that tries one.
  - **Local models:** `conf/*.local.json` overrides changed auto-mode picks in tests (a developer's LM Studio model won FAST_RESPONSE). `ZEN_NO_LOCAL_MODELS=1` skips them; it is read at import, because tests that patch `os.environ` with `clear=True` would otherwise turn it off. conftest sets it.
  - **Custom endpoint:** `CUSTOM_API_URL` from the checkout's `.env` registered the Custom provider in unit runs (`llama3.2` joined the consensus panel). The fixture now unsets it with the keys (`UNSET_PROVIDER_VARS`).

### Gemini requests have no timeout by default
- **Recorded:** 2026-10-05 (found while fixing the hanging unit test above)
- **No default:** `providers/gemini.py` sets `HttpOptions.timeout` only when a `CUSTOM_*_TIMEOUT` variable is set. Otherwise google-genai sends `timeout=None` to httpx, so a stalled connection waits forever, in the MCP server and the CLI as in the test.
- **Wrong unit:** `_resolve_http_timeout` passes seconds, but `HttpOptions.timeout` is in milliseconds (`google/genai/_api_client.py:get_timeout_in_seconds`), so `CUSTOM_READ_TIMEOUT=600` gives Gemini a 0.6 s timeout.
- **Fix:** convert to milliseconds and set a default (the OpenAI-compatible providers default to a 30 s connect and 10 min read timeout). Large uploads go through the Files API, so check that path's timeout too.

### Simulator tests omit `working_directory_absolute_path`
- **Recorded:** 2026-09-28
- **What:** `chat` requires `working_directory_absolute_path`, but no simulator test except `responses_api_endpoint` passes it, so their chat calls likely fail validation. The Responses endpoint test used to report exactly that validation error as a pass (fixed in b271101). Audit the others the same way: pass a temp directory and make every test fail on a tool error.

## Routing and ranking

### Rank-based auto-mode picks ignore price and speed
- **Recorded:** 2026-10-03
- **What:** Azure, DIAL and Custom state no preference, so the first of them with allowed models picks by capability rank (`ModelProviderRegistry._pick_by_rank`). Rank picks look at neither price nor latency: the catalogs have no field for either (some descriptions quote prices). The one exception is the `premium` catalog flag (the -pro tier and o3-pro): rank-based FAST_RESPONSE picks, here and in the OpenAI, xAI and Anthropic fallbacks (`ModelProvider.pick_fast_by_rank`), skip premium models unless nothing else is allowed.
- **OpenRouter (fixed 2026-10-04):** `OpenRouterProvider.get_preferred_model` now picks from per-category lists (`PREFERRED_MODELS`) that mirror the native providers' first choices: with every model allowed, EXTENDED_REASONING → `openai/gpt-6-astra`, BALANCED → `openai/gpt-6-sol`, FAST_RESPONSE → `openai/gpt-6-luna` (by rank they were `anthropic/claude-fable-5.1` twice, on the name tie-break, and `mistralai/devstral-2512`). Rank picks remain for an OpenRouter allow-list with nothing on the category's list. The override cannot beat Custom, Azure or DIAL, because the registry stops at the first provider with allowed models; `tests/test_auto_mode_restricted_routing.py::test_custom_endpoint_keeps_every_category_ahead_of_openrouter` guards that.
- **Fix direction (remaining):** add price or latency to the catalogs, or preference lists for Custom, Azure and DIAL.

## Watchlist (not addable yet)

- **xAI Grok 4.6 / 4.7 fast variants:** announced at 2× speed and 2× price; no public slug in `/v1/models`.
- **xAI Grok Imagine Image 2.0:** image generation; zen has no image-output path.
