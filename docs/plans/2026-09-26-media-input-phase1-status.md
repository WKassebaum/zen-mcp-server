# Media Input Phase 1: Status and Handoff

**Updated:** 2026-10-01
**Plan:** `docs/plans/2026-09-26-media-input-phase1.md` (authoritative; each completed task has an "Amended" note recording review changes, and the committed code wins over the plan's code blocks for completed tasks)
**Design:** `docs/plans/2026-09-26-media-input-design.md`
**Follow-ups found in review:** `docs/plans/BACKLOG.md`, "Media input phase 1 follow-ups"

## Where the work lives

| Item | Value |
|---|---|
| Worktree | `/Users/wrk/WorkDev/MCP-Dev/zen-media-input` |
| Branch | `feat/media-input`, based on `zen-cli-v2` at `6ba5a9b`; backed up to `origin/feat/media-input` |
| Python | `.zen_venv/bin/python` in the worktree, pinned to the live venv's versions (do not reinstall) |
| Lint | `ruff`, `black`, `isort` from PATH (`~/.local/bin`); not in the venv |
| Tests | `.zen_venv/bin/python -m pytest tests/ -q -m "not integration" -p no:cacheprovider` |
| Baseline | 1205 passed, 6 skipped, 3 failed (phase 1 complete) (the known `tests/test_alias_target_restrictions.py` Gemini failures) |
| Gemini key | exported in the user's shell (`GEMINI_API_KEY`); not in any repo `.env` |

Never edit `/Users/wrk/WorkDev/MCP-Dev/zen-cli`: it backs the user's live zen MCP server.

## Progress: phase 1 complete (tasks 1–17), merged into `zen-cli-v2` on 2026-10-01

Tasks 1–6 each passed an implementer pass, a spec-compliance review and a code-quality review. From B1 on, each batch gets one implementer and one proportionate review (see below).

| Task | What | Commits |
|---|---|---|
| 1 | Probe fixtures (`zebra.pdf`, `pelican.wav`, `otter.mp4`) and generator | `18a71b5` |
| 2 | `utils/media.py` classification, path validation, `source_path` | `cd19872`, `d3aa42b` |
| 3 | 2 GB limit, token estimate (bounded parsers, PDF page count at 560/page), prompt section, `format_size` | `94b2c5c`, `85d0b9f`, `df0bae5`, `d4dfe85`, `34b44bb`, `732b70c` |
| 4 | Media and binaries never read as text; BOM decoding; `--- MEDIA FILE (NOT ATTACHED)` placeholder | `ded20f2`, `f3dc0d8`, `1bfe592` |
| 5 | `supports_pdf/audio/video` flags, rank bonus | `6fd405d`, `d595c41` |
| 6 | Live Gemini probe; flags set from results (8 models all three kinds; 2.5 Flash and Flash-Lite pdf+video, audio flaky) | `97d5f21` |
| 7 | `MEDIA_KINDS` and `ensure_media_encodable` on every provider | `1d3c74f` |
| 8 | listmodels tests no longer leak the Gemini key removal or the CUSTOM provider | `0f5a469` |
| 9 | Auto mode filters by required media; `find_media_capable_models`; hints and error text | `e20ab57`, `a6bebf1` |
| 10 | `BaseTool` media helpers: validation (with first-turn carry-over message), prompt section, token reserve, MEDIA NOT ATTACHED note | `1d7a919` |
| 11 | Simple tools validate and send media; `server.py` records `_initial_context_keys` | `dd73cf0` |
| 12 | Auto mode (server, CLI, reconstruct fallbacks) routes on media incl. a workflow's earlier steps; MCP size check counts text only | `4bb6b09` |
| 13 | Workflow tools validate media every step and before the expert call, then send it; bare-string file lists are wrapped, not dropped | `836aa71` |
| 14 | Consensus refuses media any listed model cannot read before consulting anyone, and sends it per model | `d36f86b` |
| 15 | Gemini encoder: `MEDIA_KINDS`, inline under the cap, Files API upload above it, `system_instruction` for media requests | `d6f8bcc` |
| 16 | File-list descriptions mention native media | `819882b` |
| 17 | Live probes through zen (29/29), CLI smoke test; video estimate raised to 400 tokens/s | `2f551fb` |
| B4 carry-over | Probe script `--repeat`/`--kinds`, errors apart from misses; audio re-probe 3/3 on all eight flagged models | `ba65534` |
| Final review | New workflows start from empty state (shared tool instances leaked earlier runs' media); inline cap 60 MB | `47081d8`, `dc28c8f` |
| B1 carry-over | Catalog guard covers every catalog and reports all mismatches; Gemini `_README` documents the flags | `bdc7a1c` |

## Process for the remaining tasks (decided 2026-09-30)

Batched and lighter than tasks 1–6:

| Batch | Plan tasks | Scope |
|---|---|---|
| B1 | 7, 8, 9 | Provider media contract; test-isolation fix; capability-aware selection and hints |
| B2 | 10, 11 | Shared tool helpers; simple tools and conversation carry-over |
| B3 | 12, 13, 14 | Auto mode and the MCP boundary; workflow tools; consensus pre-flight |
| B4 | 15, 16, 17 | Gemini encoder; file-list descriptions; live probes, CLI smoke test, final verification |

Per batch: one implementer subagent (TDD, one commit per task), then one combined spec-and-quality reviewer with a proportionate, time-boxed scope. The controller checks small fixes directly instead of running another review. Full re-review only for Critical or Important findings.

Per-task spec files are generated from the plan into a scratch directory (they do not survive a reboot, so regenerate as needed):

```bash
python3 - "$DEST" <<'EOF'
import re, sys
src = open('/Users/wrk/WorkDev/MCP-Dev/zen-media-input/docs/plans/2026-09-26-media-input-phase1.md').read()
head, rest = src.split('\n### Task 1:', 1)
rules = head.split('## Ground rules for the engineer', 1)[1].split('\n---', 1)[0]
chunks = re.split(r'\n### (Task \d+:)', '\n### Task 1:' + rest)
for i in range(1, len(chunks), 2):
    title, body = chunks[i], chunks[i + 1].split('\n## Done when')[0].rstrip().rstrip('-').rstrip()
    n = int(title.split()[1].rstrip(':'))
    open(f"{sys.argv[1]}/task{n:02d}.md", "w").write(f"# {title}{body}\n\n## Ground rules (from the plan)\n{rules}\n")
EOF
```

## Carry-over items to fold into the batches

From the Task 6 quality review (approved; these are plan-level):
- **B1 (done):** extend `tests/test_media_catalog_guard.py` to every `conf/*_models.json` (add `custom`, `dial`, `azure` with no `PROBED` entries, fail on an unmapped catalog), give a stale or misspelled `PROBED` entry a clear message instead of a bare `StopIteration`, and collect all mismatches. Document the three new fields in `conf/gemini_models.json` `_README.field_descriptions`.
- **B4 (before Task 17 runs):** add `--repeat N` and `--kinds` to `scripts/probe_media_support.py`, record errors separately from failures and exit non-zero on errors; re-probe audio three times on the eight flagged models; change Task 17's guidance so a single live miss is rerun before blaming the encoder. Consider a clearer audio fixture (slower speech, trailing silence) since the 1.96 s clip ends right after "seven".
- **Phase 2 (not phase 1):** `providers/azure_openai.py` clones OpenAI capabilities with `dataclasses.replace`, so flagging an OpenAI model would flag Azure deployments without a probe; clear media flags in the clone or guard the built capabilities. The design's OpenRouter rule (flags from `architecture.input_modalities`) conflicts with "every flag needs a live probe"; decide before phase 4.

From earlier reviews, already in the plan as "Also required" notes: Task 12 (`server.py` context-reconstruction fallback honours media; `os.path.isfile` guard before `looks_binary` on raw argument paths) and Task 13 (`convert_string_to_list` wraps a bare string instead of dropping it).

## Decisions recorded

- Gemini 2.5 Flash and Flash-Lite are not flagged for audio (each misheard the number once; flaky, not unsupported).
- Media is never deleted from the Gemini Files API by zen; uploads expire after 48 h (design).
- 2026-09-30: the user approved backing up `feat/media-input` to `origin`, live Gemini calls in B4, and merging phase 1 into `zen-cli-v2` and pushing when done (fetch and rebase first; it is shared with John).
- B1 review: `providers_hint` checks the provider's catalog before blaming an allow-list (`a6bebf1`). Nothing calls `ensure_media_encodable` or passes `required_media` yet; B2/B3 wire both in.
- B2 state: simple tools validate and send media. `_prepare_file_content_for_prompt` now announces media as attached for every caller, but the workflow tools (`workflow_mixin.py`), `consensus` and `debug`'s expert context only attach and check it from Tasks 13–14, so between B2 and B3 those tools claimed media they dropped. Closed in B3: every caller now validates and sends it (debug's expert context is sent by `_call_expert_analysis`).
- Found in B2, not media: MCP follow-ups embed the conversation history twice (BACKLOG, Maintenance).
