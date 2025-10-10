# Zen CLI Integration for Claude Code

**Add this template to your project's CLAUDE.md file to enable Claude Code to use Zen CLI WorkflowTools**

---

## 🧠 Zen CLI - AI Workflow Tools Integration

### Overview

Zen CLI provides 9 powerful WorkflowTools that enable multi-step AI-assisted workflows with session continuity. These tools are designed to work seamlessly with Claude Code through session-based workflow management.

### Available WorkflowTools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| **planner** | Sequential task planning | Breaking down complex features/projects |
| **analyze** | Architecture assessment | Understanding codebase structure and patterns |
| **thinkdeep** | Extended reasoning | Complex architectural decisions requiring deep analysis |
| **precommit** | Pre-commit validation | Quality checks before committing code |
| **testgen** | Test generation | Creating comprehensive test suites |
| **secaudit** | Security auditing | Finding vulnerabilities and security issues |
| **refactor** | Refactoring suggestions | Improving code quality and maintainability |
| **docgen** | Documentation generation | Creating comprehensive documentation |
| **tracer** | Code flow tracing | Understanding execution paths and dependencies |

### How Session-Based Workflows Work

**Step 1 - Start Workflow:**
```bash
zen planner "Add user authentication to web app" --model flash
```

Response includes:
- Session ID (e.g., `planner_1760065815_42s8544v`)
- Investigation step to perform
- Continuation command with embedded instructions

**Step 2+ - Continue Workflow:**
```bash
zen planner --session planner_1760065815_42s8544v --continue "Found existing user model with email/password fields"
```

Workflow continues until completion (`next_step_required = false`)

### Auto-Trigger Patterns for Claude Code

**MANDATORY**: When you see a tool response with `workflow_status: "in_progress"`, you MUST:
1. Perform the investigation/work described in the step content
2. Call the exact `continuation_command` provided in the response
3. Replace `<your findings here>` with your actual investigation results
4. Do NOT proceed with other tasks until workflow is complete

### Usage Patterns

#### Pattern 1: Planning & Breakdown
```
User: "I need to add user authentication to my app"
Claude: Uses zen planner to create systematic plan
  1. Calls: zen planner "Add user authentication" --model flash
  2. Receives step 1: "Investigate existing user models"
  3. Reads relevant files, gathers context
  4. Calls: zen planner --session <id> --continue "Found User model with..."
  5. Repeats until plan is complete
```

#### Pattern 2: Code Analysis
```
User: "Help me understand the authentication flow"
Claude: Uses zen analyze for systematic analysis
  1. Calls: zen analyze "Understand authentication flow" --files src/auth/*.py
  2. Receives investigation step
  3. Performs code reading and analysis
  4. Calls: zen analyze --session <id> --continue "JWT implementation in auth.py..."
  5. Continues until analysis complete
```

#### Pattern 3: Security Review
```
User: "Check this code for security issues"
Claude: Uses zen secaudit for comprehensive audit
  1. Calls: zen secaudit "Audit for vulnerabilities" --files auth.py payment.py
  2. Receives security investigation step
  3. Performs security analysis
  4. Calls: zen secaudit --session <id> --continue "Found SQL injection risk..."
  5. Continues until audit complete
```

### Integration Guidelines

**When to Use WorkflowTools:**
- Complex tasks requiring systematic investigation (3+ steps)
- Code quality assessment and refactoring
- Architecture analysis and planning
- Security audits and vulnerability detection
- Test generation and documentation

**Model Selection:**
- `flash` - Fast responses for straightforward tasks
- `gemini-pro` - Deep analysis and complex reasoning
- `o3` - Strong logical reasoning and precision
- `auto` - Let Zen choose optimal model (default)

**Session Management:**
- Sessions auto-expire after 3 hours
- Sessions auto-delete on workflow completion
- Multiple concurrent sessions supported
- Session state persists in configured storage backend

### Example Workflows

**Full Feature Implementation:**
```bash
# 1. Plan the feature
zen planner "Add OAuth integration" --model gemini-pro
# Continue with investigation steps until plan complete

# 2. Analyze existing auth code
zen analyze "Understand current authentication" --files src/auth/*.py
# Continue with code analysis until complete

# 3. Generate tests
zen testgen "Create OAuth tests" --files src/oauth.py --framework pytest
# Continue with test generation until complete

# 4. Security audit
zen secaudit "Audit OAuth implementation" --files src/oauth.py --focus auth
# Continue with security review until complete

# 5. Pre-commit check
zen precommit "Validate OAuth changes" --files src/oauth.py src/auth/*.py
# Continue with validation until complete
```

### Best Practices

1. **Always Complete Workflows**: Don't abandon workflows mid-step
2. **Provide Detailed Findings**: When continuing, give comprehensive investigation results
3. **Use Appropriate Models**: Choose models based on task complexity
4. **Include Relevant Files**: Specify `--files` to provide context
5. **Follow Continuation Instructions**: Parse and execute `continuation_command` exactly

### Response Format

WorkflowTools return structured JSON with:
```json
{
  "session_id": "planner_1760065815_42s8544v",
  "step_number": 1,
  "total_steps": 5,
  "workflow_status": "in_progress",
  "next_step_required": true,
  "continuation_command": "zen planner --session <id> --continue '<findings>'",
  "workflow_instructions": {
    "for_claude_code": "MANDATORY WORKFLOW CONTINUATION...",
    "for_manual_users": "To continue this workflow..."
  },
  "content": "Investigation step details...",
  "findings": "Accumulated findings from previous steps..."
}
```

### Troubleshooting

**Session Expired:**
- Sessions expire after 3 hours of inactivity
- Error message: "Session 'xxx' not found or expired"
- Solution: Start new workflow

**Workflow Stuck:**
- Ensure you're providing investigation results, not repeating the prompt
- Check that you're using the exact session ID from the response
- Verify continuation command syntax

**Model Not Available:**
- Check available models: `zen listmodels`
- Use `--model auto` to let Zen choose
- Fallback to `flash` or `gemini-pro` if specific model unavailable

---

## Quick Reference

**Start Workflow:**
```bash
zen <tool> "Goal/Question" [--files *.py] [--model flash]
```

**Continue Workflow:**
```bash
zen <tool> --session <session_id> --continue "Your investigation results"
```

**Get Help:**
```bash
zen <tool> --help
```

**List Available Models:**
```bash
zen listmodels
```

---

**Template Version:** 1.0
**Compatible with:** Zen CLI v5.14.0+
**Last Updated:** 2025-10-09
