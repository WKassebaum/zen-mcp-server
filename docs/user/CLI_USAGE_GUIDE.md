# Zen CLI Usage Guide

## Current Status

The Zen CLI is installed and partially working. There are some import issues related to MCP dependencies that need to be resolved for full functionality.

### What Works
- CLI installation: `/Users/wrk/Library/Python/3.13/bin/zen`
- Basic command structure
- Version command: `zen --version`

### Known Issues
- Tools are encountering import errors related to MCP module dependencies
- Need to fully decouple from MCP server dependencies

## Command Structure

The Zen CLI follows this general pattern:
```bash
zen <tool> [arguments] [options]
```

## Available Tools

### 1. Chat - General AI Consultation
```bash
# Basic usage
zen chat "Your question or prompt"

# With model selection
zen chat "Explain REST APIs" --model gemini-2.0-flash-exp

# With temperature control
zen chat "Creative writing prompt" --temperature 0.8

# With files for context
zen chat "Review this code" --files /path/to/file.py

# JSON output
zen chat "List Python best practices" --json
```

### 2. Debug - Systematic Debugging
```bash
# Basic debugging
zen debug "OAuth tokens not persisting"

# With files
zen debug "Function not working" --files auth.py session.py

# Workflow mode for complex issues
zen debug --workflow "Complex authentication issue" --step 1
```

### 3. Code Review
```bash
# Review specific files
zen codereview --files src/*.py

# With specific focus
zen codereview --files main.py --focus "security"

# Workflow mode
zen codereview --workflow --files /project --step 1
```

### 4. Consensus - Multi-Model Agreement
```bash
# Get consensus from multiple models
zen consensus "Should we use microservices?"

# Specify models
zen consensus "Architecture decision" --models gemini,o3

# With context files
zen consensus "API design choices" --files api_spec.md
```

### 5. Analyze - Code Analysis
```bash
# Analyze codebase
zen analyze --files /src

# Specific analysis
zen analyze "security vulnerabilities" --files *.py

# Architecture analysis
zen analyze --architecture --files /project
```

### 6. Test Generation
```bash
# Generate tests for code
zen testgen --files module.py

# Specific test types
zen testgen --files api.py --type integration

# With coverage goals
zen testgen --files /src --coverage 80
```

### 7. Documentation Generation
```bash
# Generate documentation
zen docgen --files /src

# API documentation
zen docgen --files api.py --format openapi

# README generation
zen docgen --project /myproject --readme
```

### 8. Refactoring Suggestions
```bash
# Analyze for refactoring
zen refactor --files legacy_code.py

# Specific refactoring type
zen refactor --files /src --type "extract-method"

# With complexity threshold
zen refactor --files *.py --complexity 10
```

### 9. Security Audit
```bash
# Security analysis
zen secaudit --files /src

# Specific vulnerability check
zen secaudit --files api.py --check "sql-injection"

# Compliance check
zen secaudit --files /project --compliance "owasp"
```

### 10. Planning Tool
```bash
# Create implementation plan
zen planner "Implement OAuth2 authentication"

# With context
zen planner "Migrate to microservices" --files architecture.md

# Step-by-step plan
zen planner --detailed "Build REST API"
```

### 11. Tracer - Code Execution Tracing
```bash
# Trace code execution
zen tracer --files main.py --entry "main()"

# Trace specific function
zen tracer --function "process_payment" --files payment.py

# With call graph
zen tracer --files /src --callgraph
```

## Model Selection

### Auto Mode (Default)
```bash
zen chat "Your prompt"  # Claude selects the best model
```

### Specific Models
```bash
# Gemini models
zen chat "prompt" --model gemini-2.0-flash-exp
zen chat "prompt" --model gemini-exp-1206

# OpenAI models
zen chat "prompt" --model gpt-4o
zen chat "prompt" --model o3-mini

# X.AI models
zen chat "prompt" --model grok-beta
```

## Complex Schemas and Multi-Part Arguments

### Using JSON for Complex Arguments
```bash
# For tools with complex schemas, use JSON
zen consensus --json-args '{
  "prompt": "Architecture decision",
  "models": ["gemini-exp-1206", "o3-mini"],
  "temperature": 0.3,
  "files": ["design.md", "requirements.md"]
}'
```

### Workflow Tools with Steps
```bash
# Initial step
zen debug --workflow --step 1 --request '{
  "problem": "OAuth failing",
  "confidence": "exploring",
  "files": ["auth.py"]
}'

# Continue workflow
zen debug --workflow --step 2 --continuation-id "uuid-here" --request '{
  "findings": "Token not persisting",
  "next_action": "check_storage"
}'
```

## Configuration

### API Keys
Set environment variables:
```bash
export GEMINI_API_KEY="your-key"
export OPENAI_API_KEY="your-key"
export XAI_API_KEY="your-key"
```

Or use config file at `~/.zen-cli/config.json`:
```json
{
  "api_keys": {
    "gemini": "your-key",
    "openai": "your-key",
    "xai": "your-key"
  }
}
```

## Two-Stage Token Optimization

### Stage 1: Mode Selection
```bash
zen select "Debug OAuth token persistence issue"
# Returns recommended mode and complexity
```

### Stage 2: Execution
```bash
zen execute debug --complexity workflow --request '{...}'
```

## Output Formats

### Default (Markdown)
```bash
zen chat "prompt"  # Human-readable markdown output
```

### JSON Output
```bash
zen chat "prompt" --json  # Structured JSON response
```

### Plain Text
```bash
zen chat "prompt" --plain  # Plain text without formatting
```

## Continuation and Threading

### Start a Conversation
```bash
zen chat "Initial question"
# Returns continuation_id in response
```

### Continue Conversation
```bash
zen chat "Follow-up question" --continuation-id "uuid-from-previous"
```

## Testing the CLI

### Basic Test
```bash
# Test if installed
zen --version

# Test with minimal API call
zen chat "Say hello" --model gemini-2.0-flash-exp
```

### Testing Without API Keys
```bash
# List available models (no API needed)
zen listmodels

# Show version info
zen version
```

### Debug Mode
```bash
# Run with debug logging
ZEN_DEBUG=1 zen chat "test"

# Verbose output
zen chat "test" --verbose
```

## Troubleshooting

### Command Not Found
```bash
# Use full path
/Users/wrk/Library/Python/3.13/bin/zen --version

# Or add to PATH
export PATH="$PATH:$HOME/Library/Python/3.13/bin"
```

### Import Errors
Current issue with MCP dependencies. Workaround:
```bash
# Run directly from source
cd /Users/wrk/WorkDev/MCP-Dev/zen-cli/src
python3 -m zen_cli.main chat "your prompt"
```

### API Key Issues
```bash
# Check if keys are set
env | grep API_KEY

# Test with specific provider
zen chat "test" --model gemini-2.0-flash-exp
```

## Examples for Common Tasks

### Quick Code Review
```bash
zen codereview --files mycode.py --focus "bugs,performance"
```

### Debug with Context
```bash
zen debug "Database connection failing" \
  --files db.py config.py \
  --model gemini-exp-1206
```

### Architecture Decision
```bash
zen consensus "Should we migrate to Kubernetes?" \
  --models gemini-exp-1206,o3-mini \
  --files infrastructure.md
```

### Generate Tests
```bash
zen testgen --files api.py \
  --type "unit,integration" \
  --framework pytest
```

### Security Check
```bash
zen secaudit --files /src \
  --compliance "owasp-top-10" \
  --output security-report.md
```

## Future Enhancements Needed

1. **Fix MCP Dependencies**: Complete decoupling from MCP server
2. **Add Progress Indicators**: Show progress for long operations
3. **Implement Streaming**: Stream responses for better UX
4. **Add Interactive Mode**: REPL-style interaction
5. **Project Configuration**: Per-project `.zen.yml` files
6. **Shell Completion**: Bash/Zsh autocompletion
7. **Plugin System**: Extensible tool architecture