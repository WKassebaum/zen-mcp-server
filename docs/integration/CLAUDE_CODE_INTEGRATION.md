# Zen CLI Integration for Claude Code

Add this section to your global `~/.claude/CLAUDE.md` file to enable automatic Zen CLI usage during development sessions.

## Installation Check

First ensure Zen CLI is installed and accessible:
```bash
# Check if zen is available
which zen
zen --version

# If not installed:
pipx install git+https://github.com/WKassebaum/zen-mcp-server.git@v2.0
```

## Integration Template

Add this section to your `~/.claude/CLAUDE.md`:

```markdown
## 🧠 Zen CLI Integration

### Auto-Trigger Patterns

You have access to the Zen CLI tool via Bash. Use it automatically when encountering:

**Low Confidence Situations** - When confidence < high on critical decisions:
```bash
zen consensus "Should we use microservices or monolith for this e-commerce platform?" --models gemini-pro,o3
```

**Complex Debugging** - When stuck on difficult bugs:
```bash
zen debug "OAuth tokens not persisting across sessions" -f src/auth.py -f src/session.py --confidence exploring
```

**Architecture Decisions** - For important architectural choices:
```bash
zen analyze --files src/**/*.py --analysis-type architecture --model gemini-pro
```

**Security Reviews** - Before handling sensitive data:
```bash
zen codereview --files auth_handler.py payment.py --type security --model o3
```

### Usage Decision Matrix

| Situation | Zen Command | When to Use |
|-----------|-------------|-------------|
| Stuck debugging | `zen debug` | After 5+ minutes without progress |
| Need validation | `zen chat` | When confidence < 80% on decisions |
| Code quality check | `zen codereview` | Before committing significant changes |
| Big architectural decision | `zen consensus` | For choices affecting multiple systems |
| Complex analysis needed | `zen analyze` | Understanding large/unfamiliar codebases |
| Project planning | `zen planner` | Breaking down complex features |

### Integration Patterns

**Pattern 1: Quick Consultation**
```bash
# When you need a second opinion
zen chat "Is using Redis for session storage appropriate for our scale?"
zen chat "Explain tradeoffs of JWT vs session cookies" --model gemini-pro
```

**Pattern 2: Systematic Debugging**  
```bash
# When facing complex bugs
zen debug "Memory leak in production" --confidence exploring
zen debug "Memory leak after 1000 requests" -f app.py -f worker.py --confidence medium
```

**Pattern 3: Code Quality Assurance**
```bash
# Before important commits
zen codereview --files src/*.py --type all
zen codereview --files auth/*.py --type security --model o3  
zen codereview --files api/*.py --type performance
```

**Pattern 4: Multi-Model Consensus**
```bash
# For critical decisions  
zen consensus "Should we migrate from REST to GraphQL?" --models gemini-pro,o3,gpt-4
zen consensus "PostgreSQL vs MongoDB for our use case?" --models gemini-pro,o3
```

### Performance Guidelines

**Model Selection:**
- `gemini-flash`: Fast responses for simple queries
- `gemini-pro`: Deep analysis and complex reasoning  
- `o3`: Strong logical reasoning and precision
- `auto`: Let Zen choose optimal model for task

**File Context:**
- Use `--files` to provide relevant context
- Glob patterns supported: `--files "src/**/*.py"`
- Keep file count reasonable for token limits

**Output Integration:**
- Use `--format json` for structured data processing
- Default markdown output integrates well with responses
- Pipe to files for documentation: `> analysis.md`

### Automatic Trigger Rules

**Always use Zen CLI when:**
- Debugging issues that have taken >5 minutes without progress
- Making architectural decisions affecting >2 components  
- Reviewing code for security implications
- Need consensus on technology choices
- Analyzing unfamiliar codebases >50 files
- Planning complex features with >3 major components

**Consider Zen CLI when:**
- Confidence < 80% on technical recommendations
- User explicitly asks for "second opinion" or "validation"
- Working with critical systems (auth, payment, security)
- Need to explain complex technical tradeoffs
- Refactoring significant portions of codebase

### Session Management

**Project Context:**
```bash
# Use projects for different contexts
zen project create client_work "Client development"
zen --project client_work debug "Client-specific issue"
zen project switch personal  # Switch contexts
```

**Conversation Continuity:**
```bash
# Continue complex debugging sessions
zen debug "Initial OAuth investigation" --session auth_debug
zen continue-chat --session auth_debug  # Resume later
```

**Storage Backend Configuration:**
```bash
# For team environments
export ZEN_STORAGE_TYPE=redis
export REDIS_HOST=shared.redis.server
zen chat "Team-accessible conversation"
```
```

## Zen CLI Integration Notes

- Zen CLI is a production-ready AI development assistant with 95% token optimization
- Provides multi-model consensus, systematic debugging, and code analysis
- Includes enterprise features like Redis storage and project management  
- Maintains conversation history and context across sessions
- Thread-safe with proper concurrency controls

This integration enables Claude Code to automatically leverage Zen CLI's specialized AI tools for enhanced development assistance.