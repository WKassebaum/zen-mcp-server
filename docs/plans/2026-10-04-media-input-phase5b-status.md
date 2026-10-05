# Media Input Phase 5b — Status

**Date:** 2026-10-04
**Plan:** `docs/plans/2026-10-04-media-input-phase5b-continuation.md`
**Branch:** `feat/media-phase5b-continuation` (worktree `zen-media-phase5b`)
**Outcome:** Follow-ups re-attach the media any earlier turn attached, not only first-turn media. Media requests keep a byte-stable prefix, Claude gets a cache breakpoint after the media, and every provider reports `cached_input_tokens`. The Grok CLI preset runs with `--no-auto-update`, and the docs cover media and Grok Build via clink. Live checks: see "Live results".

## Tasks

| Task | Commit | Notes |
|---|---|---|
| Plan | `5dbf816` | |
| 5b.3 Cached-token metrics | `397b2ea` | Done first (self-contained). `providers.shared.usage_count` accepts only real ints, so Mock-built usage never yields a count. |
| 5b.4 Claude `cache_control` | `cd14a8d` | Native: on the last document block. OpenRouter `anthropic/*` (Chat Completions): a fixed text part, `CLAUDE_CACHE_BREAKPOINT_TEXT`, after the last file part, through the new hook `OpenAICompatibleProvider._media_prefix_parts`. |
| 5b.1 Per-turn media and re-attach | `3098eb2` | Also carries 5b.2's ordering: the planner emits first-seen order. |
| 5b.2 Stable prefix | `a2171ac` | Tests only: every encoder already had the layout. |
| 5b.5 Docs and the Grok CLI | this commit | `conf/cli_clients/grok.json`, `docs/configuration.md`, `docs/tools/clink.md`, zen-skill Media section, BACKLOG, design status line. |

## Behaviour

- **Recording:** `ConversationTurn.media` lists the media a turn's model call attached itself; `add_turn(..., media=)` stores it, and turns stored without it load as `None`.
  - Simple tools: the request's media, on the assistant turn. User turns record none.
  - Workflow tools: the expert call's own media (consolidated `relevant_files`), on the final step's turn.
  - Consensus: each step's own media, the proposal's on step 1, recorded once it passes that model's validation.
  - Re-attached media is not recorded again, so a file keeps the age of the turn that attached it.
- **Lookup** (`utils/conversation_memory.py`): `get_conversation_media_list` (newest first, deduped by resolved file, the newest spelling kept), `get_conversation_media_first_seen` (oldest first) and `get_conversation_media_kinds` (existing files only, for routing). They read `context.turns`; tools never create parent-linked threads.
- **Re-attach:** `BaseTool._plan_call_media` calls `utils.media.plan_media`, which returns a `MediaPlan` (`attachments`, `own`, `omitted`).
  - **Own media** is validated first (`_validate_media_support`, refused as before) and never dropped.
  - **Earlier media** is skipped when it is the same file as an own attachment (resolved path). It is left out with a note when the file is gone, is no longer readable media, is over 2 GB, or its kind is outside the model's flags and its provider's `MEDIA_KINDS`.
  - **Budget:** while the estimate of own plus earlier media (`estimate_media_tokens_for`) exceeds the tool's file budget, the oldest earlier file is dropped. Simple tools and consensus use `BaseTool._file_token_budget`, the number `_prepare_file_content_for_prompt` already used (now one helper). Workflow expert calls use the expert file allocation (`workflow_mixin._expert_file_budget`). Then, for providers with an inline cap (`MEDIA_REQUEST_MAX_BYTES`), older files are dropped until the base64 size fits.
  - **Order:** attachments go out in first-seen order across the thread, media new to the thread last, in the call's own order.
  - **Manifest:** `media_prompt_section(attachments, omitted)` numbers the attachments in that order and lists the omissions under `--- EARLIER MEDIA NOT ATTACHED ---`. The plan is set on the tool instance only while the call's prompt is built and cleared in a `finally`. The simple-tool file section, `_force_embed_files_for_expert_analysis`, debug's expert context and consensus's CONTEXT FILES all read it, and each caller appends the section when the prompt lacks it.
- **`initial_context`** now carries first-turn text files only: `server._without_media` drops current media and the thread's recorded media (so a deleted PDF is not read as text). Removed: `_initial_context_keys`, `BaseTool._paths_from_initial_context`, the `carried_over` explanation in `_validate_media_support`, and `_unattached_thread_media_note`.
- **Routing:** `server._call_media_kinds` adds the thread's recorded media for every tool (`_handle_call_tool` now reads the thread for any continuation), so intent routing picks a model for it and `_carries_media_to_explicit_only_provider` refuses to reuse Grok when only re-attached media is present. In-process auto resolution (`BaseTool._resolve_model_context`, the CLI path) counts it too.
- **Prefix layout:** checked in all seven encoders: Gemini, native Anthropic, OpenAI Chat, OpenAI and xAI Responses, OpenRouter Chat and Responses. No fixes needed.
- **Metrics:** `usage["cached_input_tokens"]` comes from `prompt_tokens_details.cached_tokens` (Chat), `input_tokens_details.cached_tokens` (Responses), `cached_content_token_count` (Gemini) and `cache_read_input_tokens` (Claude, plus `cache_write_input_tokens`). A field that is not reported is absent; a reported 0 stays 0. With prompt caching, Claude's `input_tokens` counts only uncached input, so its `total_tokens` looks smaller; the cached and written tokens are the two fields above. `response_media_metadata` copies it into the tool metadata (simple tools, the expert analysis block, consensus responses).

## Deviations from the plan

- **5b.2's ordering landed in 5b.1:** the planner had to emit an order either way, and emitting newest first first would only have been rewritten in 5b.2.
- **Inline request cap:** re-attach also drops older media to fit a provider's inline cap. Otherwise re-attached media could fail `ensure_media_encodable` and refuse a call the plan says proceeds.
- **Recorded on assistant turns only:** the server stores the user turn before the model call, so only the assistant turn knows what was attached.
- **The "media not attached" note is gone:** omissions now appear in the manifest. Media a refused call named was never attached, so it is neither re-attached nor mentioned (BACKLOG).
- **Native Claude marker with PDF plus image:** on the last document block, not the image. Images follow the prompt text, so a marker there would cache the changing text and never hit.
- **Prefix comparison with a new file:** native Claude's marker moves to the newest last block. Anthropic does not treat a moved marker as an invalidation (the breakpoint's lookback finds the previous entry), so the turn-2 to turn-3 comparison strips `cache_control`. Turns 1 and 2 are compared raw.

## Verification

- Unit suite: 1705 passed, 6 skipped, 3 failed (the known `tests/test_alias_target_restrictions.py` Gemini cases). The base had 1629 passed; this phase adds 76 tests:
  - `tests/test_cache_metrics.py`: 27;
  - `tests/test_claude_cache_control.py`: 10;
  - `tests/test_media_reattach.py`: 20;
  - `tests/test_media_stable_prefix.py`: 18;
  - `tests/test_clink_grok_agent.py`: 1.
- Updated tests are named in each commit message: 2 in 5b.3, 3 in 5b.4, 7 replaced or renamed in 5b.1.
- Each behaviour test failed for the expected reason before its change. The 5b.2 prefix tests passed at once, because the ordering came with 5b.1; emitting media newest first fails 8 of them.
- **Media-free payloads byte for byte:** a script ran the same media-free calls on the base commit (`git archive 5dbf816`) and on this branch, with every SDK client mocked and thread IDs pinned. It covered a chat turn with a text file, its follow-up, an analyze expert call and a consensus consultation, on 8 provider/endpoint cases (Gemini, native Claude, OpenAI Chat, OpenAI Responses, xAI, OpenRouter Chat for Gemini and Claude, OpenRouter Responses). All 32 SDK payloads were identical.
- No live API calls were made.

## Controller steps (pending)

1. A live second-turn probe per provider with a PDF over the caching minimums (≥ 4,096 tokens): `cached_input_tokens > 0` on turn 2, for Gemini, native Claude, OpenAI, xAI (named Grok) and OpenRouter (one model).
2. A live follow-up re-attach check through the CLI or MCP.
3. Final review, merge and push.

## Follow-ups

Recorded in `docs/plans/BACKLOG.md` under "Media input phase 5b follow-ups".


## Live results (2026-10-04, controller)

**Cache probe.** Two calls per provider with the same 8-page image-only PDF and different questions, through zen's providers. Turn 2 figures:

| Provider and model | Turn 2 cache |
|---|---|
| Gemini gemini-3.5-flash | 1,898 cached |
| Claude claude-sonnet-5-5 (cache_control) | turn 1 wrote 12,470, turn 2 read 12,470 |
| OpenAI gpt-5.5 (Chat) | 5,888 cached |
| xAI grok-4.7 | 5,888 cached |
| OpenRouter anthropic/claude-sonnet-5.5 (cache_control text part) | 12,478 cached |
| OpenAI gpt-6-luna (Responses) | 0 cached |
| OpenRouter google/gemini-3.5-flash | 0 cached |

**The two misses:**
- **gpt-6-luna.** Over 11 tries, the response's `cache_write_tokens` was nonzero every time and only one try hit, with or without `prompt_cache_key` and `reasoning`, and at gaps of up to 45 s. zen reads the field correctly (checked offline against the SDK type), and now also reports `cache_write_input_tokens`.
- **Gemini through OpenRouter.** OpenRouter alternates between two Google endpoints (Google and Google AI Studio), each with its own cache. A raw call hit 3,881 tokens right after zen's calls, then missed again. zen does not pin the endpoint, to keep availability.

**Re-attach, end to end.** On Gemini, through `server.handle_call_tool`, turn 1 attached the PDF and was asked about page 1 (OSPREY-11). Turn 2 named no files and asked about page 5. The PDF was re-attached (`media_attached` lists it) and the answer was correct (HERON-5).

## Final review fixes (2026-10-05)

The final review found nothing Critical. Fixes, one commit each, test-first:
- **`a3e8d1f`** (Important): a call's own text files come before re-attached media. Earlier media gets the file budget minus the own text files' estimate (floor 0), against the same budget each tool embeds with.
- **`a4675f1`** (Important): earlier media a follow-up left out is reported in the output as `media_omitted`, plus a `media_notice` line.
- **`e6140d4`:** first-turn media that no turn recorded (threads stored before 5b, clink-started threads) re-attaches as the oldest earlier media.
- **`637c5ea`:** follow-up history is sized for a model that takes the thread's media.
- **`3ed56f6`:** consensus intent words pick for the thread's media too. A thread with a PDF gets no Grok member through `frontier`.
- **`3e5f719`:** re-attach plans under the inline request cap with headroom for the prompt.
- **`a7e9d00`:** docs: Claude's `total_tokens` excludes cached input.
