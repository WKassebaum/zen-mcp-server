---
name: zen-skill
description: AI orchestration and multi-model collaboration tool for complex tasks, debugging, consensus building, and code analysis through systematic workflows
---

# Zen - AI Orchestration & Multi-Model Collaboration

Zen enables orchestrating multiple AI models for enhanced analysis, consensus building, systematic debugging, and comprehensive code review through structured workflows.

**Available in two forms:**
- **MCP Server** - Tools available as `mcp__zen__*` when server is enabled
- **CLI Program** - Command-line `zen` command, always available

## 🔄 MCP vs CLI: When to Use Which

### Quick Decision Guide

**Use MCP Tools (mcp__zen__*) when:**
- ✅ MCP server is enabled and running
- ✅ Working within Claude Code, Cursor, or MCP-compatible clients
- ✅ Tools show up in your available tools list
- ✅ You want structured tool parameters and responses

**Use CLI (zen command) when:**
- ✅ MCP server is disabled or not available
- ✅ MCP tools don't appear in available tools
- ✅ You need to verify Zen is working
- ✅ Direct command-line access is preferred
- ✅ **ALWAYS check with CLI first if MCP tools fail**

### How to Check Availability

**Test MCP availability:**
```python
# Try to use any mcp__zen__ tool
# If it fails with "tool not found", use CLI instead
mcp__zen__listmodels()
```

**Test CLI availability:**
```bash
# This should always work if Zen is installed
zen listmodels
```

### Syntax Comparison

**MCP Syntax:**
```python
mcp__zen__chat(
    prompt="What is 2+2?",
    model="gemini-2.5-pro",
    working_directory="/path/to/project"
)
```

**CLI Equivalent:**
```bash
zen chat "What is 2+2?" --model gemini-2.5-pro
```

**Key Differences:**
- **MCP**: Structured parameters, typed responses, integrated with IDE
- **CLI**: Command-line flags, text output, works everywhere
- **Both**: Same underlying functionality, same models, same quality

## When to Use Zen

### Auto-Trigger Scenarios

Automatically use Zen MCP when:

- **Low Confidence Decisions** - When confidence < 80% on technical recommendations or architectural choices
- **Complex Debugging** - Stuck on issues for >5 minutes without progress, mysterious errors, or production incidents
- **Architecture Decisions** - Choices affecting >2 components, technology selection, or system design patterns
- **Code Quality Critical** - Before committing significant changes (>100 lines), security-sensitive code, or production deployments
- **Need Validation** - User explicitly asks for "second opinion", "validation", or mentions being uncertain
- **Multi-Model Perspective** - Comparing approaches, evaluating tradeoffs, or making critical technical decisions

### User Requests

Use Zen MCP when user asks to:
- "Get a second opinion on..."
- "What do other models think about..."
- "Help me debug this complex issue..."
- "Review this code thoroughly..."
- "Analyze the architecture of..."
- "Plan out this complex feature..."
- "Find consensus on..."
- "Validate this approach..."

## Available Tools

### 1. Chat - General AI Consultation

**Purpose:** General AI consultation and collaborative thinking for brainstorming, validation, and second opinions

**When to Use:**
- Quick consultations and brainstorming
- Validating approaches before implementation
- Getting second opinions on design decisions
- Exploring alternative solutions
- General questions about technology or patterns

#### MCP Syntax (when server enabled)

**Tool:** `mcp__zen__chat`

**Parameters:**
- `prompt` (required): Question or idea for AI consultation
- `model` (required): AI model to use (e.g., "gemini-2.5-pro", "gpt-5", "o3")
- `working_directory` (required): Absolute directory path for context
- `files` (optional): Absolute file paths for code context
- `images` (optional): Absolute image paths for visual context
- `continuation_id` (optional): Thread ID to continue previous conversation
- `temperature` (optional): 0-1, controls randomness (0=deterministic, 1=creative)
- `thinking_mode` (optional): "minimal", "low", "medium", "high", "max"

**Example:**
```python
mcp__zen__chat(
    prompt="Is using Redis for session storage appropriate for our scale?",
    model="gemini-2.5-pro",
    working_directory="/Users/wrk/project"
)
```

#### CLI Syntax (always available)

**Command:** `zen chat <prompt> [options]`

**Options:**
- `--model <name>` - AI model (default: auto)
- `--files <paths>` or `-f <paths>` - File paths for context (space-separated)
- `--temperature <0-1>` - Response randomness
- `--thinking-mode <level>` - Reasoning depth (minimal/low/medium/high/max)

**Examples:**
```bash
# Simple question
zen chat "Is using Redis for session storage appropriate for our scale?" --model gemini-2.5-pro

# With file context
zen chat "Review this auth implementation" -f src/auth.py -f src/session.py --model o3

# With auto model selection
zen chat "What's 2+2?"  # Uses 'auto' model selection

# Check available models
zen listmodels
```

### 2. `mcp__zen__consensus`
**Purpose:** Multi-model consensus through systematic analysis and structured debate for complex decisions

**Parameters:**
- `step` (required): The proposal/question for models to evaluate
- `step_number` (required): Current step (starts at 1)
- `total_steps` (required): Total steps = number of models consulted
- `next_step_required` (required): True if more consultation needed
- `findings` (required): Summary of current step
- `models` (required): List of {"model": "name", "stance": "for/against/neutral"}
- `relevant_files` (optional): Absolute paths to supporting files
- `continuation_id` (optional): Thread ID for multi-step workflow

**When to Use:**
- Critical architectural decisions
- Technology stack selection
- Comparing multiple viable approaches
- Feature design with significant tradeoffs
- Security or performance critical choices

**Example:**
```python
mcp__zen__consensus(
    step="Should we migrate from REST to GraphQL for our API?",
    step_number=1,
    total_steps=3,
    next_step_required=True,
    findings="Initializing consensus workflow",
    models=[
        {"model": "gemini-2.5-pro", "stance": "neutral"},
        {"model": "gpt-5", "stance": "for"},
        {"model": "o3", "stance": "against"}
    ]
)
```

### 3. `mcp__zen__debug`
**Purpose:** Systematic debugging and root cause analysis with hypothesis testing

**Parameters:**
- `step` (required): Investigation narrative for this step
- `step_number` (required): Current step (starts at 1)
- `total_steps` (required): Estimated steps needed
- `next_step_required` (required): True to continue investigation
- `findings` (required): Discoveries from this step
- `hypothesis` (required): Current theory about root cause
- `confidence` (required): "exploring/low/medium/high/very_high/almost_certain/certain"
- `model` (required): AI model for investigation
- `relevant_files` (optional): Absolute paths to code files
- `files_checked` (optional): All examined files
- `continuation_id` (optional): Thread ID

**When to Use:**
- Stuck debugging for >5-10 minutes
- Mysterious errors or unexpected behavior
- Production incidents requiring systematic investigation
- Complex bugs spanning multiple files
- Race conditions or timing issues

**Example:**
```python
mcp__zen__debug(
    step="OAuth tokens not persisting across requests. Checking session configuration.",
    step_number=1,
    total_steps=3,
    next_step_required=True,
    findings="Session middleware appears configured but cookies not being set",
    hypothesis="Cookie domain or secure flag misconfiguration",
    confidence="medium",
    model="gemini-2.5-pro",
    relevant_files=["/path/to/auth.py", "/path/to/session.py"]
)
```

### 4. `mcp__zen__codereview`
**Purpose:** Systematic code review covering quality, security, performance, and architecture

**Parameters:**
- `step` (required): Review narrative for this step
- `step_number` (required): Current step (starts at 1)
- `total_steps` (required): Number of review steps
- `next_step_required` (required): True to continue review
- `findings` (required): Findings from current step
- `model` (required): AI model for review
- `relevant_files` (required): Absolute paths to files under review
- `review_type` (optional): "full/security/performance/quick"
- `confidence` (required): Current confidence level
- `continuation_id` (optional): Thread ID

**When to Use:**
- Before committing significant changes
- Security-sensitive code (auth, payments, data handling)
- Performance-critical sections
- Before production deployments
- Complex refactoring work

**Example:**
```python
mcp__zen__codereview(
    step="Reviewing authentication implementation for security issues",
    step_number=1,
    total_steps=2,
    next_step_required=True,
    findings="Initializing security review of auth module",
    model="o3",
    relevant_files=["/path/to/auth/*.py"],
    review_type="security",
    confidence="exploring"
)
```

### 5. `mcp__zen__analyze`
**Purpose:** Comprehensive code analysis for architecture, performance, and maintainability assessment

**Parameters:**
- `step` (required): Analysis plan for this step
- `step_number` (required): Current step (starts at 1)
- `total_steps` (required): Estimated analysis steps
- `next_step_required` (required): True to continue analysis
- `findings` (required): Discoveries from current step
- `model` (required): AI model for analysis
- `relevant_files` (required): Absolute paths to files
- `analysis_type` (optional): "architecture/performance/security/quality/general"
- `confidence` (required): Analysis confidence level
- `continuation_id` (optional): Thread ID

**When to Use:**
- Understanding unfamiliar codebases
- Architecture assessment and documentation
- Performance bottleneck identification
- Code quality evaluation
- Technical debt assessment

**Example:**
```python
mcp__zen__analyze(
    step="Analyzing microservices architecture for scalability concerns",
    step_number=1,
    total_steps=2,
    next_step_required=True,
    findings="Starting architecture analysis",
    model="gemini-2.5-pro",
    relevant_files=["/path/to/services/"],
    analysis_type="architecture",
    confidence="exploring"
)
```

### 6. `mcp__zen__planner`
**Purpose:** Sequential task planning with revision and branching for complex projects

**Parameters:**
- `step` (required): Planning content for this step
- `step_number` (required): Current step (starts at 1)
- `total_steps` (required): Estimated planning steps
- `next_step_required` (required): True to continue planning
- `model` (required): AI model for planning
- `continuation_id` (optional): Thread ID

**When to Use:**
- Complex multi-step features
- Migration strategies
- System design planning
- Refactoring large codebases
- Project breakdown for teams

**Example:**
```python
mcp__zen__planner(
    step="Planning migration from MongoDB to PostgreSQL",
    step_number=1,
    total_steps=1,
    next_step_required=False,
    model="gemini-2.5-pro"
)
```

### 7. `mcp__zen__thinkdeep`
**Purpose:** Multi-stage investigation and reasoning for complex problem analysis

**Parameters:**
- `step` (required): Current work step content
- `step_number` (required): Current step (starts at 1)
- `total_steps` (required): Estimated steps
- `next_step_required` (required): True to continue
- `findings` (required): Important discoveries
- `model` (required): AI model
- `relevant_files` (optional): Absolute file paths
- `confidence` (required): Confidence level
- `continuation_id` (optional): Thread ID

**When to Use:**
- Deep technical investigations
- Complex performance problems
- Architectural deep dives
- Multi-layered debugging

**Example:**
```python
mcp__zen__thinkdeep(
    step="Investigating memory leak in production API",
    step_number=1,
    total_steps=3,
    next_step_required=True,
    findings="Memory usage grows steadily under load",
    model="o3",
    confidence="exploring"
)
```

### 8. `mcp__zen__refactor`
**Purpose:** Refactoring analysis for code smells, decomposition, and modernization

**Parameters:**
- `step` (required): Refactoring plan
- `step_number` (required): Current step
- `total_steps` (required): Estimated steps
- `next_step_required` (required): Continue flag
- `findings` (required): Refactoring opportunities found
- `model` (required): AI model
- `refactor_type` (optional): "codesmells/decompose/modernize/organization"
- `confidence` (required): "exploring/incomplete/partial/complete"

**When to Use:**
- Code smell detection
- Breaking down large functions/classes
- Modernizing legacy code
- Improving code organization

### 9. `mcp__zen__testgen`
**Purpose:** Test generation with edge case coverage for functions, classes, modules

**Parameters:**
- `step` (required): Test plan content
- `step_number` (required): Current step
- `total_steps` (required): Estimated steps
- `next_step_required` (required): Continue flag
- `findings` (required): Test scenarios identified
- `model` (required): AI model

**When to Use:**
- Generating comprehensive test suites
- Edge case identification
- Test coverage improvement
- Framework-specific test creation

### 10. `mcp__zen__precommit`
**Purpose:** Pre-commit validation and quality checks for git changes

**Parameters:**
- `step` (required): Validation plan
- `step_number` (required): Current step
- `total_steps` (required): Estimated steps
- `next_step_required` (required): Continue flag
- `findings` (required): Validation results
- `model` (required): AI model
- `path` (required): Repository root path
- `confidence` (required): Validation confidence

**When to Use:**
- Before committing significant changes
- Multi-repository validation
- Change impact assessment
- Security review of commits

### 11. `mcp__zen__secaudit`
**Purpose:** Security audit with OWASP Top 10 analysis and compliance evaluation

**Parameters:**
- `step` (required): Audit plan
- `step_number` (required): Current step
- `total_steps` (required): Estimated steps
- `next_step_required` (required): Continue flag
- `findings` (required): Security findings
- `model` (required): AI model
- `audit_focus` (optional): "owasp/compliance/infrastructure/dependencies"

**When to Use:**
- Security audits before production
- Compliance evaluation (SOC2, HIPAA, GDPR)
- Vulnerability assessment
- Threat modeling

### 12. `mcp__zen__tracer`
**Purpose:** Code tracing for execution flow or dependency mapping

**Parameters:**
- `step` (required): Tracing work step
- `step_number` (required): Current step
- `total_steps` (required): Estimated steps
- `next_step_required` (required): Continue flag
- `findings` (required): Trace discoveries
- `model` (required): AI model
- `target_description` (required): What to trace and why
- `trace_mode` (required): "precision/dependencies/ask"

**When to Use:**
- Understanding execution flow
- Dependency mapping
- Call chain analysis
- Performance profiling paths

### 13. `mcp__zen__clink`
**Purpose:** CLI-to-CLI bridge for spawning external AI CLIs as subagents

**Parameters:**
- `prompt` (required): Request for the CLI
- `cli_name` (required): CLI client name ("claude", "codex", "gemini")
- `role` (optional): Role preset ("default", "planner", "codereviewer")
- `files` (optional): Absolute file paths
- `images` (optional): Absolute image paths
- `continuation_id` (optional): Thread ID

**When to Use:**
- Delegating tasks to specialized CLIs
- Fresh context for subtasks
- Leveraging CLI-specific capabilities

### 14. `mcp__zen__listmodels`
**Purpose:** List available AI models with capabilities and configuration

**Parameters:** None

**When to Use:**
- Check available models
- Understand model capabilities
- Verify model configuration
- Debug model selection issues

### 15. `mcp__zen__challenge`
**Purpose:** Prevent reflexive agreement by forcing critical thinking when statements are questioned

**Parameters:**
- `prompt` (required): Statement to scrutinize

**When to Use:**
- User critically questions previous answers
- User disagrees or pushes back
- Sanity-check contentious claims
- Force deeper reasoning on uncertain claims

## 🖥️ CLI Quick Reference

**When MCP is unavailable**, use the `zen` command-line interface. All MCP tools have CLI equivalents.

### Essential CLI Commands

#### Check Available Models
```bash
# List all configured models and providers
zen listmodels

# Test if zen is working
zen chat "test" --model auto
```

#### Chat - General Consultation
```bash
# Simple question
zen chat "What is 2+2?" --model gemini-2.5-pro

# With file context
zen chat "Review this code" -f src/app.py -f src/utils.py

# With auto model selection
zen chat "Is Redis appropriate for sessions?"
```

#### Debug - Systematic Investigation
**Note:** CLI debug uses natural language prompts rather than structured workflow parameters

```bash
# Start debugging session
zen debug "OAuth tokens not persisting" -f src/auth.py -f src/session.py --model gemini-2.5-pro

# The CLI will guide you through systematic investigation
# Follow prompts to provide findings and update hypothesis
```

#### Consensus - Multi-Model Decision
```bash
# Get consensus from multiple models
zen consensus "Should we use GraphQL or REST?" --models gemini-2.5-pro,gpt-5,o3

# With file context
zen consensus "Best architecture for this codebase?" -f docs/requirements.md -f src/
```

#### Code Review
```bash
# Review specific files
zen codereview -f src/auth.py -f src/session.py --model o3

# Security-focused review
zen codereview -f src/payment/ --review-type security

# Quick review
zen codereview -f src/utils.py --review-type quick
```

#### Analyze - Architecture & Code Analysis
```bash
# Analyze codebase architecture
zen analyze -f src/ --analysis-type architecture --model gemini-2.5-pro

# Performance analysis
zen analyze -f src/api/ --analysis-type performance

# General analysis
zen analyze -f src/core/
```

#### Planner - Task Breakdown
```bash
# Create implementation plan
zen planner "Migrate from MongoDB to PostgreSQL" --model gemini-2.5-pro

# With context files
zen planner "Add OAuth support" -f docs/requirements.md
```

### CLI vs MCP Mapping

| MCP Tool | CLI Command | Notes |
|----------|-------------|-------|
| `mcp__zen__chat` | `zen chat` | Direct 1:1 mapping |
| `mcp__zen__consensus` | `zen consensus` | Specify models with `--models` |
| `mcp__zen__debug` | `zen debug` | Interactive workflow |
| `mcp__zen__codereview` | `zen codereview` | Use `--review-type` |
| `mcp__zen__analyze` | `zen analyze` | Use `--analysis-type` |
| `mcp__zen__planner` | `zen planner` | Direct mapping |
| `mcp__zen__thinkdeep` | `zen thinkdeep` | Deep investigation |
| `mcp__zen__refactor` | `zen refactor` | Code improvement |
| `mcp__zen__testgen` | `zen testgen` | Test generation |
| `mcp__zen__precommit` | `zen precommit` | Git validation |
| `mcp__zen__secaudit` | `zen secaudit` | Security audit |
| `mcp__zen__tracer` | `zen tracer` | Code tracing |
| `mcp__zen__clink` | `zen clink` | CLI bridging |
| `mcp__zen__listmodels` | `zen listmodels` | Model listing |

### Common CLI Patterns

**Check if Zen is working:**
```bash
zen listmodels        # Should list available models
zen chat "test"       # Should respond
```

**Get help:**
```bash
zen --help            # General help
zen chat --help       # Command-specific help
zen listmodels        # See available models
```

**File context:**
```bash
# Single file
zen chat "Review this" -f src/app.py

# Multiple files
zen chat "Review these" -f src/app.py -f src/utils.py -f src/config.py

# Directory (expands to all files)
zen analyze -f src/
```

**Model selection:**
```bash
# Auto selection (recommended)
zen chat "question"

# Specific model
zen chat "question" --model gemini-2.5-pro

# Fast model for quick queries
zen chat "quick question" --model gemini-2.5-flash

# Advanced reasoning
zen debug "complex issue" --model o3
```

### When to Use CLI

**✅ Always use CLI when:**
- MCP server is disabled or not configured
- MCP tools show as "not available"
- You need to quickly test if Zen is working
- Running from terminal/shell scripts
- Debugging Zen installation issues

**Example diagnostic workflow:**
```bash
# 1. Check if zen command works
zen listmodels

# 2. If zen works but MCP doesn't, use CLI
zen chat "Is Redis good for sessions?" --model gemini-2.5-pro

# 3. If you get model errors, check configuration
cat ~/.config/zen/config.yaml   # or wherever your config is
env | grep API_KEY               # Check for API keys
```

## Best Practices

### Pattern 1: Progressive Investigation

For complex issues, start with lighter tools and escalate as needed:

1. **Quick consultation** - Use `chat` for initial validation
2. **Systematic debugging** - Use `debug` if issue is complex
3. **Deep investigation** - Use `thinkdeep` for multi-layered problems
4. **Validation** - Use `consensus` if solution is uncertain

### Pattern 2: Code Quality Workflow

Before committing significant changes:

1. **Refactor analysis** - Use `refactor` to identify improvements
2. **Code review** - Use `codereview` for comprehensive review
3. **Pre-commit validation** - Use `precommit` for change assessment
4. **Test generation** - Use `testgen` for coverage

### Pattern 3: Architecture Decisions

For major architectural choices:

1. **Analysis** - Use `analyze` to understand current architecture
2. **Consultation** - Use `chat` for initial exploration
3. **Consensus** - Use `consensus` with multiple models for final decision
4. **Planning** - Use `planner` to break down implementation

### Pattern 4: Model Selection

Choose models based on task requirements:

- **gemini-2.5-pro** - Deep analysis, complex reasoning, large context
- **gpt-5** - Strong logical reasoning, code generation
- **o3** - Precision reasoning, mathematical thinking
- **gemini-2.5-flash** - Fast responses, quick consultations
- **gpt-4o-mini** - Lightweight tasks, rapid iteration

### Pattern 5: File Context Management

Always provide relevant file context:

- Use absolute paths (not relative)
- Include related files for comprehensive understanding
- Avoid dumping large file contents - let tools read them
- Provide context about why files are relevant

## Common Patterns

### Pattern: Stuck on Complex Bug

1. **Initial investigation** - Use `debug` with low confidence
2. **File examination** - Provide relevant files as investigation progresses
3. **Hypothesis testing** - Update hypothesis and confidence as evidence emerges
4. **Validation** - Use `consensus` if root cause is unclear
5. **Implementation** - Apply fix and verify

### Pattern: Major Feature Planning

1. **Requirements gathering** - Use `chat` to explore approaches
2. **Planning** - Use `planner` to break down work
3. **Architecture** - Use `analyze` to assess impact on existing code
4. **Validation** - Use `consensus` for critical design decisions
5. **Test planning** - Use `testgen` to plan test coverage

### Pattern: Security-Critical Changes

1. **Code review** - Use `codereview` with type="security"
2. **Security audit** - Use `secaudit` for comprehensive analysis
3. **Consensus** - Use `consensus` for critical security decisions
4. **Pre-commit** - Use `precommit` before committing changes

## Troubleshooting

### Issue 1: Model Not Available

**Symptoms:** Error "Model not found" or "Provider not configured"

**Solution:**
1. Use `listmodels` to check available models
2. Verify API keys are configured in environment
3. Check model name spelling (case-sensitive)
4. Try alternative model from same provider

### Issue 2: Workflow Not Completing

**Symptoms:** Tool returns but doesn't provide final answer

**Solution:**
1. Check `next_step_required` - if True, continue workflow
2. Use `continuation_id` to resume multi-step workflows
3. Set confidence appropriately (don't use "certain" prematurely)
4. Ensure all required fields are provided

### Issue 3: Poor Quality Results

**Symptoms:** Generic or unhelpful responses

**Solution:**
1. Provide more specific context in prompts
2. Include relevant files for code-related tasks
3. Try higher-capability model (e.g., gemini-2.5-pro vs flash)
4. Break complex tasks into smaller steps
5. Use appropriate thinking_mode (higher for complex tasks)

### Issue 4: Token Limits Exceeded

**Symptoms:** Error about context length

**Solution:**
1. Reduce number of files provided
2. Focus on specific relevant sections
3. Use continuation_id to manage conversation state
4. Consider model with larger context (gemini-2.5-pro has 1M tokens)

## Integration with Development Workflow

### During Development

- **Design phase** - Use `chat` and `planner` for exploration
- **Implementation** - Use `debug` when stuck, `refactor` for quality
- **Testing** - Use `testgen` for comprehensive coverage
- **Review** - Use `codereview` before commits

### Before Commits

- **Quality check** - Use `refactor` and `codereview`
- **Validation** - Use `precommit` for change assessment
- **Security** - Use `secaudit` for sensitive changes

### For Investigations

- **Understanding code** - Use `analyze` and `tracer`
- **Finding issues** - Use `debug` and `thinkdeep`
- **Architecture** - Use `analyze` for structural assessment

### For Decision Making

- **Quick decisions** - Use `chat` for consultation
- **Critical decisions** - Use `consensus` with multiple models
- **Planning** - Use `planner` for complex work breakdown

---

**Remember:** Zen MCP excels at systematic, multi-step workflows. Start with appropriate confidence levels, provide relevant context, and let workflows progress naturally. Use continuation_id to maintain context across multiple interactions.
