---
name: zen-skill
description: Authoritative guide for invoking the zen CLI (v9.1.x) - AI orchestration for chat, debugging, consensus, code review, security audit, planning, and structured multi-step workflows. CLI-first; MCP fallback documented at end.
---

# Zen — AI Orchestration via CLI

Zen exposes a multi-model AI toolkit (chat, consensus, debug, codereview, secaudit, analyze, planner, thinkdeep, refactor, testgen, tracer, docgen, precommit, clink, challenge, apilookup, listmodels, setup, version). Same backend as the `mcp__zen__*` MCP tools — different surface.

**Version reference:** zen 9.1.3 (2026-04). Verify with `zen version`.

---

## Use the CLI by default

The CLI is the primary interface. Reasons:

- Always available once `pip install -e .` (or pipx) — no MCP server lifecycle to manage
- `--json` output is parseable
- Multi-step workflows persist via `-s --session <id>` for up to 3 hours, surviving context resets
- One Bash call, one stdout — minimal failure surface
- Reach for MCP only when iterating ≥3 times in a single session against the same workflow tool (saves repeated CLI overhead)

**Sanity check before relying on it:**
```bash
which zen && zen version && zen listmodels --format simple | head
```

---

## Routing: direct Bash vs spawning a sub-agent

`Bash` puts the full stdout into the **main** conversation context — there is no firewall. A 4K-token `zen analyze` report stays in context until `/compact`.

A **sub-agent** (`general-purpose` or `Explore`) runs the Bash call itself, reads the full output, and returns only a capped synthesis. The raw output is discarded with the sub-agent.

| Scenario | Approach |
|---|---|
| `zen chat`, `zen listmodels`, `zen apilookup`, `zen challenge`, `zen version` | **Direct Bash** — output is short |
| `zen analyze`, `zen codereview`, `zen secaudit`, `zen tracer`, `zen docgen` | **Sub-agent** — heavy output, you want the synthesis |
| Any `--session/--continue` workflow run to completion | **Sub-agent** — drives the whole loop, returns one summary |
| Multi-model consensus / second opinions | **Parallel sub-agents** — one per model, syntheses collapse cleanly |
| You need the raw output verbatim for follow-up edits | **Direct Bash** — sub-agent summary is lossy by design |

When delegating, brief the sub-agent like a fresh colleague: state the goal, give the exact `zen ...` command, cap the report length (e.g., "report in under 300 words, include any code snippets verbatim"), and tell it whether to drive a multi-step workflow to completion.

---

## Two execution modes

### One-shot commands (single call, returns final answer)

`chat`, `consensus`, `challenge`, `apilookup`, `listmodels`, `version`, `setup`, `clink`

### Workflow commands (multi-step with sessions)

`analyze`, `codereview`, `debug`, `docgen`, `planner`, `precommit`, `refactor`, `secaudit`, `testgen`, `thinkdeep`, `tracer`

These are **iterative**: each invocation returns either a final answer or a `continuation_command` with investigation steps. You (or a sub-agent) perform the investigation, then resume:

```bash
# Step 1: start (session ID is auto-generated and printed in output)
zen analyze "Understand auth flow" -f src/auth/

# Step 2+: continue with findings
zen analyze --session analyze_1234_abcd --continue "Found JWT validation in middleware.py:42, refresh logic in tokens.py:88"

# Repeat until the response indicates the workflow is complete (3-hour session timeout)
```

When using `--json`, parse the `continuation_command` field to know what to invoke next. Sub-agents handle this loop cleanly without polluting main context.

---

## Command reference (all 19, verified against `--help`)

### One-shot

#### chat — quick consultation
```bash
zen chat <message> [--model <name>] [-f <file>]... [--json]
```
- `--model` defaults to `auto`. No `--temperature` or `--thinking-mode` flag exists.

#### consensus — multi-model decision
```bash
zen consensus <question> [-m <model1,model2,...>] [--json]
```
- `--models` is a comma-separated list. No per-model stance flag at CLI level.

#### challenge — force critical analysis
```bash
zen challenge <statement>... [--json]
```
- Wraps statement in critical-thinking instructions; use when validating a claim against reflexive agreement.

#### apilookup — API/SDK doc lookup instructions
```bash
zen apilookup <query>... [--json]
```
- Returns guidance for web-searching latest docs/breaking changes. Pair with `WebSearch`.

#### listmodels — enumerate available models
```bash
zen listmodels [--format table|json|simple]
```

#### version — show CLI version
```bash
zen version
```

#### setup — interactive setup wizard
```bash
zen setup
```
- Configures API keys, storage backend, and MCP registration. Never run autonomously.

#### clink — bridge to other AI CLIs (claude, codex, gemini, grok)
```bash
zen clink <prompt> --cli-name <claude|codex|gemini|grok> [--role <default|planner|codereviewer>] [-m|--model <id>] [-f <file>]... [-i <image>]... [--json]
```
- Spawns an external AI CLI as a full subagent in a fresh context; only the final result returns. The sub-CLI uses its own tools (web search, file access, shell) — unlike `chat`, which is a single model reply.
- **Reach for clink when**: (1) a task would burn heavy context in the current session (big review/audit/exploration — offload it, keep the conclusion); (2) you need a capability the current session lacks (gemini's 1M context or web search); (3) you want the work billed to a CLI subscription instead of per-token API keys.
- **Subscription auth (login tokens)**: `claude` runs on a Claude Pro/Max login and `grok` on a Grok subscription login (xAI's Grok Build CLI) — the only ToS-sanctioned ways to do agentic work on those plans; no ANTHROPIC_API_KEY/XAI_API_KEY needed. `gemini` gives 1,000 free requests/day on a personal Google login. See docs/tools/clink.md "Subscription Authentication".
- **Pick by strength**: `gemini` = 1M context + web search; `claude` = strongest coding agent on subscription; `grok` = fast agentic coding on subscription; `codex` = isolated implementation/review sandbox.
- **Model override (`-m/--model`)**: passed through to the target CLI as `--model`, replacing any config-pinned default (e.g. `claude.json` hard-pins `sonnet`). CLI-specific aliases — for Claude Code prefer `fable` / `opus` / `sonnet` (note: Claude CLI rejects Zen's `fable-5` alias; use `fable` or `claude-fable-5`). Example: `zen clink "audit auth" --cli-name claude --model fable --json`.
- **Roles**: `planner` (strategy/breakdown), `codereviewer` (severity-tagged review), `default` (general). Prerequisite: the target CLI must be installed and logged in (`claude`, `grok login`, etc.).

### Workflow (all support `-s --session`, `--continue`, `-m --model`, `--json`)

#### analyze — architecture & code analysis
```bash
zen analyze <goal> [-f <file>]... [--analysis-type architecture|patterns|complexity|all]
```

#### codereview — professional review with severity
```bash
zen codereview -f <file>... [--type quality|security|performance|all]
```
**Note:** flag is `--type` (not `--review-type`), choices are `quality|security|performance|all`.

#### debug — systematic investigation
```bash
zen debug <problem> [-f <file>]... [--confidence exploring|low|medium|high|certain]
```

#### docgen — generate documentation
```bash
zen docgen <goal> [-f <file>]... [--style docstring|markdown|jsdoc|godoc]
```

#### planner — sequential task breakdown
```bash
zen planner <goal> [-f <file>]...
```

#### precommit — pre-commit validation
```bash
zen precommit <goal> [-f <file>]...
```

#### refactor — refactoring suggestions
```bash
zen refactor <goal> [-f <file>]... [--refactor-type readability|performance|maintainability|codesmells|all]
```

#### secaudit — security audit
```bash
zen secaudit <goal> [-f <file>]... [--focus auth|crypto|injection|all]
```

#### testgen — test suite generation
```bash
zen testgen <goal> [-f <file>]... [--framework <name>] [--test-type unit|integration|e2e|all]
```

#### thinkdeep — extended reasoning
```bash
zen thinkdeep <question> [--thinking-budget <128-32768>] [-m <model>]
```
- Requires a model that supports extended thinking (gpt-5.5-pro, claude-opus-4-7, gemini-3.1-pro-preview, o3).

#### tracer — code-flow / dependency tracing
```bash
zen tracer <target> [--depth <N>] [--trace-mode forward|backward|both|ask]
```

---

## Model selection

Auto-mode picks by `intelligence_score`. Current SOTA per provider (as of 2026-04):

| Provider | Top model | Aliases |
|---|---|---|
| Anthropic | `claude-opus-4-7` | `opus`, `claude-opus`, `opus-4.7` |
| OpenAI | `gpt-5.5-pro` | `gpt5.5-pro`, `gpt-5-5-pro` |
| OpenAI (balanced) | `gpt-5.5` | `gpt5.5`, `gpt-5-5` |
| Google | `gemini-3.1-pro-preview` | varies |
| xAI | `grok-4.20-beta-0309-reasoning` | `grok`, `grok4` |

Verify with `zen listmodels --format simple` — config lives in `conf/*_models.json` in the zen-cli project and changes over time.

**Picking a model explicitly:**
```bash
zen chat "validate this approach" --model opus           # Anthropic flagship
zen debug "race condition" --model gpt-5.5-pro -f x.py   # Frontier reasoning
zen analyze "perf bottlenecks" --model gemini-3.1-pro-preview -f src/
```

Default `auto` is fine for most cases.

---

## Common flags

- `-f, --files <path>` — repeatable; absolute paths preferred. Directory paths expand.
- `-m, --model <name>` — override auto-mode model selection.
- `--json` — machine-parseable output. Always use this when a sub-agent or shell pipeline will consume the result.
- `-s, --session <id>` — workflow commands only; resume an existing session.
- `--continue <findings>` — workflow commands only; submit investigation results to advance the workflow.

---

## Configuration & paths

- **API keys & storage:** `~/.zen/.env` (created/updated by `zen setup`)
- **Conversation persistence:** `~/.zen/conversations/`
- **CLI binary location:** depends on install — `which zen` to confirm
- **Logs (when running as MCP server):** `<zen-cli-root>/logs/mcp_server.log`, `mcp_activity.log`

---

## Sub-agent invocation patterns

### Pattern 1: Heavy single command

```
Agent({
  description: "Security audit of auth module",
  subagent_type: "general-purpose",
  prompt: "Run `zen secaudit 'Audit authentication for OWASP Top 10' -f src/auth/ --focus auth --json` from /Users/wrk/project. Drive any --session/--continue follow-ups to completion. Report findings in under 400 words: top 3 vulnerabilities (severity + file:line + fix), then 'no further critical issues' if applicable. Include exact code snippets for any fix recommendations."
})
```

### Pattern 2: Parallel multi-model second opinion

Send a single message with N Agent calls (one per model). Each runs `zen chat "<question>" --model <X> --json`, returns a 100-word synthesis. Main thread compares.

### Pattern 3: Multi-step workflow run to completion

```
Agent({
  description: "Plan OAuth migration",
  subagent_type: "general-purpose",
  prompt: "Drive `zen planner 'Migrate from session auth to OAuth2' -f src/auth/ --json` to completion. For each step, parse continuation_command from JSON, perform any requested investigation against the codebase, and resume with --session/--continue. When workflow signals complete, return the final plan as a numbered checklist (no preamble)."
})
```

---

## When to fall back to MCP

Use `mcp__zen__*` tools instead of CLI when:

1. The MCP server is already registered with this Claude session, **and**
2. You will iterate ≥3 times against the same workflow tool in this conversation, **and**
3. You need structured tool-result types (not just JSON strings) for downstream reasoning.

Otherwise prefer CLI. The MCP and CLI tools share the same backend, models, and quality.

**MCP tool naming:** `mcp__zen__chat`, `mcp__zen__consensus`, `mcp__zen__debug`, `mcp__zen__codereview`, `mcp__zen__analyze`, `mcp__zen__planner`, `mcp__zen__thinkdeep`, `mcp__zen__refactor`, `mcp__zen__testgen`, `mcp__zen__precommit`, `mcp__zen__secaudit`, `mcp__zen__tracer`, `mcp__zen__docgen`, `mcp__zen__clink`, `mcp__zen__listmodels`, `mcp__zen__challenge`, `mcp__zen__apilookup`. Workflow tools require structured params (`step`, `step_number`, `total_steps`, `next_step_required`, `findings`, `confidence`, `model`, `relevant_files`).

---

## Troubleshooting

| Symptom | First check |
|---|---|
| `zen: command not found` | `which zen`; if missing, `pip install -e .` from zen-cli root, or `pipx install zen-mcp-server` |
| "Model not found" | `zen listmodels` to see actual aliases; check `~/.zen/.env` for the relevant API key |
| Workflow never completes | You stopped responding to `continuation_command` — resume with `--session <id> --continue "<findings>"` |
| Silent slow response | Some models (gpt-5.5-pro, o3-pro) use async Responses API; can take minutes — use `--json` and run via sub-agent |
| Empty/garbled output | Check `~/.zen/.env` has at least one valid provider key; run `zen setup` to reconfigure |

---

## Quick decision tree

```
User asks for AI consultation/review/audit/plan?
  ├─ Output will be short (<800 tokens, e.g. chat, listmodels) → direct Bash
  ├─ Output will be heavy → spawn general-purpose sub-agent
  ├─ Multi-step workflow (analyze, planner, debug, secaudit, etc.) → spawn sub-agent, drive --session loop
  └─ Need N independent perspectives → spawn N sub-agents in parallel, one per model
```

That covers 95% of zen invocations. When in doubt, prefer sub-agent — context is the scarcer resource than spawn cost.
