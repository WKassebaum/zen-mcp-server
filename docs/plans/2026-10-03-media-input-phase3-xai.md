# Media input phase 3 (xAI PDF, explicit models only): implementation plan

**Goal:** Grok models take PDFs through xAI's `/v1/responses` endpoint when the user names a Grok model. Auto mode and capability hints never route PDFs to Grok.

**Decision (user, 2026-10-03):** explicit model only.
- **Why:** past one page, xAI handles attached PDFs with a server-side `attachment_search` tool. That tool costs $5 per 1,000 calls, makes token use cumulative across its internal passes, and may read long documents only partly.
- **Auto mode** keeps sending PDFs to Gemini, Claude and OpenAI, which read every page.

**Facts (live, 2026-10-03, raw openai SDK against `https://api.x.ai/v1`, grok-4.7, `store=false`):**
- **Inline PDFs work on `/v1/responses`** as `{"type": "input_file", "filename": ..., "file_data": ...}`. `file_data` can be a `data:application/pdf;base64,` URL or plain base64. This is the same part shape `OpenAICompatibleProvider._responses_content` already produces for OpenAI.
- **`/v1/chat/completions` refuses file parts:** HTTP 400 "File content is not supported on /v1/chat/completions. Please use /v1/responses instead."
- **Input tokens:**
  - No PDF: 1,249. xAI adds a hidden prompt of about 1,250 tokens to every call.
  - One-page text PDF: 1,775, 0 server-side tools.
  - One scanned letter page: 2,255, 0 tools. Read correctly.
  - Four scanned pages: 9,997, 1 server-side tool call. All four page markers came back in order.
- **`reasoning: {"effort": ...}` on `/v1/responses`:** accepted by grok-4.7. grok-4.20-0309-non-reasoning and grok-build-0.1 return 400 "does not support parameter reasoningEffort".
- **Docs** (https://docs.x.ai/developers/files, read 2026-10-03):
  - Files go through `attachment_search`.
  - `store` defaults to true, with 30-day retention.
  - Per-file limits conflict: 50 MB with HTTP 413 vs 512 MB.
  - Images go as `input_image`, jpg/png, up to 20 MiB.

**Commands, rules and process:** the same as `docs/plans/2026-10-03-followups-and-routing.md` (header).

**Base:** the merged follow-ups + routing work. It provides:
- per-model media rates and `estimate_media_tokens_for`;
- the registry rank helpers;
- `find_media_capable_models` media tie-break.

---

## Batch C

### C1. Explicit-only media providers

**Files:** `providers/base.py`, `providers/registry.py`, `utils/media.py`, tests.

**Behaviour:**
- **New flag.** `ModelProvider.MEDIA_AUTO_ROUTING: ClassVar[bool] = True`. Comment: providers set it False when their media handling is weaker than full reading, so media reaches them only when the user names one of their models.
- **Registry.** `ModelProviderRegistry._filter_models_for_media` returns `[]` for a provider with `MEDIA_AUTO_ROUTING` False whenever `required_media` is non-empty. It is used by both auto routing and `find_media_capable_models`, so both skip such providers.
- **Explicit models still work.** An explicitly named model is validated against its own capability flags (`tools/shared/base_tool.py:_validate_media_support`); confirm that path does not call `_filter_models_for_media` for the named model. If the named model is refused, the hint lists only auto-routable capable models.
- **`utils.media.MEDIA_PROVIDERS` and `providers_hint`.** These answer "which key would let auto mode serve this", so they must not name `XAI_API_KEY`. Leave xAI out of `MEDIA_PROVIDERS`, with a comment saying why.

**Tests:**
- With Gemini, OpenAI and xAI configured (mocked) and every xAI model flagged `supports_pdf`, auto mode for a PDF never returns a Grok model, even though xAI is first in priority.
- `find_media_capable_models({PDF})` lists no Grok model.
- An explicit `grok-4.7` with a PDF passes `_validate_media_support`.

### C2. xAI provider sends PDFs through `/v1/responses`

**Files:** `providers/xai.py`, `providers/openai_compatible.py`, tests.

**Behaviour:**
- **Class attributes** on `XAIModelProvider`:
  - `MEDIA_KINDS = frozenset({MediaKind.PDF})`.
  - `MEDIA_AUTO_ROUTING = False`.
  - `MEDIA_REQUEST_MAX_BYTES = 50_000_000`, base64-encoded. Comment: the design's figure; xAI docs give 50 MB (upload reference, HTTP 413) and 512 MB (files guide).
  - `PDF_TOKENS_PER_PAGE = 2_500`. Comment: measured 1,006 for one scanned page, and about 2,190 per page over four pages, counting the search pass's second inference.
- **Media switches the endpoint.** When `media` is non-empty, the request goes to `_generate_with_responses_endpoint` even though xAI models are not `use_openai_response_api`. Without media, xAI stays on Chat Completions, as today.
  - **Where:** find the cleanest hook in `OpenAICompatibleProvider.generate_content`. One way is a provider method such as `_use_responses_endpoint(capabilities, media)`, which xAI overrides; the base returns the capability flag. Keep OpenAI's behaviour unchanged.
  - **Order:** `ensure_media_encodable` and the size check already run first; keep them first.
- **`reasoning` only where the model takes it.** `_generate_with_responses_endpoint` sends `reasoning` only when the model supports it.
  - **Default (base):** today's behaviour: send it for every model that uses the Responses endpoint. Verify each OpenAI and OpenRouter Responses model still gets it, so nothing changes for them.
  - **xAI:** send it only when `capabilities.supports_extended_thinking` is true. grok-4.20-0309-non-reasoning and grok-build-0.1 are false in `conf/xai_models.json`, and the API rejects the parameter for them.
  - **Implementation:** a small overridable method, `_responses_reasoning(capabilities)`, returning the dict or `None`.
- **Usage metadata.** Responses usage from xAI carries `num_server_side_tools_used` and `cost_in_usd_ticks`. When present, copy `num_server_side_tools_used` into `ModelResponse.metadata["server_side_tool_calls"]` so search calls are visible. Leave `_extract_usage` token fields as they are.
- **Images** already map to `input_image` (phase 2). With media present, images ride the same Responses request.

**Tests** (mocked client; assert on the exact `responses.create` kwargs):
- grok-4.7 + PDF → `responses.create` is called with an `input_file` part whose `file_data` starts with `data:application/pdf;base64,`, with `store: False` and with `reasoning`.
- grok-build-0.1 + PDF → no `reasoning` key.
- grok-4.7 without media → `chat.completions.create`, as today.
- An OpenAI gpt-6-luna request is unchanged: `reasoning` is present and so is the endpoint.
- PDFs over 50 MB encoded raise `MediaNotSupportedError` before any client call.
- `server_side_tool_calls` reaches the metadata when the usage has it.

### C3. Probe script, catalog flags, probe matrix, docs

**Files:**
- `scripts/probe_media_support.py`
- `tests/test_probe_media_support.py`
- `conf/xai_models.json`
- `tests/media_probe_matrix.py`
- `tests/test_media_catalog_guard.py` (if needed)
- `docs/configuration.md`
- `.claude/skills/zen-skill/` (media section, if one exists)
- `docs/plans/BACKLOG.md`
- design doc status line
- `docs/plans/2026-10-03-media-input-phase3-status.md` (new)

**Behaviour:**
- **Probe script.** `--provider xai` probes through `XAIModelProvider`, like the openai and anthropic paths, reading `XAI_API_KEY` via `tests.live_keys`. PDF is the only kind. Add a unit test in the style of the existing provider-factory tests.
- **Catalog.** Add the `supports_pdf` field description line to `conf/xai_models.json` `_README`, if it is missing. Flags are set by the controller after the live probe, not by the implementer.
- **Docs.** Grok reads PDFs only when named (`--model grok-4.7`). Say:
  - xAI searches documents longer than about a page with a server-side tool, billed at $5 per 1,000 calls plus the tokens of each pass;
  - zen sends `store=false`;
  - auto mode never routes PDFs to Grok.

---

## Controller steps

1. Live probe: `scripts/probe_media_support.py --provider xai --repeat 2`, all 7 models. Also probe the 4-page scanned PDF in the scratchpad through `XAIModelProvider`.
2. Flag the models that pass every try; record them in `PROBED` with the date and token figures.
3. CLI smoke test: `zen chat "..." --model grok-4.7 -f tests/fixtures/media/zebra.pdf` from the worktree (the CLI loads its own config). Also auto mode with the same PDF: the answer must come from a non-Grok model.
4. Final whole-branch review, merge, push, BACKLOG update.
