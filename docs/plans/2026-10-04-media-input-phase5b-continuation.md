# Media input phase 5b (follow-up re-attach, stable prefix, cache metrics, docs): implementation plan

**Goal:**
- Media attached on any earlier turn of a conversation travels with every follow-up, not only first-turn media.
- Requests keep a byte-stable prefix so providers' prompt caches hit.
- zen reports cached input tokens.
- Claude gets a `cache_control` marker.
- The docs cover media and the Grok CLI.

**Process:** the same as `docs/plans/2026-10-03-followups-and-routing.md` (header).
- **Already on the base branch:**
  - Phase 4 (the OpenRouter encoder, `providers/openrouter.py`).
  - Phase 5a: the upload cache; `asyncio.to_thread` model calls; the per-tool lock; `media_attached`, `media_notice` and `server_side_tool_calls` in the tool output metadata.
  - Intent routing (consensus now needs at least 2 models).
- **Tests:** media paths must be absolute. zen classifies a relative path as a text file, so a relative fixture path silently attaches nothing.
- Worktree: `zen-media-phase5b`, branched from `zen-cli-v2` after the intent, phase 4 and phase 5a merges.
- No live calls by the implementer.

**Design:** `docs/plans/2026-09-26-media-input-design.md` sections 3–4.

**Today's behaviour:**
- First-turn media returns only through `initial_context`, and only when a follow-up names no files itself (`server.reconstruct_thread_context` merge; `BaseTool._paths_from_initial_context`, used by simple, workflow and consensus).
- Media attached on a later turn is never re-sent.

---

## 5b.1 Per-turn media and re-attach

**Files:**
- `utils/conversation_memory.py`
- `tools/simple/base.py`
- `tools/workflow/workflow_mixin.py`
- `tools/consensus.py`
- `tools/shared/base_tool.py`
- `utils/media.py`
- `server.py` (if routing must count re-attached media)
- tests

**Behaviour:**
- **Recording.** `ConversationTurn.media: Optional[list[str]]`: the media paths attached on that turn. `add_turn(..., media=None)` stores it, and storage round-trips it; old stored turns without the field load fine. Each tool records the media it actually sent when it stores its turns:
  - simple tools: the request's media;
  - workflow tools: the expert call's media;
  - consensus: the proposal's media.
- **Lookup.** `get_conversation_media_list(context) -> list[str]` returns paths newest first, deduped by resolved path.
- **Re-attach.** On a continuation, the media sent is:
  1. this call's own media, first;
  2. then earlier turns' media, newest first, deduped against (1).

  This replaces the `initial_context` route for *media*. `initial_context` still carries first-turn *text* files as today. A media path must never be attached twice.
- **Missing files.** An earlier media file that no longer exists on disk is skipped. The manifest (`media_prompt_section`) says `[omitted: earlier report.pdf — file no longer exists]`.
- **Model limits.** If the model's flags or encoder can't take an earlier turn's media kind, that file is omitted with `[omitted: earlier clip.mp4 — <model> does not take video]`, and the call proceeds.
  - Media named in *this* call is still refused, exactly as today.
  - This is a deliberate change: today a carried-over first-turn file the model can't take refuses the call (`_validate_media_support(..., carried_over)`). Update those tests and name them in the commit message.
  - Explicit-only providers (Grok) take earlier PDFs only when this call names the Grok model. Follow-up reuse of a Grok model is already blocked when media is present (`server._carries_media_to_explicit_only_provider`). That helper and `server._call_media_kinds` must count re-attached media too.
- **Budget.** If `estimate_media_tokens_for` of the combined set exceeds what the model's budget leaves, drop the *oldest* earlier media first. The manifest says `[omitted: older recording.mp4 — over budget]`. "What the budget leaves" is the reserve the tool already computes; reuse that number. This call's own media is never dropped.
- **Uploads.** Upload-heavy media goes through phase 5a's upload cache, so re-attaching a large Gemini file costs no new upload.

**Tests:**
- Turn 1 attaches a.pdf; turn 2 attaches b.pdf. Turn 3 (no files) sends both, newest first in the list.
- A text file on turn 1 still comes back through `initial_context` exactly once.
- No duplicate when turn 2 names a.pdf again.
- Deleted file → omitted note.
- A follow-up to a model without video, where turn 1 had a video → note, call proceeds.
- An over-budget oldest file is dropped with a note.
- A workflow final step and consensus also re-attach.
- Grok reuse is blocked when only re-attached media is present.

## 5b.2 A stable prefix for media requests

**Files:**
- `providers/gemini.py`
- `providers/anthropic.py`
- `providers/openai_compatible.py`
- `providers/openrouter.py`
- tests

**Behaviour:**
- **Layout, media requests only:**
  1. the system prompt as its own element;
  2. media parts in *first-seen order across the thread* (oldest first);
  3. the changing text (history plus the new request).

  Media-free requests keep today's layout byte for byte.
- **Ordering.** The tools pass media to the providers in first-seen order. Re-attach (5b.1) computes the list newest first for budget trimming, then emits it oldest first. The manifest numbering ("attachment N of M") follows the emitted order.
- **Check every encoder.** Confirm that media parts come before the text part, and the system prompt is separate, in all of: Gemini, Anthropic, OpenAI Chat, OpenAI and xAI Responses, and OpenRouter Chat and Responses. Fix any that don't.

**Tests:** for each provider, two consecutive turns of one conversation (mocked client) produce request payloads whose bytes are identical up to the end of the last media part. Serialize with `json.dumps(sort_keys=False)` of the messages/contents.

## 5b.3 Cached-token metrics

**Files:** each provider's usage extraction, plus the tool metadata surfacing added in 5a.

**Behaviour:** `ModelResponse.usage["cached_input_tokens"]`, read from:
- **Chat Completions** (OpenAI, xAI, OpenRouter): `usage.prompt_tokens_details.cached_tokens`.
- **Responses API** (OpenAI, xAI, OpenRouter): `usage.input_tokens_details.cached_tokens`.
- **Gemini:** `usage_metadata.cached_content_token_count`.
- **Claude:** `usage.cache_read_input_tokens`. Also record `cache_creation_input_tokens` as `cache_write_input_tokens`.

Missing fields mean the key is absent, not 0. Show `cached_input_tokens` in the tool metadata next to `media_attached`.

**Tests:** usage parsing per endpoint with real SDK usage objects where available (`openai.types`, `anthropic.types`, `google.genai.types`), and an absent field.

## 5b.4 Claude `cache_control`

**Files:** `providers/anthropic.py`, `providers/openrouter.py`, tests.

**Behaviour:**
- **Native Anthropic:** `cache_control: {"type": "ephemeral"}` on the *last media block* (document or image), on media requests only.
- **OpenRouter `anthropic/*` models:** the chat schema allows `cache_control` on text parts only. Put it on a text part placed right after the last file part. If that needs a split text part, the first text part is a short fixed string; keep it stable. Media requests only.
- **Nothing else changes.** No marker on media-free requests or other models.

**Tests:** marker placement for native Anthropic (PDF only; PDF plus image); OpenRouter anthropic; none for openai/* or media-free requests.

## 5b.5 Docs and the Grok CLI

- **`conf/cli_clients/grok.json`:** add `--no-auto-update` to the headless args (xAI recommends it for scripts). Check the file's structure and that the clink parser test still passes.
- **`docs/configuration.md` / the clink docs, Grok Build via clink:**
  - It needs `grok login` with SuperGrok or X Premium+ (or `XAI_API_KEY`).
  - Each call carries about 45k tokens of agent overhead from the subscription's weekly allowance.
  - A per-model `api_key` in `~/.grok/config.toml` overrides the login.
  - The xAI API itself takes API keys only; no OAuth.
- **`.claude/skills/zen-skill/SKILL.md`:** a short Media section covering:
  - attaching files (`-f` / `absolute_file_paths`);
  - which providers take what;
  - Grok named-only;
  - follow-ups re-attach;
  - the upload cache and 48 h retention;
  - `cached_input_tokens`.
- **BACKLOG:** remove what this phase fixes, including the phase 2 follow-up "Claude cache_control deferred to phase 5". Record the rest.
- **Design doc status line:** "Phases 1–5 done".
- **New status doc:** `docs/plans/2026-10-04-media-input-phase5b-status.md`.

## Controller steps

1. A live second-turn probe per provider with a PDF large enough to clear caching minimums (≥ 4,096 tokens, e.g. a generated multi-page text PDF): `cached_input_tokens > 0` on turn 2. Cover Gemini, Claude (native), OpenAI, xAI (named Grok) and OpenRouter (one model).
2. A live follow-up re-attach check through the CLI or MCP.
3. Final review, merge and push.
