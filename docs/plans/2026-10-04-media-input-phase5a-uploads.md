# Media input phase 5a (upload cache, non-blocking calls, visible media metadata): implementation plan

**Goal:**
- Large Gemini media is uploaded once and reused.
- The MCP server keeps serving other calls while a model call or a large upload runs.
- Users can see what was attached, how it travelled, and when xAI ran its paid search.

Phase 5b comes later: follow-up re-attach, the stable prefix layout, cache metrics and Claude `cache_control`.

**Process:** the same as `docs/plans/2026-10-03-followups-and-routing.md` (header).
- Worktree: `/Users/wrk/WorkDev/MCP-Dev/zen-media-phase5a`.
- Branch: `feat/media-phase5a-uploads`.
- No live calls by the implementer.

**Design references:** `docs/plans/2026-09-26-media-input-design.md` section 3, and the BACKLOG "Media input phase 1 follow-ups" entries:
- re-upload on a tool-level retry;
- re-uploads per follow-up and per consensus model;
- upload polling blocks the MCP server;
- upload names not shown to users.

---

## 5a.1 Gemini upload cache

**Files:**
- `utils/media_upload_cache.py` (new)
- `providers/gemini.py` (`_build_media_parts`, `_upload_media`)
- tests

**Behaviour:**
- **Location.** A JSON file at `~/.zen/media_uploads.json`, overridable with the `ZEN_MEDIA_UPLOAD_CACHE` env var (tests use a tmp path).
  - Create it with mode 0600.
  - Write atomically: temp file in the same directory, then `os.replace`.
  - Several MCP server processes share it, so tolerate races (last writer wins; the worst case is one extra upload).
  - A corrupt or unreadable file is treated as empty and logged at warning level.
- **Key.** `sha256` of the file contents, streamed in 1 MiB chunks, plus `":"` plus the mime type.
  - Gemini Files API uploads belong to the API key's project, not to a model, so the model is not part of the key.
  - Also store a fingerprint of the API key: the first 12 hex characters of its sha256. Entries from another key are ignored.
- **Value:** `{"file_name": "files/...", "file_uri": "...", "mime_type": "...", "size_bytes": int, "expires_at": <unix seconds>}`. `expires_at` = upload time + 47 h; Google keeps uploads 48 h, so it expires 1 h early.
- **Reuse.**
  - Before uploading an attachment that must be uploaded, look up its key.
  - On a live entry, call `client.files.get(name=file_name)`. If it returns ACTIVE with the same URI, reuse it: no upload, and `transport: "cached"` in `media_attached`.
  - If the lookup raises (404, permission) or the state is not ACTIVE, evict the entry and upload once.
  - Expired entries are evicted on read.
- **Writes.** After every successful upload, write the entry.
- **No deletes.** zen never deletes uploads; Google's 48 h expiry does.
- **Re-uploads disappear.** Follow-ups, consensus models and tool-level retries re-send the same file and now hit the cache. Remove those BACKLOG bullets once the tests prove it.

**Tests:**
- Hit (no `files.upload` call, `transport` cached).
- Miss (upload, entry written).
- Expired entry.
- `files.get` raising (evict, upload once).
- Another API key's entry ignored.
- Corrupt JSON file.
- Atomic write leaves no temp file behind.
- File mode 0600.
- Two attachments of the same content uploaded once.
- A tool-level retry (simple tool empty-response retry) uploads once. Use a mocked client.

## 5a.2 Model calls no longer block the MCP server

**Files:**
- `tools/simple/base.py` (two `generate_content` call sites, around lines 442 and 500)
- `tools/consensus.py` (around line 672)
- `tools/workflow/workflow_mixin.py` (around line 1566)
- `server.py` (`handle_call_tool`)
- tests

**Behaviour:**
- **Run off the event loop.** Every `provider.generate_content(...)` call becomes `await asyncio.to_thread(provider.generate_content, ...)` with the same arguments. The enclosing function must be async; if one is not, make the smallest change that keeps the call chain async, and report it.
- **Serialize each tool.** Tool instances in `server.TOOLS` are shared and keep per-run state (`work_history`, `_model_context`, `_current_arguments`, ...). Two calls of the same tool must not interleave. In `server.handle_call_tool`, hold a per-tool `asyncio.Lock` (a dict keyed by tool name, created lazily) around the tool's execution: from model resolution through `tool.execute`. Different tools run concurrently. Comment why.
- **Gemini upload polling** runs inside `generate_content`, so it is now off the event loop too. No other change is needed there.

**Tests:**
- Two concurrent `handle_call_tool` calls to *different* tools, each with a mocked `generate_content` that sleeps 0.3 s, finish in under 0.5 s together.
- Two concurrent calls to the *same* tool run one after the other: total ≥ 0.6 s, and the second sees no state from the first. Use `asyncio.gather`.
- Existing tests still pass. Some may patch `generate_content` with plain mocks; `to_thread` handles those.

## 5a.3 Media and search metadata reach the user

**Files:**
- `tools/simple/base.py` (response metadata, around lines 610-731)
- `tools/workflow/workflow_mixin.py` (expert analysis result)
- `tools/consensus.py` (per-model response)
- `src/zen_cli/main.py` (non-JSON output, briefly)
- `providers/openai_compatible.py`
- tests

**Behaviour:**
- **Copy into the tool's output metadata** (the `ToolOutput.metadata` that MCP returns and the CLI's `--json` prints), when `ModelResponse.metadata` carries them:
  - `media_attached`: the list of `{name, kind, bytes, transport, file_name?}`;
  - `server_side_tool_calls` (xAI).

  Simple tools: next to `model_used` and `provider_used`. Workflow tools: in the expert analysis block's metadata. Consensus: in each model's response dict.
- **Upload notice.** When any record has `transport` `uploaded` or `cached`, add one human sentence to the output content's existing notes area, or to a `media_notice` metadata field if the tool has no notes area: "Uploaded to the Gemini Files API: files/abc (clip.mp4); Google deletes uploads after 48 h." Keep it to one line per call.
- **xAI search warning.** When `server_side_tool_calls > 0` on an xAI response, log a warning: "xAI ran N server-side search call(s) for <model>; billed separately ($5 per 1,000)". Add the same as a `media_notice` line.
- **CLI.** The non-JSON output prints the notice line after the answer, dimmed.

**Tests:**
- Simple tool: metadata shows `media_attached` with `transport` and `file_name`, and the notice sentence appears for an uploaded file.
- Workflow and consensus: their outputs carry `media_attached`.
- xAI: `server_side_tool_calls=2` produces the warning log and the notice; 0 produces neither.

## 5a.4 Docs and BACKLOG

- `docs/configuration.md` Media Input: the upload cache (location, 47 h reuse, no deletes) and a privacy note: media above Gemini's inline cap is stored on Google's servers for up to 48 hours.
- `docs/plans/BACKLOG.md`: remove the phase 1 follow-ups this fixes (re-upload on retry, re-uploads per follow-up and per consensus model, upload polling blocks the server, upload names not shown). Record anything left.
- `docs/plans/2026-10-04-media-input-phase5a-status.md` (new): task → commit table and verification.
