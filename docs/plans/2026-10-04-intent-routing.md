# Intent words, consensus panel and OpenRouter preference lists: implementation plan

**Goal:**
- A named model is always used, exactly as named. This is already true; keep it.
- When no specific model is named, the user can state an intent: `frontier`, `balanced` or `fast`.
- Consensus with no models, or with `frontier`, consults the top model of each provider.
- OpenRouter-only auto mode picks by purpose (the native providers' preference lists), not by rank.

**User decisions (2026-10-04):**
- Intent words are model names: no new parameter.
- The consensus panel is the top model per provider, up to 4.
- OpenRouter mirrors the native preference lists.

**Process:** the same as `docs/plans/2026-10-03-followups-and-routing.md` (header: commands, rules, one commit per task).
- Worktree: `/Users/wrk/WorkDev/MCP-Dev/zen-intent`.
- Branch: `feat/intent-routing`.

---

## I1. Intent words resolve to a model

**Files:**
- `providers/registry.py`
- `server.py` (the `model_name.lower() == "auto"` block in `handle_call_tool`, around line 866)
- `tools/shared/base_tool.py` (`_resolve_model_context` CLI path, around line 1433, and `get_model_field_schema` descriptions)
- `tools/listmodels.py`
- `docs/configuration.md`
- tests

**Behaviour:**
- **The words.** `INTENT_MODELS = ("frontier", "balanced", "fast")`, case-insensitive. No catalog name or alias uses them; add a test that keeps it that way.
- **One shared resolver.** Add `ModelProviderRegistry.resolve_model_intent(name, tool_category, required_media=frozenset()) -> Optional[str]`. It returns None when `name` is not an intent word or `auto`, and otherwise:
  - **`auto`:** today's behaviour, `get_preferred_fallback_model(tool_category, required_media)`.
  - **`fast`:** `get_preferred_fallback_model(ToolModelCategory.FAST_RESPONSE, required_media)`, whatever the tool's category.
  - **`balanced`:** `get_preferred_fallback_model(ToolModelCategory.BALANCED, required_media)`.
  - **`frontier`:** the single highest-ranked model available across *all* configured providers. Respect restrictions and `required_media`, including explicit-only providers: Grok never gets media through an intent word. Premium models are allowed. Ties break by `PROVIDER_PRIORITY_ORDER`, then canonical name. Return the canonical name.
  - **No model can take the media:** raise `MediaNotSupportedError`, as auto does today.
- **MCP boundary and CLI path.** Both call the resolver instead of their inline auto handling, so the `auto` block now also handles the intent words. Keep the existing workflow earlier-step media logic (`server._call_media_kinds`) feeding `required_media`. Log `"<word> resolved to <model>"`.
- **Follow-up reuse.** `reconstruct_thread_context` reuses the previous turn's model only when `model` is omitted. An intent word counts as given: it resolves fresh, so do not reuse.
- **Schema description.** In `get_model_field_schema`, mention the words in one short sentence for both auto and non-auto mode: "Or an intent: 'frontier' (best available), 'balanced', 'fast'; 'auto' picks per tool."
- **listmodels.** Add a line under the header listing the intent words.
- **Consensus.** Its own per-model handling is covered in I2.

**Tests:**
- **Resolver, with Gemini+OpenAI+xAI configured:**
  - `frontier` returns a 20-score flagship (rank 111).
  - `fast` returns the FAST_RESPONSE pick and `balanced` the BALANCED pick.
  - `frontier` with a PDF never returns a Grok model.
  - An allow-list limits `frontier`.
- **End to end:** the MCP boundary with `model="frontier"` runs on the resolved model, and so does the CLI-path `_resolve_model_context`.
- **Named models untouched:** a named model is never passed to the resolver, e.g. `model="gemini-2.5-flash"` stays `gemini-2.5-flash`.
- **Follow-up:** a continuation with `model="fast"` does not reuse the previous turn's model.

## I2. Consensus: the frontier panel, and the CLI consults every model

**Files:**
- `tools/consensus.py`
- `providers/registry.py` (the panel helper)
- `src/zen_cli/main.py` (`consensus` command, around line 440)
- tests

**Behaviour:**
- **Panel helper.** `ModelProviderRegistry.frontier_panel(limit=4, required_media=frozenset()) -> list[str]`:
  - For each provider in `PROVIDER_PRIORITY_ORDER` that has allowed (and media-capable) models, take its highest-ranked allowed canonical model.
  - Skip a pick whose *vendor* is already on the panel. Vendor: the provider type for native providers. For OpenRouter, the id prefix before `/`, mapped `x-ai`→`xai`, `google`→`google`, `anthropic`→`anthropic`, `openai`→`openai`; other prefixes are their own vendor. Custom/Azure/DIAL count as their provider type.
  - Stop at `limit`. Order: as picked.
- **Consensus request handling, step 1:**
  - When `models` is empty or missing, it becomes the panel, with `stance: "neutral"`.
  - Any entry whose `model` is `frontier` expands in place into the panel, each member copying that entry's `stance` and `stance_prompt`.
  - Entries `fast`, `balanced` and `auto` resolve through `resolve_model_intent` with the tool's category.
  - After expansion, fewer than 2 models is an error naming the configured keys.
  - The expanded list is what `models_to_consult` stores, so later steps consult concrete names.
  - Lower the `models` schema `minItems` from 2 to 1, so `[{"model": "frontier"}]` is valid.
  - Update the field description: "Name models explicitly, or use 'frontier' for the top model of each configured provider".
- **CLI `zen consensus`:**
  - Default (no `--models`) is `frontier`; `--models frontier` works too.
  - Bug fix: it runs only step 1 today, so it consults only the first model (confirmed with a mocked run on 2026-10-04). Loop: call `ConsensusTool().execute` for step 1, then for steps 2..N with the returned `continuation_id`, `step_number`, `current_model_index`, a short `findings`, and `next_step_required` false on the last step, until `consensus_complete`.
  - Print every model's verdict; `--json` returns a list of all step results.
  - Remove the old default `["gemini-2.5-flash", "gpt-4o-mini"]`.

**Tests:**
- **Panel:**
  - Gemini+OpenAI+xAI+Anthropic (mocked keys) gives 4 distinct vendors, each the provider's top model.
  - Native Anthropic + OpenRouter gives no second Anthropic model.
  - A PDF panel excludes Grok.
- **Consensus step 1:**
  - `[{"model": "frontier", "stance": "for"}]` expands, and each member gets `for`.
  - An empty `models` list becomes the panel.
  - A single concrete model is an error.
- **CLI:** a mocked `_consult_model` sees every model of `--models a,b,c` (exactly 3 calls), and the default panel with no `--models`.

## I3. OpenRouter preference lists

**Files:** `providers/openrouter.py`, `docs/plans/BACKLOG.md`, tests.

**Behaviour:**
- **Lists.** Add `OpenRouterProvider.get_preferred_model(category, allowed_models)` with per-category lists of OpenRouter ids, mirroring the native providers' first choices and interleaving vendors:
  - **EXTENDED_REASONING:** `openai/gpt-6-astra`, `anthropic/claude-fable-5.1`, `google/gemini-3.1-pro-preview`, `x-ai/grok-4.7`, `anthropic/claude-opus-5.5`, `openai/gpt-6-sol`.
  - **BALANCED:** `openai/gpt-6-sol`, `anthropic/claude-sonnet-5.5`, `google/gemini-3.1-pro-preview`, `x-ai/grok-4.7`, `openai/gpt-5.6-sol`.
  - **FAST_RESPONSE:** `openai/gpt-6-luna`, `google/gemini-3.5-flash`, `anthropic/claude-sonnet-5.5`, `x-ai/grok-4.6`, `google/gemini-3.6-flash`.

  Check each id exists in `conf/openrouter_models.json`, and use the ids exactly as written there.
- **Matching.** `allowed_models` mixes aliases and canonical names: match on resolved canonical names.
- **Fallback.** Return None when nothing on the list is allowed. The registry's existing `_pick_by_rank` (premium-aware) then applies.
- **Custom priority.** The registry stops at the first provider with allowed models, so this cannot beat Custom/Azure/DIAL. Keep `test_custom_endpoint_keeps_every_category_ahead_of_openrouter` passing.
- **BACKLOG.** Update "Rank-based auto-mode picks ignore price and speed": OpenRouter now has lists; rank picks remain for Custom/Azure/DIAL and for allow-lists outside the lists.

**Tests:**
- OpenRouter-only, no restriction: chat → `openai/gpt-6-luna`, BALANCED → `openai/gpt-6-sol`, EXTENDED → `openai/gpt-6-astra`.
- `OPENROUTER_ALLOWED_MODELS=opus,sonnet,mistral`: chat → `anthropic/claude-sonnet-5.5` (on the FAST list), EXTENDED → `anthropic/claude-opus-5.5`.
- Custom+OpenRouter: Custom still wins every category.
- Update the existing tests in `tests/test_auto_mode_restricted_routing.py` and `tests/test_auto_mode_comprehensive.py` that encode the old rank picks, and name them in the commit.

## I4. Docs

- `docs/configuration.md`: a short "Choosing a model" section covering named models (always used as named, never swapped), `auto`, the intent words, and the consensus panel.
- `.claude/skills/zen-skill/SKILL.md`: one paragraph on `--model frontier|balanced|fast` and `zen consensus` defaults. Check that file's structure first, and keep the edit small.
