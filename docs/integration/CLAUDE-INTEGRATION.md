# Claude Code Integration Guide for Zen CLI

This guide helps Claude Code users effectively integrate and use the Zen CLI tool for AI-powered development assistance.

## Overview

Zen CLI provides standalone AI-powered development tools with 95% token optimization through a two-stage architecture. It offers intelligent code analysis, debugging, security audits, and more without requiring an MCP server.

## Installation & Setup

```bash
# Install via pix (recommended)
pix install zen-cli

# Or install via pip with user packages (macOS PEP 668)
pip3 install --user --break-system-packages zen-cli

# Set required environment variables
export GEMINI_API_KEY="your_actual_gemini_api_key"
export OPENAI_API_KEY="your_actual_openai_api_key"
export XAI_API_KEY="your_xai_api_key"  # Optional for Grok models

# Verify installation
zen --version
zen listmodels
```

## When to Use Zen CLI

### High-Value Scenarios
- **Complex debugging** requiring systematic investigation
- **Architecture decisions** needing multi-model consensus
- **Security audits** for authentication, encryption, or API security
- **Code review** with expert-level analysis
- **Performance optimization** and bottleneck identification
- **Test generation** with comprehensive edge case coverage

### Integration Patterns with Claude Code

#### Pattern 1: Complex Multi-Step Tasks
When Claude Code encounters complex tasks requiring specialized expertise:

```bash
# Instead of Claude doing everything directly
# Delegate complex debugging to Zen CLI
zen debug "OAuth tokens not persisting across requests" --files auth.py session.py

# Get architectural consensus
zen consensus "Should we use microservices or monolith for this project?"

# Comprehensive security review
zen secaudit --files src/auth/ src/api/
```

#### Pattern 2: Second Opinion & Validation
When Claude Code needs validation on critical decisions:

```bash
# Validate approach before implementation
zen chat "Review this database migration strategy: [details]"

# Get consensus on technical decisions
zen consensus "Evaluate React vs Vue for this project"

# Security validation
zen secaudit "Review this JWT implementation for vulnerabilities"
```

## Core Commands & Usage

### Essential Commands
```bash
# List available AI models
zen listmodels

# Interactive chat with AI
zen chat "Explain microservices architecture"

# Debug specific issues
zen debug "Memory leak in Node.js app" --files server.js utils.js

# Code review with expert analysis  
zen codereview --files src/*.py

# Security audit
zen secaudit --files auth/ api/

# Generate comprehensive tests
zen testgen --files mymodule.py

# Get multi-model consensus
zen consensus "Best database for high-throughput analytics"

# Analyze code architecture
zen analyze --files src/

# Refactoring recommendations
zen refactor --files legacy_code.py
```

### Advanced Commands
```bash
# Sequential task planning
zen planner "Implement user authentication system"

# Code execution tracing
zen tracer --files complex_algorithm.py

# Pre-commit analysis
zen precommit --files modified_files.py

# Deep analysis and investigation
zen thinkdeep "Why is this distributed system experiencing cascading failures"
```

## Model Selection Strategy

### Automatic Model Selection
```bash
# Use "auto" for intelligent model routing
zen chat "Complex coding question" --model auto
zen debug "Hard to debug issue" --model auto
```

### Preferred Models by Task Type
- **Fast Coding Questions**: `grok-code-fast-1` (newest XAI model - very fast, cheap, smart)
- **Complex Reasoning**: `gpt-4o`, `claude-3-5-sonnet-20241022`
- **Extended Analysis**: `grok-4`, `gpt-5` (when available)
- **Balanced Tasks**: `gemini-2.0-flash-exp`, `grok-code-fast-1`

### Manual Model Selection
```bash
# Use specific models for specialized tasks
zen debug "Complex issue" --model grok-code-fast-1
zen consensus "Architecture decision" --model gpt-4o
zen secaudit "Security review" --model claude-3-5-sonnet-20241022
```

## Conversation Persistence & Sessions

### Auto-Session Management
Zen CLI automatically creates and tracks conversation sessions using idempotent identity based on:
- Current working directory
- Git repository state (if available)  
- Time window (hourly buckets)

```bash
# Sessions are automatically managed - no manual setup needed
zen chat "Start working on authentication"
zen debug "OAuth issue" # Continues previous conversation context
zen codereview --files auth.py # Maintains session context
```

### Manual Session Management
```bash
# List active sessions
zen sessions list

# Continue specific session
zen chat "Continue discussion" --session session_id

# Create named session
zen chat "New feature discussion" --session feature_x_planning
```

### Session Storage
- **Default**: File-based storage in `~/.zen-cli/conversations/`
- **Optional**: Redis support (configure in `~/.zen-cli/config.json`)
- **Persistence**: Conversations persist across CLI invocations
- **TTL**: Configurable expiration (default: 3 hours)

## Integration with Claude Code

### Proactive Usage Patterns

#### Code Analysis & Review
```yaml
# When Claude Code encounters large codebases
Claude: "This is a complex codebase. Let me get expert analysis."
Action: zen analyze --files src/

# Before major refactoring
Claude: "Let me get a second opinion on this refactoring approach."
Action: zen refactor --files legacy_system/
```

#### Debugging Assistance
```yaml  
# When stuck on complex bugs
Claude: "This requires systematic debugging. Let me delegate to Zen CLI."
Action: zen debug "Intermittent authentication failures" --files auth/ session/

# For performance issues
Claude: "Let me get specialized performance analysis."
Action: zen analyze --performance --files slow_module.py
```

#### Architecture & Design Decisions
```yaml
# For architectural choices
Claude: "This is a critical architecture decision. Getting expert consensus."
Action: zen consensus "Evaluate event-driven vs request-response architecture"

# For security-critical implementations
Claude: "Security is crucial here. Running comprehensive audit."
Action: zen secaudit --files payment_processing/
```

### Token Optimization Strategy

Zen CLI uses a two-stage architecture for 95% token reduction:
1. **Stage 1**: Quick analysis and mode selection (200 tokens)
2. **Stage 2**: Focused execution with optimized context (600-800 tokens)

This makes it ideal for:
- Complex analysis that would consume many tokens in Claude Code
- Multi-step investigations requiring sustained context
- Expert-level review and validation

## Troubleshooting

### Common Issues & Solutions

#### Command Not Found
```bash
# Check installation path
which zen

# Add to PATH if needed (macOS)
export PATH="$PATH:$HOME/Library/Python/3.13/bin"
```

#### API Key Issues  
```bash
# Verify API keys are set
echo $GEMINI_API_KEY
echo $OPENAI_API_KEY

# Test with specific provider
zen listmodels --provider gemini
```

#### Model Resolution Errors
```bash
# Check available models
zen listmodels

# Use specific model instead of "auto"
zen chat "test" --model grok-code-fast-1
```

#### Storage/Session Issues
```bash
# Check storage directory
ls ~/.zen-cli/conversations/

# Clear sessions if needed
rm -rf ~/.zen-cli/conversations/
```

### Debug Mode
```bash
# Enable debug output for troubleshooting
ZENLOGIC_DEBUG=1 zen chat "test message"
```

## Example Workflows

### Full-Stack Development Cycle
```bash
# 1. Architecture planning
zen planner "Build customer portal with authentication"

# 2. Security review of design
zen secaudit "Review authentication flow design"

# 3. Implementation guidance
zen chat "Best practices for JWT implementation"

# 4. Code review during development
zen codereview --files auth_service.py

# 5. Testing strategy
zen testgen --files auth_service.py

# 6. Performance analysis
zen analyze --performance --files auth_service.py

# 7. Pre-commit validation  
zen precommit --files auth_service.py
```

### Debugging Workflow
```bash
# 1. Initial investigation
zen debug "API returns 500 errors intermittently" --files api_handler.py

# 2. Code tracing
zen tracer --files api_handler.py database.py

# 3. Get second opinion
zen chat "Analyze this error pattern: [paste logs]"

# 4. Validation of fix
zen codereview --files fixed_api_handler.py
```

### Architecture Review Process
```bash
# 1. Current state analysis
zen analyze --files src/

# 2. Multi-model consensus on changes
zen consensus "Should we adopt microservices architecture?"

# 3. Deep investigation of implications
zen thinkdeep "Impact of migrating from monolith to microservices"

# 4. Security implications
zen secaudit "Security considerations for microservices"
```

## Best Practices

### When to Use Each Tool
- **chat**: General questions, explanations, guidance
- **debug**: Specific bugs or issues with code context  
- **codereview**: Quality assessment of code changes
- **consensus**: Important decisions needing validation
- **secaudit**: Security-critical code or designs
- **analyze**: Understanding complex codebases or architecture
- **testgen**: Comprehensive test coverage
- **planner**: Breaking down complex tasks
- **thinkdeep**: Deep investigation of complex problems

### Effective Usage Patterns
1. **Provide Context**: Include relevant files with `--files` flag
2. **Be Specific**: Clear problem descriptions get better results
3. **Use Sessions**: Let auto-sessions maintain context across related tasks
4. **Combine Tools**: Use analyze → debug → codereview workflows
5. **Validate Decisions**: Use consensus for important choices

### Performance Tips
- Use `auto` model selection for intelligent routing
- Leverage sessions to avoid repeating context
- Combine multiple questions in single commands when related
- Use file-based storage for persistence across work sessions

---

## Configuration

### Config File Location
`~/.zen-cli/config.json`

### Example Configuration
```json
{
  "storage": {
    "type": "file",
    "cleanup_interval_hours": 24
  },
  "models": {
    "default_provider": "auto",
    "preferred_fast": "grok-code-fast-1",
    "preferred_reasoning": "gpt-4o"
  },
  "session": {
    "timeout_hours": 3,
    "auto_create": true
  }
}
```

---

*This integration guide ensures Claude Code users can effectively leverage Zen CLI for enhanced AI-powered development assistance while maintaining optimal performance and user experience.*