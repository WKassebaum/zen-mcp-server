# zen-cli Feature Backlog

Future work that has been scoped or discovered but deliberately not started. Add the date an item was recorded and what would unblock it. Move an item into a `docs/plans/YYYY-MM-DD-<topic>-design.md` when it is picked up.

## Planned

### Media input (PDF, audio, video)
- **Recorded:** 2026-09-26
- **Status:** Design validated — `docs/plans/2026-09-26-media-input-design.md`. Implementation not started.

## Future features

### Gemini Omni video generation (`zen videogen`)
- **Recorded:** 2026-05-23 (deferred); contract established 2026-09-26.
- **What:** Prompt, optional reference images or a ≤10 s video → MP4 saved to disk, via `gemini-omni-1.1-flash`.
- **Contract:** Interactions API only (`client.interactions.create` / `POST /v1beta/interactions`), not `generateContent`. One MP4 per call, 3–10 s, 24 fps, 360p/720p/1080p/4k (1080p and 4k upscaled), 16:9 or 9:16, SynthID watermark. Base64 inline or `delivery: "uri"` then poll `files.get` until `ACTIVE`. No audio input. `gemini-omni-flash-preview` is deprecated 2026-09-30.
- **Cost and latency:** ~$0.10/s of output at 720p (5,792 tokens/s at $17.50/M), 360p about a third of that; third-party median ~42 s per clip.
- **Blocker to decide:** `google-genai` ≥ 2.10 is needed for `interactions` (installed: 1.46, a major-version bump), or call the REST endpoint directly with httpx.
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
- **What:** Older cassettes in `tests/openai_cassettes/` (and git history) contain the OpenAI organization ID and Cloudflare `set-cookie` values. The sanitizer now blanks these for new recordings (`tests/pii_sanitizer.py`). Decide whether to re-record or scrub the existing files.

### Stale model lists in docs
- **Recorded:** 2026-09-26
- **What:** The `model` option lists in `docs/tools/*.md` and `docs/advanced-usage.md` predate the GPT-6, Opus 5.5 and Grok 4.7 catalog. Regenerate them from `conf/*_models.json`.

## Watchlist (not addable yet)

- **xAI Grok 4.6 / 4.7 fast variants:** announced at 2× speed and 2× price; no public slug in `/v1/models`.
- **xAI Grok Imagine Image 2.0:** image generation; zen has no image-output path.
