# Global CLAUDE.md Template - Zen MCP Integration

**Add this to your global ~/.claude/CLAUDE.md for system-wide Zen MCP support**

---

## 🧠 Zen MCP - AI Orchestration Across All Projects

### Overview

Zen MCP enables multi-model AI collaboration across all your projects. Add this to your global CLAUDE.md for consistent behavior across all sessions.

### Core Integration Patterns

#### Auto-Trigger Rules
```yaml
# Automatically use Zen when encountering these patterns

Debugging_Stuck:
  Pattern: "stuck for >5 minutes", "can't figure out", "mysterious error"
  Action: Use mcp__zen__debug with systematic investigation
  Model: gemini-2.5-pro or o3

Architecture_Decisions:
  Pattern: "should we use", "architecture decision", "technology choice"
  Action: Use mcp__zen__consensus with multiple models
  Models: gemini-2.5-pro, o3, gpt-5

Security_Reviews:
  Pattern: "security", "authentication", "authorization", "vulnerability"
  Action: Use mcp__zen__codereview or mcp__zen__secaudit
  Model: o3 (for precision)

Code_Quality:
  Pattern: "review this", "check code quality", "before commit"
  Action: Use mcp__zen__codereview or mcp__zen__precommit
  Model: gemini-2.5-pro or flash

Complex_Planning:
  Pattern: "plan the implementation", "break down", "roadmap"
  Action: Use mcp__zen__planner with systematic breakdown
  Model: flash or gemini-pro

Low_Confidence:
  Pattern: confidence < 80% on technical recommendation
  Action: Use mcp__zen__chat or mcp__zen__consensus for validation
  Model: gemini-2.5-pro
```

#### Model Selection Strategy
```yaml
Task_Based_Selection:
  Quick_Questions: flash (< 2s response)
  Deep_Analysis: gemini-2.5-pro (1M context)
  Logical_Reasoning: o3 (strong reasoning)
  Large_Codebase: gemini-2.5-pro (1M context)
  Security_Audit: o3 (precision)
  Multi_Perspective: consensus with multiple models

Performance_Optimization:
  Start_Fast: Use flash for initial exploration
  Escalate_Smart: Switch to pro/o3 when complexity increases
  Multi_Model_Critical: Use consensus for important decisions
```

#### Workflow Management
```yaml
Multi_Step_Tools:
  - debug (2-5 steps)
  - codereview (2-3 steps)
  - planner (3-7 steps)
  - thinkdeep (2-5 steps)
  - analyze (2-4 steps)

Protocol:
  Step_1: Start with step_number=1, total_steps estimate
  Step_N: Continue with continuation_id from previous response
  Completion: When next_step_required=false

Critical_Rule: >
  When next_step_required=true, you MUST:
  1. Perform the investigation described
  2. Continue with continuation_id and findings
  3. Never abandon workflow mid-step
```

### Tool Selection Matrix

```yaml
Consultation:
  Tool: mcp__zen__chat
  When: Quick validation, second opinion, brainstorming
  Steps: 1
  Model: flash or gemini-pro

Consensus:
  Tool: mcp__zen__consensus
  When: Critical decisions, architecture choices, technology selection
  Steps: 1-2
  Model: Multiple (gemini-pro, o3, gpt-5)

Debugging:
  Tool: mcp__zen__debug
  When: Complex bugs, mysterious errors, root cause analysis
  Steps: 2-5
  Model: gemini-2.5-pro or o3

Code_Review:
  Tool: mcp__zen__codereview
  When: Quality check, security audit, pre-commit validation
  Steps: 2-3
  Model: gemini-2.5-pro or o3

Planning:
  Tool: mcp__zen__planner
  When: Feature planning, project breakdown, migration strategy
  Steps: 3-7
  Model: flash or gemini-pro

CLI_Bridge:
  Tool: mcp__zen__clink
  When: Isolated sub-tasks, fresh context needed, external CLI capabilities
  Steps: 1
  Model: N/A (uses target CLI)
```

### File Handling Standards

```yaml
Path_Requirements:
  Format: Absolute paths only
  Good: "/Users/you/project/src/auth.py"
  Bad: "./src/auth.py", "~/project/src/auth.py"

Directory_Expansion:
  Feature: Automatic directory expansion
  Usage: "/Users/you/project/src/" → expands to all files

File_Deduplication:
  Scope: Per-tool automatic deduplication
  Benefit: Prevents duplicate file processing

Context_Optimization:
  Include: Only files relevant to current task
  Avoid: Including entire codebase unnecessarily
```

### Integration with Other MCP Tools

```yaml
# When multiple MCP servers are available

Claude_Codeindex_First:
  Condition: Codebase >50 files
  Action: Use codeindex for semantic search FIRST
  Then: Use Zen for analysis/review

Memory_Keeper_Check:
  Condition: Starting any Zen workflow
  Action: Check Memory Keeper for relevant past solutions
  Then: Proceed with Zen tools using historical context

Combined_Workflows:
  Pattern_1: codeindex search → zen analyze → zen codereview
  Pattern_2: memory_keeper recall → zen debug → memory_keeper save
  Pattern_3: zen consensus → zen planner → zen precommit
```

### Advanced Usage Patterns

#### Pattern: Multi-Model Code Review
```
1. Start codereview with your initial analysis (step 1)
2. Continue with detailed findings (step 2)
3. System consults expert model (Gemini Pro or O3) automatically
4. Receive unified review with combined findings
```

#### Pattern: Context Revival After Reset
```
1. User: "Continue debugging the OAuth issue"
2. Use mcp__zen__chat with continuation_id from previous session
3. Model retrieves full context and continues seamlessly
```

#### Pattern: Collaborative Investigation
```
1. Use mcp__zen__debug for systematic investigation
2. Get stuck? Use mcp__zen__consensus for multiple perspectives
3. Solution found? Use mcp__zen__precommit to validate
4. All tools share conversation context automatically
```

#### Pattern: CLI Subagent Delegation
```
1. Complex task detected: "audit entire codebase for security"
2. Use mcp__zen__clink to spawn subagent (Gemini CLI, Codex, etc.)
3. Subagent performs isolated investigation in fresh context
4. Returns final report without polluting main context
5. Continue implementation with subagent's findings
```

### Best Practices

```yaml
Workflow_Completion:
  Rule: Never abandon multi-step workflows
  Action: Complete all steps until next_step_required=false

Context_Provision:
  Rule: Always include relevant files
  Action: Use relevant_files parameter with absolute paths

Model_Matching:
  Rule: Match model to task complexity
  Action: Start with flash, escalate to pro/o3 as needed

Confidence_Tracking:
  Rule: Monitor confidence levels during investigation
  Values: exploring → low → medium → high → very_high → certain

Conversation_Reuse:
  Rule: Leverage continuation_id for related tasks
  Action: Continue previous investigations when relevant
```

### Common Mistakes to Avoid

```yaml
Abandoned_Workflows:
  Problem: Starting workflow and switching tasks
  Solution: Complete all steps until workflow finishes

Relative_Paths:
  Problem: Using ./src/auth.py or ~/project/file.py
  Solution: Always use absolute paths

Missing_Context:
  Problem: Not providing relevant files
  Solution: Include files with relevant_files parameter

Premature_Escalation:
  Problem: Using pro/o3 for simple tasks
  Solution: Start with flash, escalate only when needed

Lost_Context:
  Problem: Not using continuation_id for related work
  Solution: Reuse continuation_id for follow-up investigations
```

### Troubleshooting

```yaml
Session_Expired:
  Error: "Session not found or expired"
  Cause: Sessions expire after 3-6 hours
  Solution: Start new workflow

Model_Unavailable:
  Error: "Model not configured"
  Solution: Run mcp__zen__listmodels to check available models
  Fallback: Use --model auto

File_Not_Found:
  Error: "File not found"
  Cause: Using relative paths
  Solution: Convert to absolute paths

Workflow_Looping:
  Symptom: Same step repeating
  Cause: Not providing investigation RESULTS
  Solution: Include findings parameter with actual discoveries
```

### Quick Reference Commands

```yaml
# Check server status
mcp__zen__version

# List available models
mcp__zen__listmodels

# Quick consultation
mcp__zen__chat:
  prompt: "Validate this approach"
  model: "flash"

# Start debug workflow
mcp__zen__debug:
  step: "Problem description"
  step_number: 1
  model: "gemini-2.5-pro"
  relevant_files: ["/path/to/file.py"]

# Continue workflow
mcp__zen__debug:
  continuation_id: "debug_xxx_yyy"
  step: "Investigation findings"
  step_number: 2

# Multi-model consensus
mcp__zen__consensus:
  prompt: "Decision question"
  models: [{"model": "gemini-pro"}, {"model": "o3"}]

# CLI bridge
mcp__zen__clink:
  cli_name: "gemini"
  role: "planner"
  prompt: "Create implementation plan"
```

### Integration Checklist

```yaml
Setup:
  - [ ] Zen MCP server running
  - [ ] API keys configured
  - [ ] At least one provider available
  - [ ] listmodels shows available models

Configuration:
  - [ ] DISABLED_TOOLS configured (if needed)
  - [ ] DEFAULT_MODEL set (or use auto)
  - [ ] Conversation timeout configured
  - [ ] Log level appropriate

Usage:
  - [ ] Using absolute paths for files
  - [ ] Starting workflows with step_number=1
  - [ ] Continuing with continuation_id
  - [ ] Tracking confidence levels
  - [ ] Completing workflows fully
```

---

## 📚 Additional Resources

**Documentation:**
- Full User Template: `templates/CLAUDE_MD_USER_TEMPLATE.md`
- Quick Start: `templates/CLAUDE_MD_QUICKSTART.md`
- Tool Details: `docs/tools/`
- Configuration: `docs/configuration.md`
- Troubleshooting: `docs/troubleshooting.md`

**Key Concepts:**
- [Conversation Continuity](https://github.com/BeehiveInnovations/zen-mcp-server/blob/main/docs/advanced-usage.md#conversation-continuity)
- [Context Revival](https://github.com/BeehiveInnovations/zen-mcp-server/blob/main/docs/context-revival.md)
- [CLI Bridge (clink)](https://github.com/BeehiveInnovations/zen-mcp-server/blob/main/docs/tools/clink.md)

---

**Template Version:** 2.0 (Global)
**Compatible with:** Zen MCP v5.14.0+
**Last Updated:** 2025-01-14
**Scope:** Global ~/.claude/CLAUDE.md

---

**Note:** This global template provides system-wide patterns. For project-specific integration, also create a CLAUDE.md in your project directory with project-specific rules and contexts.
