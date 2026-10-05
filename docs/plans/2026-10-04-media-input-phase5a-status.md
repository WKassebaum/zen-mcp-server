# Media Input Phase 5a — Status

**Date:** 2026-10-04
**Plan:** `docs/plans/2026-10-04-media-input-phase5a-uploads.md`
**Branch:** `feat/media-phase5a-uploads` (worktree `zen-media-phase5a`)
**Outcome:** Large Gemini media is uploaded once and reused for 47 hours. Model calls run in worker threads, so the MCP server serves other tools while one waits. Tool output shows what was attached, how it travelled, and when xAI ran its paid search.

## Tasks

| Task | Commit | Notes |
|---|---|---|
| Plan | `f520de7` | |
| 5a.1 Gemini upload cache | `5415a8f` | New `utils/media_upload_cache.py`. `GeminiModelProvider._remote_media` checks, in order: an upload of the same bytes earlier in the same request, then the cache (verified with `files.get`: ACTIVE at the same URI). Otherwise it uploads and records the upload. `tests/conftest.py` gains the autouse fixture `isolated_media_upload_cache`, which points `ZEN_MEDIA_UPLOAD_CACHE` at a per-test file under the session temp dir. |
| 5a.2 Non-blocking model calls | `eb53a64` | All four `generate_content` call sites use `await asyncio.to_thread(...)`; all four were already in async functions. `server.handle_call_tool` holds a per-tool `asyncio.Lock` (created lazily, kept per event loop) from model resolution through `tool.execute`. |
| 5a.3 Media and search metadata in the output | `40844ee` | `utils.media.response_media_metadata` is the single source for all three output shapes. None of them had a notes area, so the notice always goes in the `media_notice` metadata field. The xAI warning is logged in `OpenAICompatibleProvider`'s Responses path, for `ProviderType.XAI` only. |
| 5a.4 Docs and BACKLOG | this commit | `docs/configuration.md` "Media Input" now covers `media_attached`, the xAI warning, the upload cache and the 48-hour privacy note. BACKLOG: four phase 1 follow-ups removed, two phase 3 bullets updated, and phase 5a follow-ups recorded. |

## Behaviour

- **Upload cache file:** `~/.zen/media_uploads.json` by default, or `$ZEN_MEDIA_UPLOAD_CACHE`.
  - Layout: `{"version": 1, "entries": {"<sha256>:<mime>": {...}}}`.
  - Each entry holds `file_name`, `file_uri`, `mime_type`, `size_bytes`, `expires_at` (upload time + 47 h) and `key_fingerprint` (the first 12 hex characters of `sha256(api key)`).
  - The fingerprint is stored inside each entry, so an entry made with another key is ignored and then overwritten by this key's upload.
- **Writing the cache:**
  - Atomic: a temp file in the same directory, then `os.replace`, with mode 0600.
  - Expired entries are dropped whenever the file is read.
  - A corrupt or unreadable file reads as empty and logs a warning. A failed write logs a warning and removes its temp file. Neither fails the model call.
  - A process-wide `threading.Lock` serializes read-modify-write cycles, because uploads can now finish in two worker threads at once.
- **Reusing an upload:**
  - A cached entry is checked with `files.get(name=...)`. A raised error, or any state other than ACTIVE at the same URI, evicts the entry, and the file is uploaded once.
  - A second attachment with the same bytes in one request reuses the first one's upload and is recorded as `transport: "cached"`.
  - zen never calls `files.delete`.
- **Concurrency:**
  - Two different tools, each with a 0.3 s model call, finish together in about 0.31 s.
  - Two calls of the same tool take at least 0.6 s and never overlap. The first call's `model_used` stays its own; without the lock it reported the second call's model, which the test checks.
- **Output metadata:**
  - `media_attached` is copied when the list is non-empty. Gemini always reports a list, and media-free calls add nothing.
  - `server_side_tool_calls` is copied whenever present, 0 included.
  - `media_notice` is one line: uploads (uploaded or cached) for Gemini, and for xAI the search count when it is above 0.
  - The CLI's human output (`print_result_human`, `_present_workflow_step`, consensus) prints each notice after the answer as dimmed plain text, not as Rich markup.

## Verification

- Unit suite: 1507 passed, 6 skipped, 3 failed. The 3 failures are the known `tests/test_alias_target_restrictions.py` Gemini cases. This phase adds 43 tests and changes no existing test, so the base had 1464 passing (computed, not re-run):
  - `tests/test_media_upload_cache.py`: 21;
  - `tests/test_server_concurrency.py`: 6;
  - `tests/test_media_output_metadata.py`: 16.
- Each new behaviour test was run before its change and failed for the expected reason. A few guard tests ("another key's entry ignored", "no media adds no fields", "no xAI calls log nothing") pass either way by design.
- The suite run does not create `~/.zen/media_uploads.json` (checked after the run).
- No live API calls were made; every client is mocked.

## Follow-ups

Recorded in `docs/plans/BACKLOG.md` under "Media input phase 5a follow-ups".
