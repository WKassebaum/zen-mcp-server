# zen-skill

Authoritative Claude Code skill for invoking the `zen` CLI (v9.1.x).

Covers all 19 subcommands (chat, debug, consensus, codereview, secaudit, analyze, planner, thinkdeep, refactor, testgen, tracer, docgen, precommit, clink, challenge, apilookup, listmodels, setup, version), the multi-step `--session/--continue` workflow pattern, model selection, and guidance on when to spawn a sub-agent vs run zen directly via Bash.

## Auto-loaded in this repo

Claude Code reads project skills from `.claude/skills/` automatically. No action needed when working inside `zen-cli`.

## Install globally (optional)

To make this skill available to Claude Code in **every** project on your machine:

```bash
mkdir -p ~/.claude/skills/zen-skill
cp .claude/skills/zen-skill/SKILL.md   ~/.claude/skills/zen-skill/
cp .claude/skills/zen-skill/examples.md ~/.claude/skills/zen-skill/
```

Or symlink so the repo version stays canonical:

```bash
ln -sfn "$(pwd)/.claude/skills/zen-skill" ~/.claude/skills/zen-skill
```

## Files

- `SKILL.md` — primary guide (auto-loaded by Claude Code)
- `examples.md` — extended usage scenarios
- `README.md` — this file (install instructions)

## Updating

When `zen` adds/changes commands, update `SKILL.md` here in the repo and commit. Anyone with the symlinked global install picks up changes automatically; anyone who copied the file should re-run the copy commands above.

Verify against current CLI: `zen --help`, `zen <command> --help`, `zen version`.
