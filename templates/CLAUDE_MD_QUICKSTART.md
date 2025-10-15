# Zen MCP Quick Start Template

**Minimal setup for getting started with Zen MCP in your CLAUDE.md**

---

## 🧠 Zen MCP Integration

### Quick Setup

Add this section to your project's CLAUDE.md to enable AI orchestration with multiple models.

### Available Tools

**Quick Consultation:**
- `mcp__zen__chat` - Get second opinions and validate approaches
- `mcp__zen__consensus` - Multi-model consensus for critical decisions
- `mcp__zen__clink` - Bridge to external AI CLIs (Gemini, Codex, etc.)

**Systematic Workflows:**
- `mcp__zen__debug` - Root cause analysis
- `mcp__zen__codereview` - Code quality and security review
- `mcp__zen__planner` - Break down complex projects
- `mcp__zen__precommit` - Validate changes before committing

### Auto-Trigger Patterns

**Always use Zen when:**
- Debugging >5 minutes without progress → `debug`
- Architectural decisions affecting >2 components → `consensus`
- Security code reviews → `codereview` or `secaudit`
- Complex feature planning → `planner`
- Pre-commit validation → `precommit`

### Usage Examples

**Quick Consultation:**
```
Use zen chat to validate: "Is Redis appropriate for our session storage?"
```

**Multi-Model Consensus:**
```
Use zen consensus with gemini-pro and o3 to decide: REST vs GraphQL migration
```

**Systematic Debugging:**
```
Use zen debug to investigate: "Memory leak after 1000 requests"
Continue with findings until root cause identified
```

**Code Review:**
```
Use zen codereview for security audit of auth module
```

### Model Selection

- `flash` - Fast responses (default)
- `gemini-2.5-pro` - Deep analysis
- `o3` - Strong reasoning
- `auto` - Let Zen choose

### Workflow Protocol

**Multi-step tools** (debug, codereview, planner):
1. Start with step 1 and initial investigation
2. Receive continuation_id in response
3. Continue with findings from investigation
4. Repeat until workflow completes

**Critical Rule**: When tool returns `next_step_required: true`, you MUST:
- Perform the investigation described
- Continue with continuation_id and your findings
- Never abandon workflow mid-step

### File Context

**Always use absolute paths:**
✅ `/Users/you/project/src/auth.py`
❌ `./src/auth.py`

**Include relevant files:**
```json
{
  "relevant_files": [
    "/absolute/path/to/file.py",
    "/absolute/path/to/directory/"
  ]
}
```

---

## 📋 Quick Reference

**Start investigation:**
```
mcp__zen__debug: step="Problem description" step_number=1 model="gemini-pro"
```

**Continue workflow:**
```
mcp__zen__debug: continuation_id="xxx" step="Investigation results" step_number=2
```

**Get consensus:**
```
mcp__zen__consensus: prompt="Decision?" models=[{"model":"gemini-pro"},{"model":"o3"}]
```

**Quick validation:**
```
mcp__zen__chat: prompt="Validate this approach" model="flash"
```

---

**Next Steps:**
- Run `mcp__zen__listmodels` to see available models
- Run `mcp__zen__version` to verify server is running
- See full template: `templates/CLAUDE_MD_USER_TEMPLATE.md`

---

**Template Version:** 2.0 (Quick Start)
**Last Updated:** 2025-01-14
