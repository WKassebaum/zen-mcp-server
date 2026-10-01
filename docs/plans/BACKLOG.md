# zen-cli Feature Backlog

Future work that has been scoped or discovered but deliberately not started. Add the date an item was recorded and what would unblock it. Move an item into a `docs/plans/YYYY-MM-DD-<topic>-design.md` when it is picked up.

## Planned

### Media input (PDF, audio, video)
- **Recorded:** 2026-09-26
- **Status:** Design validated — `docs/plans/2026-09-26-media-input-design.md`. Implementation not started.

### Media input phase 1 follow-ups
Found by the phase 1 task reviews (2026-09-28 to 09-30); none blocks phase 1.
- **Duplicate attachments on case-insensitive disks and hard links:** `CLIP.mp4` and `clip.mp4`, or a hard link, attach twice. Dedupe on `(st_dev, st_ino)`.
- **FIFO swap window:** a small gap between `is_file()` and `open()` in media detection. Open with `O_NONBLOCK` and `fstat` the handle.
- **Exact audio durations:** MP3 (Xing/Info or CBR frames), FLAC (STREAMINFO) and Ogg (last page granule) fall back to a size-based estimate that undercounts voice-bitrate audio (the response reserve absorbs it).
- **Gemini Files API limit on paid tiers:** the video docs table says 20 GB paid / 2 GB free; zen caps at 2,000,000,000 bytes. Verify and raise if paid accounts allow more.
- **Token estimates vs Gemini 3 defaults:** the media-resolution table gives video 70 tokens/frame and audio 25 tokens/s; zen's 300/s and 32/s err high. If zen ever sets `media_resolution` explicitly, the "+ native text" PDF rows make 560/page low.
- **PDF page overcount:** incremental saves are counted again (errs high); the largest `/Count` among `/Type /Pages` nodes would be exact.
- **Prompt-file markers:** `handle_prompt_file` still uses `FILE NOT FOUND` / `NOT A FILE` / `FILE TOO LARGE` marker text as the prompt; only `--- ERROR` markers are skipped (pre-existing).
- **Binaries that start with a UTF-16/32 BOM:** the U+0000 check after BOM decoding catches few of them (about 8% of random UTF-16 payloads, 0% UTF-32). An incremental decoder with `errors="replace"` treating U+0000 or U+FFFD as binary caught all of them with no false positives in review probes; MPEG-1 Layer I audio with CRC additionally needs a C1-control check.
- **Gemini 2.5 Flash / Flash-Lite audio is flaky:** in the 2026-09-30 live probe both misheard the spoken number ("Pelican 5", "Pelican") and passed on a single retry, so audio is left unflagged for them. Re-probe (several runs) before flagging. Separately, `gemini-2.5-flash-lite` is catalogued `supports_images: false` yet read the PDF and video frames; check its image support and fix the flag.
- **Binary sniff on symlinks:** `read_file_content` sniffs the resolved path's extension while media detection checks both names, so `notes.txt -> blob` with NUL bytes reports binary (read_files already resolves paths, so rare).

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
- **Usage reported as zero:** `_extract_usage` reads `prompt_tokens` / `completion_tokens`, but a Responses `usage` object has `input_tokens` / `output_tokens`. Input and output are therefore reported as 0; only `total_tokens` is right.
- **Latent crash on output caps:** a non-empty `max_output_tokens` is forwarded as `max_completion_tokens`, which `Responses.create` does not accept (the parameter is `max_output_tokens`). The SDK raises `TypeError: ... unexpected keyword argument 'max_completion_tokens'`. No caller passes a value today.

### Unit suite is not hermetic in CI
- **Recorded:** 2026-09-28
- **What:** With no real API keys (CI conditions), two tests fail besides the three alias-restriction failures: `tests/test_large_prompt_handling.py::test_large_file_context_does_not_trigger_mcp_prompt_limit` makes a real Gemini request (locally it passes only by spending the exported `GEMINI_API_KEY` on every suite run), and `tests/test_zen_storage_backends.py::test_default_backend` depends on leftover state and environment. Mock the first; isolate the second.

### Simulator tests omit `working_directory_absolute_path`
- **Recorded:** 2026-09-28
- **What:** `chat` requires `working_directory_absolute_path`, but no simulator test except `responses_api_endpoint` passes it, so their chat calls likely fail validation. The Responses endpoint test used to report exactly that validation error as a pass (fixed in b271101). Audit the others the same way: pass a temp directory and make every test fail on a tool error.

### MCP follow-ups embed the conversation history twice
- **Recorded:** 2026-10-01 (found during media input batch B2)
- **What:** `tools/simple/base.py` decides whether `server.py` already embedded the history by looking for `"=== CONVERSATION HISTORY ==="`, but `build_conversation_history` writes `"=== CONVERSATION HISTORY (CONTINUATION) ==="`. The check never matches, so on every MCP follow-up a simple tool treats the server-built prompt as raw user input: after `server.py` has stored the user turn, the tool stores a second user turn whose text is the whole server prompt, history included, and then wraps that prompt in a freshly built history. Each follow-up therefore sends the history twice and nests it into the stored thread, so threads grow much faster than their content. Present since upstream 2025-06 (`2a067a7` added the check, `7462599`/`fccfb0d` the header); confirm with a test before fixing. Match the real header, or have `server.py` mark the arguments as already reconstructed, and add a test that runs a two-turn MCP conversation and counts the history blocks and stored turns.

## Routing and ranking

### Auto mode ignores the tool category for OpenRouter/Azure/DIAL/Custom-only setups
- **Recorded:** 2026-09-27 (behaviour dates from upstream 1a8ec2e, 2025-08)
- **What:** these providers inherit `get_preferred_model`, which returns `None` (`providers/base.py:343`). `ModelProviderRegistry.get_preferred_fallback_model` then returns `sorted(allowed_models)[0]` (`providers/registry.py:417`), an alphabetical pick across canonical names and aliases. In OpenRouter-only auto mode every category resolves to alias `5.1` (openai/gpt-5.2). With the docstring example `OPENROUTER_ALLOWED_MODELS=opus,sonnet,mistral`, chat goes to Opus 5.5, the most expensive allowed model. Requests still succeed. The default setup is unaffected because xAI is first in priority.
- **Fix direction:** fix this in the registry: stop at the first provider that has allowed models, and when it returns no preference, rank its canonical names (not aliases) by capability for the category.
- **Warning:** do not add an `OpenRouterProvider.get_preferred_model` override. A verifier showed it lets a lower-priority OpenRouter preference beat Custom, Azure and DIAL: with Custom+OpenRouter, FAST_RESPONSE moved from `llama3.2` to `openai/gpt-6-luna`.
- **Tests:** strengthen `tests/test_auto_mode_comprehensive.py::test_openrouter_fallback_when_no_native_apis`, which only asserts "not None", and add a Custom+OpenRouter case.

### Capability rank clamps at 100, so intelligence_score above 18 is ignored
- **Recorded:** 2026-09-27
- **What:** `get_effective_capability_rank()` returns `max(0, min(100, score))` (`providers/shared/model_capabilities.py:111`). Every model with `intelligence_score` 18 or higher therefore ties, and ties sort by name. `listmodels` lists grok-4.5 above grok-4.7, Opus 5.5 last among the Opus entries and gpt-6-* after gpt-5.2. The auto-mode "Top models" hint in the tool schema shows gpt-5.2 and OpenRouter Opus 4.6/4.7 and none of the new flagships. Actual routing uses the hardcoded route lists and is unaffected. The 9dd618f commit message claims an ordering that does not happen.
- **Media bonus (2026-09-30):** the +1 per media kind added in media-input phase 1 has no effect on any model that already ranks 100, including every flagged Gemini 3.x model, and it applies to every request, not only media requests, so it reorders text-only listings for unsaturated models (e.g. gemini-3-flash-preview 95 → 98). When the clamp is fixed, decide whether media kinds should raise general rank or only break ties inside media-capable selection (`find_media_capable_models`). Also: `docs/model_ranking.md` describes a "Custom endpoints: -1" penalty that no code applies.
- **Fix direction:** remove the upper clamp (`return max(0, score)`). In simulation the unit suite passed and the top five became fable-5.1, gpt-6-astra, gemini-3.1-pro, gpt-6-sol and grok-4.7. Then spread the Anthropic scores, since every Opus entry is at 19. A secondary sort key would also work, but it needs edits at five sort sites.

### Gemini `find_best` ranks by reverse string order
- **Recorded:** 2026-09-27 (code dates from 2025-08)
- **What:** `sorted(candidates, reverse=True)[0]` (`providers/gemini.py:482`) ranks gemini-3.5-flash-lite above gemini-3.5-flash, and the alias `gemini3.5-flash` above gemini-3.8-flash. With `GOOGLE_ALLOWED_MODELS=gemini-3.5-flash,gemini-3.5-flash-lite`, EXTENDED_REASONING and BALANCED run on flash-lite (score 13) instead of flash (19). This needs a restriction, auto mode and no xAI key. Unrestricted routing is correct.
- **Fix direction:** resolve candidates through `_resolve_model_name` and dedupe; a canonical-only filter would empty an alias-only allowlist. Rank by `(intelligence_score, name)`, optionally keep FAST_RESPONSE preferring flash-lite, and add a regression test for the flash/flash-lite restriction.

### OpenAI/xAI FAST_RESPONSE fallback returns the most capable model
- **Recorded:** 2026-09-27 (code predates the GPT-6 work)
- **What:** when no allowed model is on the FAST list, `providers/openai.py:155` and `providers/xai.py:95` return `allowed_models[0]`. That list is sorted by rank, highest first, so `OPENAI_ALLOWED_MODELS=gpt-5-nano,gpt-6-astra` routes chat to gpt-6-astra. gpt-5-nano, gpt-5.6-terra and gpt-4.1 are in no OpenAI route list. This needs an OpenAI restriction with OpenAI as the first provider that has allowed models; none of the documented examples trigger it.
- **Fix direction:** in the FAST_RESPONSE branch, fall back to the lowest-rank allowed canonical model: walk the list from the end and skip aliases, because `allowed_models` contains aliases. Put this in a shared helper used by both providers. Add gpt-5-nano to the end of the FAST list, and gpt-5.6-terra and gpt-4.1 to BALANCED.

### MCP server does not register the native Anthropic provider
- **Recorded:** 2026-09-27
- **What:** `server.configure_providers()` never registers `AnthropicProvider`; only the CLI does (`src/zen_cli/main.py:167-170`). This holds even though the live MCP entry passes `ANTHROPIC_API_KEY`. In the MCP server, Claude models therefore resolve only through OpenRouter, and the dash-form native IDs (`claude-opus-5-5`, `claude-fable-5-1`, `claude-sonnet-5`, ...) return "not available". The zen-skill now recommends `opus` / `fable` / `sonnet`, which resolve in both.
- **Decision needed (billing):** there are two options:
  1. Register ANTHROPIC in `server.configure_providers()`, mirroring the CLI. This moves `opus` / `fable` / `sonnet` from OpenRouter to native Anthropic billing.
  2. Add the dash-form native IDs as aliases on the `anthropic/*` OpenRouter entries. This was verified to resolve with no collisions.

## Watchlist (not addable yet)

- **xAI Grok 4.6 / 4.7 fast variants:** announced at 2× speed and 2× price; no public slug in `/v1/models`.
- **xAI Grok Imagine Image 2.0:** image generation; zen has no image-output path.
