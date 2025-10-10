# Planner Tool - Interactive Step-by-Step Planning

**Break down complex projects into manageable, structured plans through step-by-step thinking**

The `planner` tool helps you break down complex ideas, problems, or projects into multiple manageable steps. Perfect for system design, migration strategies,
architectural planning, and feature development with session-based workflow continuation.

## 🆕 Session-Based Workflow (CLI)

The planner now supports **session-based workflow continuation** in CLI mode, enabling multi-step planning across multiple invocations:

**Start New Plan:**
```bash
zen planner "Add user authentication to web app" --model flash
```

**Continue Plan:**
```bash
zen planner --session planner_1760065815_42s8544v --continue "Found existing user model with email/password fields"
```

### How It Works

The planner tool enables step-by-step thinking with session continuity:

1. **Start Planning**: Describe the task or problem to plan
2. **Session Created**: Auto-generated session ID with 3-hour TTL
3. **Investigation Steps**: Tool provides systematic investigation steps
4. **Continue Planning**: Provide findings and continue to next step
5. **Plan Completion**: Workflow completes when all steps finished
6. **Auto-Cleanup**: Session deleted on completion or expiration

## Example Prompts

#### Pro Tip
Claude supports `sub-tasks` where it will spawn and run separate background tasks. You can ask Claude to 
run Zen's planner with two separate ideas. Then when it's done, use Zen's `consensus` tool to pass the entire
plan and get expert perspective from two powerful AI models on which one to work on first! Like performing **AB** testing
in one-go without the wait!

```
Create two separate sub-tasks: in one, using planner tool show me how to add natural language support 
to my cooking app. In the other sub-task, use planner to plan how to add support for voice notes to my cooking app. 
Once done, start a consensus by sharing both plans to o3 and flash to give me the final verdict. Which one do 
I implement first?
```

```
Use zen's planner and show me how to add real-time notifications to our mobile app
```

```
Using the planner tool, show me how to add CoreData sync to my app, include any sub-steps
```

## Key Features

- **Step-by-step breakdown**: Build plans incrementally with full context awareness
- **Branching support**: Explore alternative approaches when needed  
- **Revision capabilities**: Update earlier decisions as new insights emerge
- **Multi-session continuation**: Resume planning across multiple sessions with context
- **Dynamic adjustment**: Modify step count and approach as planning progresses
- **Visual presentation**: ASCII charts, diagrams, and structured formatting
- **Professional output**: Clean, structured plans without emojis or time estimates

## More Examples

```
Using planner, plan the architecture for a new real-time chat system with 100k concurrent users
```

```
Create a plan using zen for migrating our React app from JavaScript to TypeScript
```

```
Develop a plan using zen for implementing CI/CD pipelines across our development teams
```

## Best Practices

- **Start broad, then narrow**: Begin with high-level strategy, then add implementation details
- **Include constraints**: Consider technical, organizational, and resource limitations
- **Plan for validation**: Include testing and verification steps
- **Think about dependencies**: Identify what needs to happen before each step
- **Consider alternatives**: Note when multiple approaches are viable
- **Enable continuation**: Use continuation_id for multi-session planning

## Continue With a New Plan

Like all other tools in Zen, you can `continue` with a new plan using the output from a previous plan by simply saying

```
Continue with zen's consensus tool and find out what o3:for and flash:against think of the plan
```

You can mix and match and take one output and feed it into another, continuing from where you left off using a different
tool / model combination.

## CLI Usage Reference

### Command Syntax

**Start new planning workflow:**
```bash
zen planner "Goal description" [OPTIONS]
```

**Continue existing workflow:**
```bash
zen planner --session <session_id> --continue "Your investigation findings" [OPTIONS]
```

### Options

- `--session, -s`: Session ID for continuing workflow (auto-generated if not provided)
- `--continue`: Investigation findings/results to continue workflow
- `--model, -m`: AI model to use (flash, gemini-pro, o3, auto)
- `--context-files, -f`: Additional context files to include
- `--json`: Output as JSON instead of formatted text

### Examples

**Simple Planning:**
```bash
zen planner "Add OAuth integration to API" --model flash
```

**With Context Files:**
```bash
zen planner "Refactor authentication system" --context-files auth.py session.py
```

**Continue Planning:**
```bash
zen planner --session planner_xxx --continue "Analyzed auth.py - found JWT implementation with 3 endpoints"
```

### Claude Code Integration

When Claude Code uses the planner tool, it automatically:

1. Starts workflow with initial goal
2. Receives investigation step with continuation command
3. Performs investigation (reads files, analyzes code)
4. Calls continuation command with findings
5. Repeats until planning complete

**Response Format:**
```json
{
  "session_id": "planner_1760065815_42s8544v",
  "step_number": 2,
  "total_steps": 5,
  "workflow_status": "in_progress",
  "continuation_command": "zen planner --session <id> --continue '<findings>'",
  "workflow_instructions": {
    "for_claude_code": "MANDATORY: Perform investigation then continue...",
    "for_manual_users": "To continue: Run continuation command..."
  }
}
```

### Session Management

- **TTL**: 3 hours from last activity
- **Auto-Cleanup**: Sessions deleted on completion
- **Storage**: Persisted in configured storage backend (File/Redis/Memory)
- **State Tracking**: Findings, files_checked, confidence carried forward

### Troubleshooting

**Session Expired:**
```
Error: Session 'planner_xxx' not found or expired (TTL: 3 hours)
```
Solution: Start new planning workflow

**Missing Goal:**
```
Error: Goal required for new workflow
```
Solution: Provide goal description for new workflow, or use --session/--continue for continuation

---

**See Also:**
- [Session-Based Workflows](../advanced-usage.md#session-based-workflows)
- [Claude Code Integration](../../CLAUDE_CODE_INTEGRATION.md)
- [All WorkflowTools](../index.md#workflow-tools)