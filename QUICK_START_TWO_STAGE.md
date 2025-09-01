# Quick Start: Two-Stage Token Optimization

## TL;DR - Save 95% Tokens in 2 Steps

### Step 1: Ask What Mode to Use
```json
{
  "tool": "zen_select_mode",
  "arguments": {
    "task_description": "Your task here"
  }
}
```

### Step 2: Execute with That Mode
```json
{
  "tool": "zen_execute",
  "arguments": {
    "mode": "mode_from_step_1",
    "request": {
      /* parameters from step 1 */
    }
  }
}
```

**That's it! You just saved 95% tokens (43k → 800)!**

---

## Common Patterns

### Debugging Something
```json
// Step 1
{ "tool": "zen_select_mode", 
  "arguments": { "task_description": "Debug why X isn't working" }}

// Step 2 (use response from Step 1)
{ "tool": "zen_execute",
  "arguments": {
    "mode": "debug",
    "request": {
      "problem": "X isn't working",
      "files": ["/relevant/file.py"],
      "confidence": "exploring"
    }
  }}
```

### Code Review
```json
// Step 1
{ "tool": "zen_select_mode",
  "arguments": { "task_description": "Review auth system for security" }}

// Step 2
{ "tool": "zen_execute",
  "arguments": {
    "mode": "codereview",
    "request": {
      "files": ["/src/auth.py"],
      "review_type": "security"
    }
  }}
```

### Quick Chat/Question
```json
// Step 1
{ "tool": "zen_select_mode",
  "arguments": { "task_description": "How should I implement OAuth?" }}

// Step 2
{ "tool": "zen_execute",
  "arguments": {
    "mode": "chat",
    "request": {
      "prompt": "How should I implement OAuth for a React app?"
    }
  }}
```

## Available Modes

| Mode | Purpose | When to Use |
|------|---------|-------------|
| `debug` | Root cause analysis | Bugs, errors, issues |
| `codereview` | Code quality assessment | PR reviews, audits |
| `analyze` | Architecture analysis | Design decisions |
| `chat` | General consultation | Questions, brainstorming |
| `consensus` | Multi-model agreement | Complex decisions |
| `security` | Security audit | Vulnerabilities, threats |
| `refactor` | Improvement opportunities | Code smells, debt |
| `testgen` | Test generation | Coverage, edge cases |
| `planner` | Task planning | Breaking down work |
| `tracer` | Code tracing | Execution flow |

## FAQ

### Q: Do I always need both steps?
**A:** Yes, for token optimization. Stage 1 determines the minimal schema for Stage 2.

### Q: What if I know the mode already?
**A:** Still use Stage 1 - it provides the exact fields needed and examples.

### Q: Can I use the old tools?
**A:** Yes, they're available as fallback but use 50x more tokens.

### Q: How much does this really save?
**A:** 95% token reduction - from 43,000 to 200-800 tokens total!

### Q: What's the complexity parameter?
**A:** Optional. Use "simple" (default), "workflow" (multi-step), or "expert" (comprehensive).

## Tips for Claude Code Users

1. **Claude knows the pattern**: Just ask Claude to use Zen tools - it will automatically use two-stage flow

2. **Check CLAUDE.md**: Your project's CLAUDE.md file has the pattern configured

3. **Token telemetry**: Check `~/.zen_mcp/token_telemetry.jsonl` to see your savings

4. **Backwards compatible**: Original tools still work if you disable optimization

## Enable/Disable Optimization

```bash
# Enable (save 95% tokens)
echo "ZEN_TOKEN_OPTIMIZATION=enabled" >> .env
docker-compose restart

# Disable (use original tools)
echo "ZEN_TOKEN_OPTIMIZATION=disabled" >> .env
docker-compose restart
```

## Example: Complete Debug Session

```bash
# 1. Claude identifies issue
"I need to debug why OAuth tokens aren't persisting"

# 2. Stage 1: Mode selection (200 tokens)
zen_select_mode → recommends "debug" mode

# 3. Stage 2: Execution (600 tokens)
zen_execute with mode="debug" → provides solution

# Total: 800 tokens (vs 43,000 tokens before!)
```

## Support

- **Stuck?** The tools provide helpful error messages
- **Wrong mode?** Stage 1 suggests alternatives
- **Need help?** Check TOKEN_OPTIMIZATION_IMPLEMENTATION_PLAN.md

---

**Remember: Two steps = 95% savings!**  
`zen_select_mode` → `zen_execute` → Done! 🚀