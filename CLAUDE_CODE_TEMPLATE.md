# Zen CLI v2.0 - Claude Code Integration Template

This template enables Claude Code to leverage the production-ready Zen CLI v2.0 for enhanced AI-powered development assistance. The Zen CLI provides direct access to multiple AI models (Gemini, OpenAI, etc.) with enterprise-grade features including project management, multi-backend storage, and conversation continuity.

## Installation for Claude Code Users

### 🚀 Automated Installation (Recommended)
```bash
# Clone and install with auto-detection
git clone https://github.com/WKassebaum/zen-mcp-server.git zen-cli
cd zen-cli
git checkout v2.0
./install.sh
```

The installer will:
- ✅ Auto-detect Claude Code installation  
- ✅ Install Zen CLI with pipx
- ✅ Offer to install Claude Code integration template
- ✅ Set up configuration automatically

### 📦 Alternative Installation Methods
```bash
# Method 1: Direct from GitHub with pipx
pipx install git+https://github.com/WKassebaum/zen-mcp-server.git@v2.0

# Method 2: Template installer only (if Zen CLI already installed)  
curl -sSL https://raw.githubusercontent.com/WKassebaum/zen-mcp-server/v2.0/install-claude-template.sh | bash

# Method 3: Manual installation
git clone https://github.com/WKassebaum/zen-mcp-server.git zen-cli
cd zen-cli && git checkout v2.0
pip install --user --break-system-packages .
./install-claude-template.sh
```

### ⚙️ API Key Setup
```bash
# Add to your ~/.zshrc or ~/.bashrc
export GEMINI_API_KEY="your-gemini-key-here"
export OPENAI_API_KEY="your-openai-key-here"

# Reload shell and verify
source ~/.zshrc
zen --version
zen listmodels
```

## Claude Code Template Instructions

Add the following to your Claude Code CLAUDE.md or project instructions:

```markdown
## Zen CLI Integration

You have access to the Zen CLI, a powerful standalone tool for AI-assisted development.
Use it to get second opinions, validate approaches, or delegate specialized tasks.

### Auto-Trigger Patterns

Use Zen CLI automatically when you encounter:

#### Low Confidence Situations
When confidence < high on critical decisions:
```bash
zen consensus "Should we use microservices or monolith for this e-commerce platform?" \
  --models gemini-pro,o3 \
  --context-files architecture.md,requirements.txt
```

#### Complex Debugging
When stuck on difficult bugs:
```bash
zen debug "OAuth tokens not persisting across sessions" \
  --files src/auth.py,src/session.py \
  --confidence exploring \
  --model gemini-pro
```

#### Architecture Decisions
For important architectural choices:
```bash
zen analyze --files src/**/*.py \
  --analysis-type architecture \
  --model gemini-pro
```

#### Security Reviews
Before handling sensitive data:
```bash
zen codereview --files auth_handler.py payment.py \
  --type security \
  --model o3
```

#### Deep Thinking Required
For complex problem-solving:
```bash
zen thinkdeep "How to implement rate limiting with distributed caching" \
  --thinking-mode high \
  --model gemini-pro
```

### Usage Patterns for Claude Code

#### Pattern 1: Quick Consultation
When you need a second opinion:
```bash
# Get quick advice
zen chat "Is using Redis for session storage a good idea for our scale?"

# With specific model
zen chat "Explain the tradeoffs of JWT vs session cookies" --model gemini-pro
```

#### Pattern 2: Systematic Debugging
When facing complex bugs:
```bash
# Start exploration
zen debug "Memory leak in production" --confidence exploring

# Provide more context
zen debug "Memory leak occurs after 1000 requests" \
  --files app.py,worker.py \
  --confidence medium
```

#### Pattern 3: Code Quality Checks
Before important commits:
```bash
# Full review
zen codereview --files src/*.py --type all

# Security focus
zen codereview --files auth/*.py --type security --model o3

# Performance analysis
zen codereview --files api/*.py --type performance --model gemini-flash
```

#### Pattern 4: Multi-Model Consensus
For critical decisions:
```bash
# Architecture decisions
zen consensus "Should we migrate from REST to GraphQL?" \
  --models gemini-pro,o3,gpt-4 \
  --context-files api_spec.yaml

# Technology choices
zen consensus "PostgreSQL vs MongoDB for our use case?" \
  --models gemini-pro,o3
```

#### Pattern 5: Project Planning
Breaking down complex tasks:
```bash
# Create implementation plan
zen planner "Implement OAuth2 with refresh tokens and PKCE" \
  --context-files requirements.md

# Migration planning
zen planner "Migrate from monolith to microservices" \
  --context-files architecture.md,tech_debt.md
```

#### Pattern 6: Interactive Development (v2.0 New)
Enhanced development workflows:
```bash
# Interactive mode with conversation continuity
zen interactive --model gemini-pro

# Continue previous debugging session
zen continue-chat --session oauth_debug

# Project-specific conversations
zen --project client_work chat "Review authentication requirements"
```

#### Pattern 7: Multi-Backend Storage (v2.0 New)
Enterprise storage and team collaboration:
```bash
# File storage (default)
zen chat "Local development question" --session local_dev

# Redis storage for team collaboration
export ZEN_STORAGE_TYPE=redis
export REDIS_HOST=redis.company.com
zen chat "Team-accessible conversation" --session team_project

# Project-specific Redis configuration
zen project create enterprise_app "Enterprise development"
zen config set projects.enterprise_app.storage.type=redis
zen --project enterprise_app debug "Enterprise-specific issue"
```

### Advanced Integration

#### Automated Workflows
Chain commands for comprehensive analysis:
```bash
# Complete code review workflow
zen analyze --files src/ --analysis-type architecture > analysis.md
zen codereview --files src/*.py --type quality > review.md
zen consensus "Are there any critical issues?" \
  --context-files analysis.md,review.md \
  --models gemini-pro,o3
```

#### JSON Output for Processing (v2.0 Enhanced)
Get structured output with flexible formatting:
```bash
# JSON for parsing and automation
zen debug "API timeout issues" --format json | jq '.result.hypothesis'

# Markdown for documentation
zen analyze --files src/ --format markdown > analysis.md

# Plain text for simple scripts  
zen chat "Quick question" --format plain

# Store structured results
zen codereview --files src/*.py --format json > review.json
```

#### Project Management Workflows (v2.0 New)
Organize work by projects and clients:
```bash
# Create and manage projects
zen project create client_alpha "Alpha Corp development"
zen project create internal_tools "Internal tooling project"

# Switch project context
zen project switch client_alpha

# Project-specific debugging with isolated conversations
zen --project client_alpha debug "Client-specific OAuth issue" \
  --files client_auth.py --session alpha_oauth

# List and manage projects
zen project list
zen project delete old_project
```

#### Conditional Execution
Use in bash scripts:
```bash
# Run security audit before deployment
if [ "$DEPLOY_ENV" = "production" ]; then
    zen codereview --files src/ --type security --model o3
    if [ $? -ne 0 ]; then
        echo "Security issues found. Aborting deployment."
        exit 1
    fi
fi
```

### When to Use Each Tool (v2.0 Updated)

| Situation | Command | Purpose |
|-----------|---------|---------|
| Stuck on bug | `zen debug` | Systematic investigation |
| Need validation | `zen chat` | Quick consultation |
| Code quality | `zen codereview` | Professional review |
| Big decision | `zen consensus` | Multiple perspectives |
| Complex analysis | `zen analyze` | Architecture understanding |
| Project breakdown | `zen planner` | Task decomposition |
| Deep reasoning | `zen thinkdeep` | Extended analysis |
| Interactive development | `zen interactive` | Multi-turn conversations |
| Continue session | `zen continue-chat` | Resume previous conversations |
| Project management | `zen project` | Organize work by client/context |
| Configuration | `zen config` | Manage settings and health |
| Session management | `zen sessions` | List and manage active sessions |

### Environment Variables

Set these in your shell or Claude Code environment:
```bash
# Required: At least one API key
export GEMINI_API_KEY="your-gemini-key"
export OPENAI_API_KEY="your-openai-key"
export OPENROUTER_API_KEY="your-openrouter-key"
export XAI_API_KEY="your-xai-key"

# Optional: Redis for conversation memory
export REDIS_URL="redis://localhost:6379/0"

# Optional: Default model preference
export DEFAULT_MODEL="gemini-pro"  # or "auto"
```

### Troubleshooting

#### Check Configuration
```bash
zen config  # View current configuration
zen listmodels  # See available models
zen version  # Check version and setup
```

#### Common Issues

1. **No API keys**: Set at least one API key environment variable
2. **Redis not available**: Conversation memory will use in-memory fallback
3. **Model not available**: Check `zen listmodels` for available models
4. **Import errors**: Ensure all dependencies are installed: `pip install -e .`

### Performance Tips

1. **Model Selection**:
   - `gemini-flash`: Fast responses for simple queries
   - `gemini-pro`: Deep analysis and complex reasoning
   - `o3`: Strong logical reasoning
   - `auto`: Let Zen choose based on task

2. **File Context**:
   - Use `--files` to provide relevant context
   - Glob patterns work: `--files "src/**/*.py"`
   - Keep file count reasonable for token limits

3. **Output Formats**:
   - Use `--json` for structured data
   - Default markdown output for readability
   - Pipe to files for documentation: `> analysis.md`

## Example Claude Code Workflow

Here's how Claude Code might use Zen CLI in practice:

```markdown
User: "Help me debug why our authentication is failing intermittently"

Claude's Internal Process:
1. Initial investigation locally
2. If complexity is high or confidence is low:
   ```bash
   zen debug "Authentication failing intermittently" \
     --files auth_handler.py,session_manager.py \
     --confidence exploring \
     --model gemini-pro
   ```
3. Analyze the response from Zen
4. If Zen suggests specific hypotheses, investigate them
5. For critical fixes, validate approach:
   ```bash
   zen consensus "Should we implement retry logic with exponential backoff?" \
     --models gemini-pro,o3
   ```
6. Before committing:
   ```bash
   zen codereview --files auth_handler.py --type security
   ```

Claude's Response to User:
"I've identified the issue with help from specialized analysis. The authentication 
is failing due to race conditions in token refresh. Here's my fix with validation 
from security review..."
```

## Benefits for Claude Code

1. **Enhanced Capabilities**: Access to multiple specialized AI models
2. **Validation**: Get second opinions on critical decisions
3. **Specialization**: Use the best model for each task
4. **Efficiency**: Delegate complex analysis to specialized tools
5. **Quality**: Professional code reviews and security audits
6. **Confidence**: Build consensus from multiple expert systems

## Quick Reference Card

```bash
# Quick consultation
zen chat "question"

# Debug with context  
zen debug "problem" --files file1.py,file2.py

# Code review
zen codereview --files src/*.py --type quality

# Multi-model consensus
zen consensus "decision?" --models model1,model2

# Architecture analysis
zen analyze --files src/ --analysis-type architecture

# Project planning
zen planner "goal" --context-files requirements.md

# Deep thinking
zen thinkdeep "complex topic" --thinking-mode high

# List available models
zen listmodels

# Check configuration
zen config
```

---

This template enables Claude Code to seamlessly integrate with Zen CLI, providing
access to powerful AI capabilities through simple command-line interfaces. The 
standalone architecture means no server setup required - just install and use!
```