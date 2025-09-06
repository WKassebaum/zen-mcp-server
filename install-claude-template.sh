#!/bin/bash
# Zen CLI - Claude Code Template Installer
# Automatically adds Zen CLI integration template to Claude Code

set -e

CLAUDE_CONFIG_DIR="$HOME/.claude"
CLAUDE_MD="$CLAUDE_CONFIG_DIR/CLAUDE.md"
TEMPLATE_MARKER="## 🧠 Zen CLI Integration"

echo "🤖 Zen CLI - Claude Code Template Installer"
echo "=========================================="

# Function to detect Claude Code installation
detect_claude_code() {
    local claude_detected=false
    
    echo "🔍 Detecting Claude Code installation..."
    
    # Method 1: Check for Claude Code binary
    if command -v claude-code &> /dev/null; then
        echo "✅ Claude Code binary found: $(which claude-code)"
        claude_detected=true
    fi
    
    # Method 2: Check for Claude Code config directory
    if [ -d "$CLAUDE_CONFIG_DIR" ]; then
        echo "✅ Claude Code config directory found: $CLAUDE_CONFIG_DIR"
        claude_detected=true
    fi
    
    # Method 3: Check for Claude Code config file
    if [ -f "$CLAUDE_CONFIG_DIR/config.json" ]; then
        echo "✅ Claude Code config file found"
        claude_detected=true
    fi
    
    # Method 4: Check for existing CLAUDE.md
    if [ -f "$CLAUDE_MD" ]; then
        echo "✅ Claude Code CLAUDE.md found"
        claude_detected=true
    fi
    
    if [ "$claude_detected" = false ]; then
        echo "❌ Claude Code not detected"
        echo ""
        echo "Claude Code doesn't appear to be installed or configured."
        echo "Please install Claude Code first, then run this script again."
        echo ""
        echo "Claude Code installation: https://claude.ai/code"
        exit 1
    fi
    
    echo "✅ Claude Code installation confirmed"
}

# Function to backup existing CLAUDE.md
backup_claude_md() {
    if [ -f "$CLAUDE_MD" ]; then
        local backup_file="${CLAUDE_MD}.backup.$(date +%Y%m%d_%H%M%S)"
        echo "📋 Backing up existing CLAUDE.md to: ${backup_file##*/}"
        cp "$CLAUDE_MD" "$backup_file"
    fi
}

# Function to check if template is already installed
check_existing_template() {
    if [ -f "$CLAUDE_MD" ] && grep -q "$TEMPLATE_MARKER" "$CLAUDE_MD"; then
        echo "⚠️  Zen CLI template already exists in CLAUDE.md"
        echo ""
        read -p "Do you want to update the existing template? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "❌ Installation cancelled"
            exit 0
        fi
        
        echo "🔄 Updating existing template..."
        # Remove existing template section
        if command -v sed &> /dev/null; then
            # Create temp file without the template section
            awk "/$TEMPLATE_MARKER/,/^## / {if (!/^## / || /$TEMPLATE_MARKER/) next} 1" "$CLAUDE_MD" > "${CLAUDE_MD}.tmp"
            mv "${CLAUDE_MD}.tmp" "$CLAUDE_MD"
        fi
    fi
}

# Function to install the template
install_template() {
    echo "📝 Installing Zen CLI integration template..."
    
    # Ensure Claude config directory exists
    mkdir -p "$CLAUDE_CONFIG_DIR"
    
    # Create CLAUDE.md if it doesn't exist
    if [ ! -f "$CLAUDE_MD" ]; then
        echo "📄 Creating new CLAUDE.md file..."
        cat > "$CLAUDE_MD" << 'EOF'
# CLAUDE.md - Claude Code Configuration

This file contains configuration and templates for Claude Code.

EOF
    fi
    
    # Add the Zen CLI integration template
    cat >> "$CLAUDE_MD" << 'EOF'

## 🧠 Zen CLI Integration

### Auto-Trigger Patterns

You have access to the Zen CLI tool via Bash. Use it automatically when encountering:

**Low Confidence Situations** - When confidence < high on critical decisions:
```bash
zen consensus "Should we use microservices or monolith for this e-commerce platform?" --models gemini-pro,o3
```

**Complex Debugging** - When stuck on difficult bugs:
```bash
zen debug "OAuth tokens not persisting across sessions" --files src/auth.py,src/session.py --confidence exploring
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
zen debug "Memory leak after 1000 requests" --files app.py,worker.py --confidence medium
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

### Quick Reference

```bash
# Essential commands
zen chat "question"                                    # Quick consultation
zen debug "problem" --files file1.py,file2.py        # Debug with context  
zen codereview --files src/*.py --type quality        # Code review
zen consensus "decision?" --models model1,model2      # Multi-model consensus
zen analyze --files src/ --analysis-type architecture # Architecture analysis
zen planner "goal" --context-files requirements.md    # Project planning
```

EOF
    
    echo "✅ Template installed successfully!"
}

# Function to verify installation
verify_installation() {
    echo ""
    echo "🔍 Verifying installation..."
    
    if grep -q "$TEMPLATE_MARKER" "$CLAUDE_MD"; then
        echo "✅ Template verified in CLAUDE.md"
    else
        echo "❌ Template verification failed"
        exit 1
    fi
    
    # Check if zen command is available
    if command -v zen &> /dev/null; then
        echo "✅ Zen CLI command available: $(which zen)"
    else
        echo "⚠️  Zen CLI command not found in PATH"
        echo "   You may need to restart your terminal or run: pipx ensurepath"
    fi
}

# Function to display next steps
show_next_steps() {
    echo ""
    echo "🎉 Installation Complete!"
    echo "======================="
    echo ""
    echo "Next steps:"
    echo "1. 📝 Edit $CLAUDE_MD to customize the template if needed"
    echo "2. 🔑 Ensure your API keys are set:"
    echo "   export GEMINI_API_KEY=\"your-key\""
    echo "   export OPENAI_API_KEY=\"your-key\""
    echo "3. ✅ Test the integration:"
    echo "   zen chat \"Hello from Claude Code integration!\""
    echo "4. 🚀 Start a new Claude Code session to use the template"
    echo ""
    echo "📖 For more details, see: CLAUDE_CODE_TEMPLATE.md"
    echo ""
}

# Main execution
main() {
    detect_claude_code
    backup_claude_md
    check_existing_template
    install_template
    verify_installation
    show_next_steps
}

# Run main function
main "$@"