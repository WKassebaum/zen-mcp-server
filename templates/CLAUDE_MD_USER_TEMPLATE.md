# Zen MCP Integration Template for CLAUDE.md

**Copy the sections below that are relevant to your project and add them to your CLAUDE.md file.**

---

## 🧠 Zen MCP - AI Orchestration & Multi-Model Collaboration

### Overview

Zen MCP enables your AI assistant (Claude, Codex, etc.) to orchestrate multiple AI models for enhanced analysis, debugging, code reviews, and collaborative development. This integration provides access to Gemini, OpenAI, O3, and 50+ other models through a unified interface.

**Key Capabilities:**
- **Multi-Model Orchestration** - Consult multiple AI models for different perspectives
- **Conversation Continuity** - Full context flows across tools and models
- **Workflow Tools** - Systematic multi-step workflows for complex tasks
- **CLI Bridge (clink)** - Connect external AI CLIs (Gemini CLI, Codex CLI, etc.)
- **Direct Content Support** - Pass content via stdin without saving files

---

## 🔧 Core Tools Reference

### Quick Consultation Tools (Single-Step)
- **`mcp__zen__chat`** - Brainstorm ideas, get second opinions, validate approaches
- **`mcp__zen__consensus`** - Multi-model debate and decision making
- **`mcp__zen__clink`** - Bridge to external AI CLIs (Gemini CLI, Codex CLI, Claude Code)

### Systematic Workflow Tools (Multi-Step)
- **`mcp__zen__debug`** - Root cause analysis with hypothesis tracking
- **`mcp__zen__codereview`** - Professional code reviews (quality, security, performance)
- **`mcp__zen__planner`** - Break down complex projects into plans
- **`mcp__zen__precommit`** - Validate changes before committing
- **`mcp__zen__thinkdeep`** - Extended reasoning for complex decisions
- **`mcp__zen__analyze`** - Architecture and pattern analysis
- **`mcp__zen__refactor`** - Code quality and refactoring suggestions
- **`mcp__zen__testgen`** - Comprehensive test generation
- **`mcp__zen__secaudit`** - Security vulnerability assessment
- **`mcp__zen__docgen`** - Documentation generation
- **`mcp__zen__tracer`** - Code execution flow tracing

### Utility Tools
- **`mcp__zen__apilookup`** - Current API/SDK documentation lookup
- **`mcp__zen__challenge`** - Critical thinking validation
- **`mcp__zen__listmodels`** - Show available models and capabilities
- **`mcp__zen__version`** - Server version and configuration

---

## 🎯 Auto-Trigger Patterns

### When to Use Zen MCP (Automatic Triggers)

**ALWAYS use Zen when:**
- Debugging issues that have taken >5 minutes without progress → `mcp__zen__debug`
- Making architectural decisions affecting >2 components → `mcp__zen__consensus`
- Reviewing code for security implications → `mcp__zen__codereview` or `mcp__zen__secaudit`
- Need consensus on technology choices → `mcp__zen__consensus`
- Analyzing unfamiliar codebases >50 files → `mcp__zen__analyze`
- Planning complex features with >3 major components → `mcp__zen__planner`

**CONSIDER using Zen when:**
- Confidence < 80% on technical recommendations → `mcp__zen__chat`
- User explicitly asks for "second opinion" or "validation" → `mcp__zen__chat` or `mcp__zen__consensus`
- Working with critical systems (auth, payment, security) → `mcp__zen__secaudit`
- Need to explain complex technical tradeoffs → `mcp__zen__thinkdeep`
- Refactoring significant portions of codebase → `mcp__zen__refactor`

---

## 📋 Usage Patterns & Examples

### Pattern 1: Quick Consultation
```json
// Get quick validation or second opinion
{
  "tool": "mcp__zen__chat",
  "prompt": "Is using Redis for session storage appropriate for our scale?",
  "model": "gemini-2.5-pro"
}
```

### Pattern 2: Multi-Model Consensus
```json
// Get multiple expert opinions
{
  "tool": "mcp__zen__consensus",
  "prompt": "Should we migrate from REST to GraphQL?",
  "models": [
    {"model": "gemini-2.5-pro", "stance": "for"},
    {"model": "o3", "stance": "against"},
    {"model": "gpt-5", "stance": "neutral"}
  ]
}
```

### Pattern 3: Systematic Debugging
```json
// Step 1: Start investigation
{
  "tool": "mcp__zen__debug",
  "step": "Memory leak occurs after 1000 requests",
  "step_number": 1,
  "total_steps": 3,
  "confidence": "exploring",
  "relevant_files": ["/path/to/app.py", "/path/to/worker.py"],
  "model": "gemini-2.5-pro"
}

// Step 2: Continue with findings
{
  "continuation_id": "debug_xxx_yyy",
  "step": "Found unclosed connections in worker.py line 45",
  "step_number": 2,
  "findings": "Database connections not properly closed in error handler",
  "confidence": "high"
}
```

### Pattern 4: Code Review Workflow
```json
// Systematic code review with expert validation
{
  "tool": "mcp__zen__codereview",
  "step": "Review authentication module for security issues",
  "step_number": 1,
  "total_steps": 2,
  "relevant_files": ["/path/to/auth.py", "/path/to/session.py"],
  "review_type": "security",
  "model": "o3"
}
```

### Pattern 5: CLI Bridge (clink)
```json
// Spawn external CLI subagent for isolated work
{
  "tool": "mcp__zen__clink",
  "cli_name": "gemini",
  "role": "codereviewer",
  "prompt": "Audit auth module for security issues",
  "files": ["/path/to/auth/*.py"]
}
```

---

## 🔄 Workflow Tool Protocol

### Multi-Step Workflow Structure

**Step 1 - Start Workflow:**
```json
{
  "step": "Describe investigation strategy",
  "step_number": 1,
  "total_steps": 5,
  "next_step_required": true,
  "findings": "Initial observations",
  "model": "gemini-2.5-pro"
}
```

**Response includes:**
- `continuation_id` - Session identifier for continuing
- `next_step_required` - Whether more steps are needed
- `workflow_instructions` - Guidance for next step

**Step 2+ - Continue Workflow:**
```json
{
  "continuation_id": "debug_xxx_yyy",
  "step": "Investigation results from previous step",
  "step_number": 2,
  "findings": "What you discovered",
  "next_step_required": true
}
```

**CRITICAL**: When `next_step_required: true`:
1. ✅ Perform the investigation described
2. ✅ Call with `continuation_id` and your findings
3. ✅ Update `findings` with cumulative discoveries
4. ❌ Do NOT abandon workflow mid-step

---

## 🎨 Model Selection Guide

### Recommended Models by Task

**Fast Responses (< 2 seconds):**
- `gemini-2.5-flash` - Gemini's fastest model
- `flash` - Alias for gemini-2.5-flash
- `flashlite` - Even faster, lightweight

**Deep Analysis & Complex Reasoning:**
- `gemini-2.5-pro` - Gemini's most capable (1M token context)
- `gpt-5-pro` - OpenAI's reasoning model (400K context)
- `o3` - Strong logical reasoning

**Automatic Selection:**
- `auto` - Let Zen choose optimal model (default)

### Model Selection Decision Matrix

| Task Type | Recommended Model | Why |
|-----------|------------------|-----|
| Quick validation | `flash` | Speed optimized |
| Code review | `gemini-2.5-pro` or `o3` | Deep analysis |
| Debugging | `gemini-2.5-pro` or `gpt-5-pro` | Extended context |
| Security audit | `o3` or `gpt-5-pro` | Precision reasoning |
| Architecture planning | `gemini-2.5-pro` | Large context window |
| Consensus decisions | Multiple models | Diverse perspectives |

---

## 💡 Advanced Integration Patterns

### Pattern: Multi-Model Code Review Workflow
```
User: "Perform comprehensive code review using multiple models"

Your Workflow:
1. Use mcp__zen__codereview with your analysis (Step 1)
2. Continue with detailed findings (Step 2)
3. System automatically consults expert model (Gemini Pro or O3)
4. Receive unified review with all findings combined
```

### Pattern: Context Revival After Reset
```
When context resets mid-task:
1. User: "Continue debugging the OAuth issue"
2. Use mcp__zen__chat with continuation_id from previous conversation
3. Model retrieves full context and continues seamlessly
```

### Pattern: Collaborative Debugging
```
1. Start with mcp__zen__debug (systematic investigation)
2. Get stuck? Use mcp__zen__consensus for multiple perspectives
3. Solution found? Use mcp__zen__precommit to validate changes
4. All tools share conversation context automatically
```

### Pattern: CLI Subagent Delegation
```
1. Complex task detected (e.g., "audit entire codebase")
2. Use mcp__zen__clink to spawn Gemini CLI subagent
3. Subagent performs isolated investigation in fresh context
4. Returns final report without polluting your context window
5. Continue with implementation using subagent's findings
```

---

## 🔐 File Handling Best Practices

### Passing File Context

**Method 1: File Paths (Traditional)**
```json
{
  "relevant_files": [
    "/absolute/path/to/file.py",
    "/absolute/path/to/directory/"
  ]
}
```

**Method 2: Directory Expansion**
```json
{
  "relevant_files": [
    "/path/to/src/"  // Auto-expands to all files in directory
  ]
}
```

**Important File Handling Rules:**
1. ✅ Always use **absolute paths**
2. ✅ Directories are automatically expanded
3. ✅ Files are deduplicated per tool
4. ❌ Never use relative paths (e.g., `./file.py`)
5. ❌ Never use shortened paths (e.g., `.../file.py`)

---

## 🎓 Best Practices

### Workflow Management
1. **Complete Workflows** - Don't abandon multi-step workflows
2. **Provide Context** - Include relevant files for better analysis
3. **Choose Right Model** - Match model capabilities to task complexity
4. **Track Confidence** - Use confidence levels to gauge investigation completeness
5. **Leverage Continuity** - Reuse continuation_id for related tasks

### Model Usage
1. **Start with Fast Models** - Use `flash` for initial exploration
2. **Escalate When Needed** - Switch to `pro` or `o3` for complex analysis
3. **Multi-Model for Critical Decisions** - Use `consensus` for important choices
4. **Check Available Models** - Use `listmodels` to see configured providers

### Context Optimization
1. **Specify Relevant Files Only** - Include only files needed for task
2. **Use Directories Wisely** - Let system expand directories automatically
3. **Leverage Continuation** - Reuse sessions for related investigations
4. **CLI Subagents for Isolation** - Use `clink` for large independent tasks

---

## 🚨 Common Patterns to Avoid

### ❌ Don't Do This

**Abandoning Workflows:**
```
// Bad: Starting workflow and not continuing
Step 1: "Analyzing architecture..."
// Then switching to different task
```

**Using Relative Paths:**
```json
{
  "relevant_files": ["./src/auth.py"]  // ❌ Will fail
}
```

**Not Providing Context:**
```json
{
  "prompt": "Debug the OAuth issue"  // ❌ No files or context
}
```

### ✅ Do This Instead

**Complete Workflows:**
```
Step 1: "Analyzing architecture..." → Continue with findings
Step 2: "Found MVC pattern..." → Continue until complete
```

**Use Absolute Paths:**
```json
{
  "relevant_files": ["/Users/you/project/src/auth.py"]  // ✅
}
```

**Provide Rich Context:**
```json
{
  "prompt": "Debug OAuth token persistence issue",
  "relevant_files": ["/Users/you/project/src/auth/", "/Users/you/project/src/session.py"],
  "model": "gemini-2.5-pro"
}
```

---

## 📊 Tool Comparison Matrix

| Tool | Use Case | Steps | Model Recommendation |
|------|----------|-------|---------------------|
| `chat` | Quick questions | 1 | flash/gemini-pro |
| `consensus` | Critical decisions | 1-2 | Multiple models |
| `debug` | Root cause analysis | 2-5 | gemini-pro/o3 |
| `codereview` | Code quality | 2-3 | gemini-pro/o3 |
| `planner` | Project breakdown | 3-7 | flash/gemini-pro |
| `thinkdeep` | Complex reasoning | 2-5 | gemini-pro |
| `analyze` | Architecture review | 2-4 | gemini-pro |
| `precommit` | Change validation | 2-3 | flash/gemini-pro |
| `clink` | CLI delegation | 1 | N/A (uses target CLI) |

---

## 🔍 Troubleshooting

### Session Expired
```
Error: "Session 'xxx' not found or expired"
Solution: Sessions expire after 3-6 hours. Start new workflow.
```

### Model Not Available
```
Error: "Model 'o3' not configured"
Solution: Check available models with mcp__zen__listmodels
Use --model auto to let Zen choose
```

### File Not Found
```
Error: "File not found: ./src/auth.py"
Solution: Use absolute paths: /Users/you/project/src/auth.py
```

### Workflow Stuck
```
Symptom: Same step repeating
Solution: Ensure you're providing investigation RESULTS, not repeating the prompt
Include findings parameter with actual discoveries
```

---

## 📚 Quick Reference

### Essential Tool Calls

**Quick Consultation:**
```
mcp__zen__chat with prompt="question" model="flash"
```

**Multi-Model Consensus:**
```
mcp__zen__consensus with prompt="decision?" models=[{"model":"gemini-pro"},{"model":"o3"}]
```

**Start Debug Investigation:**
```
mcp__zen__debug with step="problem description" step_number=1 model="gemini-pro"
```

**Continue Workflow:**
```
mcp__zen__debug with continuation_id="xxx" step="findings from investigation" step_number=2
```

**Code Review:**
```
mcp__zen__codereview with step="review strategy" relevant_files=["/path/to/files"] step_number=1 model="o3"
```

**CLI Bridge:**
```
mcp__zen__clink with cli_name="gemini" role="planner" prompt="create implementation plan"
```

---

## 🎯 Integration Checklist

### Setup Verification
- [ ] Zen MCP server is running (`mcp__zen__version`)
- [ ] API keys are configured (`mcp__zen__listmodels`)
- [ ] At least one provider is available (Gemini/OpenAI/etc.)
- [ ] File paths use absolute paths
- [ ] Tools are enabled (check DISABLED_TOOLS setting)

### Workflow Verification
- [ ] Start workflows with step_number=1
- [ ] Continue workflows with continuation_id
- [ ] Provide findings parameter with discoveries
- [ ] Track confidence levels (exploring → certain)
- [ ] Complete workflows (next_step_required=false)

### Best Practices
- [ ] Use fast models first (flash)
- [ ] Escalate to pro/o3 when needed
- [ ] Leverage consensus for critical decisions
- [ ] Include relevant files for context
- [ ] Use clink for large isolated tasks

---

## 📖 Additional Resources

**Full Documentation:**
- Tool Details: See individual tool documentation in `docs/tools/`
- Advanced Usage: `docs/advanced-usage.md`
- Configuration: `docs/configuration.md`
- Troubleshooting: `docs/troubleshooting.md`

**Key Concepts:**
- [Conversation Continuity](docs/advanced-usage.md#conversation-continuity)
- [Context Revival](docs/context-revival.md)
- [Model Selection](docs/advanced-usage.md#model-selection)
- [Thinking Modes](docs/advanced-usage.md#thinking-modes)
- [CLI Bridge (clink)](docs/tools/clink.md)

---

**Template Version:** 2.0
**Compatible with:** Zen MCP v5.14.0+
**Last Updated:** 2025-01-14

---

## 🎨 Optional: Custom Integration Patterns

### For Large Codebases
```
When analyzing codebases >50 files:
1. First use Claude-Codeindex for semantic search (if available)
2. Then use mcp__zen__analyze for architecture assessment
3. Finally use mcp__zen__codereview for quality validation
```

### For Security-Critical Projects
```
Always run before commits:
1. mcp__zen__secaudit for vulnerability scan
2. mcp__zen__precommit for change validation
3. mcp__zen__consensus with security-focused models
```

### For Complex Features
```
Full feature development cycle:
1. mcp__zen__planner - Break down requirements
2. mcp__zen__analyze - Understand existing architecture
3. [Your implementation work]
4. mcp__zen__testgen - Generate comprehensive tests
5. mcp__zen__codereview - Quality validation
6. mcp__zen__precommit - Final validation
```

---

**End of Template** - Copy relevant sections to your project's CLAUDE.md file
