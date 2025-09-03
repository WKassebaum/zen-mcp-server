# Zen CLI Testing Guide

## Testing Strategy

This guide provides comprehensive testing procedures for the Zen CLI to ensure all functionality works correctly.

## Prerequisites

### 1. Environment Setup
```bash
# Ensure API keys are set
export GEMINI_API_KEY="your-key"
export OPENAI_API_KEY="your-key"  # Optional
export XAI_API_KEY="your-key"     # Optional

# Verify installation
zen --version  # Should output: zen, version 1.0.0
```

### 2. Test Files Setup
Create test files for testing:
```bash
# Create test directory
mkdir -p ~/zen-test
cd ~/zen-test

# Create sample Python file
cat > test_code.py << 'EOF'
def calculate_sum(a, b):
    """Add two numbers."""
    return a + b

def process_data(data):
    # TODO: Implement data processing
    pass

class UserAuth:
    def login(self, username, password):
        # Security issue: plain text password
        if password == "admin":
            return True
        return False
EOF

# Create sample config file
cat > config.json << 'EOF'
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "password": "plain_text_password"
  }
}
EOF
```

## Test Suite

### Level 1: Basic Functionality Tests

#### Test 1.1: Version Check
```bash
# Command
zen --version

# Expected Output
zen, version 1.0.0

# Status: ✅ PASS / ❌ FAIL
```

#### Test 1.2: Help Display
```bash
# Command
zen --help

# Expected Output
# Should display available commands and options

# Status: ✅ PASS / ❌ FAIL
```

### Level 2: Individual Tool Tests

#### Test 2.1: Chat Tool
```bash
# Basic chat
zen chat "What is 2+2?"
# Expected: Simple answer "4"

# Chat with model selection
zen chat "Explain Python decorators" --model gemini-2.0-flash-exp
# Expected: Explanation of decorators

# Chat with file context
zen chat "What does this function do?" --files test_code.py
# Expected: Explanation of calculate_sum function

# Chat with temperature
zen chat "Write a haiku about coding" --temperature 0.9
# Expected: Creative haiku

# JSON output
zen chat "List 3 Python tips" --json
# Expected: JSON formatted response
```

#### Test 2.2: Debug Tool
```bash
# Basic debug
zen debug "Function returns None instead of value"
# Expected: Debugging suggestions

# Debug with files
zen debug "process_data not working" --files test_code.py
# Expected: Analysis of the TODO function

# Debug workflow (if working)
zen debug --workflow --step 1 --request '{"problem": "login failing", "files": ["test_code.py"]}'
# Expected: Step-by-step debugging process
```

#### Test 2.3: Code Review Tool
```bash
# Review single file
zen codereview --files test_code.py
# Expected: Review pointing out TODO and security issue

# Review with focus
zen codereview --files test_code.py --focus "security"
# Expected: Focus on plain text password issue

# Review multiple files
zen codereview --files test_code.py config.json
# Expected: Review both files
```

#### Test 2.4: Security Audit Tool
```bash
# Security audit
zen secaudit --files test_code.py config.json
# Expected: Flag password security issues

# Specific vulnerability check
zen secaudit --files test_code.py --check "hardcoded-secrets"
# Expected: Find hardcoded password
```

#### Test 2.5: Test Generation Tool
```bash
# Generate tests
zen testgen --files test_code.py
# Expected: Generate tests for calculate_sum

# Specific test framework
zen testgen --files test_code.py --framework pytest
# Expected: Pytest-style tests
```

#### Test 2.6: Documentation Generation
```bash
# Generate docs
zen docgen --files test_code.py
# Expected: Documentation for the module

# Specific format
zen docgen --files test_code.py --format markdown
# Expected: Markdown documentation
```

#### Test 2.7: Refactor Analysis
```bash
# Refactor suggestions
zen refactor --files test_code.py
# Expected: Suggest implementing TODO, improving security

# Complexity analysis
zen refactor --files test_code.py --complexity 5
# Expected: Complexity-based suggestions
```

#### Test 2.8: List Models
```bash
# List available models
zen listmodels
# Expected: List of configured models by provider
```

#### Test 2.9: Version Tool
```bash
# Show version info
zen version
# Expected: Detailed version information
```

### Level 3: Advanced Features Tests

#### Test 3.1: Consensus Tool
```bash
# Multi-model consensus
zen consensus "Is this code secure?" --files test_code.py
# Expected: Consensus from multiple models about security

# Specify models
zen consensus "Best practice for passwords" --models gemini,o3
# Expected: Agreement from specified models
```

#### Test 3.2: Analyze Tool
```bash
# Code analysis
zen analyze --files test_code.py
# Expected: Comprehensive code analysis

# Architecture analysis
zen analyze --architecture --files ~/zen-test
# Expected: Project structure analysis
```

#### Test 3.3: Planner Tool
```bash
# Create plan
zen planner "Fix security issues in authentication"
# Expected: Step-by-step plan

# Plan with context
zen planner "Improve this code" --files test_code.py
# Expected: Specific improvement plan
```

#### Test 3.4: Tracer Tool
```bash
# Trace execution
zen tracer --files test_code.py --function calculate_sum
# Expected: Trace of function execution

# Call graph
zen tracer --files test_code.py --callgraph
# Expected: Visual call graph
```

### Level 4: Integration Tests

#### Test 4.1: Continuation/Threading
```bash
# Start conversation
RESPONSE=$(zen chat "What is Python?" --json)
CONTINUATION_ID=$(echo $RESPONSE | jq -r '.continuation_id')

# Continue conversation
zen chat "What about its history?" --continuation-id $CONTINUATION_ID
# Expected: Contextual response about Python's history
```

#### Test 4.2: Two-Stage Optimization
```bash
# Stage 1: Mode selection
zen select "Debug authentication issue"
# Expected: Mode recommendation

# Stage 2: Execution
zen execute debug --complexity simple --request '{"problem": "login fails"}'
# Expected: Execution with optimized tokens
```

#### Test 4.3: Output Formats
```bash
# Markdown (default)
zen chat "Hello"
# Expected: Markdown formatted response

# JSON
zen chat "Hello" --json
# Expected: {"status": "success", "result": "..."}

# Plain text
zen chat "Hello" --plain
# Expected: Plain text without formatting
```

## Performance Tests

### Test P1: Response Time
```bash
# Measure response time
time zen chat "Hello" --model gemini-2.0-flash-exp
# Expected: < 5 seconds for simple query
```

### Test P2: Token Usage
```bash
# Check token optimization
ZEN_DEBUG=1 zen chat "Explain REST" 2>&1 | grep -i token
# Expected: Token count information
```

### Test P3: Large File Handling
```bash
# Create large file
python3 -c "print('def func():\n    pass\n' * 1000)" > large.py

# Test with large file
zen codereview --files large.py
# Expected: Handle gracefully or show size warning
```

## Error Handling Tests

### Test E1: Missing API Key
```bash
# Unset API key
unset GEMINI_API_KEY

# Try to use tool
zen chat "Hello"
# Expected: Clear error about missing API key
```

### Test E2: Invalid Model
```bash
# Use non-existent model
zen chat "Hello" --model invalid-model
# Expected: Error listing available models
```

### Test E3: File Not Found
```bash
# Reference non-existent file
zen codereview --files /nonexistent/file.py
# Expected: Clear file not found error
```

### Test E4: Invalid JSON Arguments
```bash
# Malformed JSON
zen consensus --json-args '{"invalid json}'
# Expected: JSON parsing error
```

## Test Automation Script

Create `run_tests.sh`:
```bash
#!/bin/bash

# Zen CLI Test Suite
echo "Starting Zen CLI Test Suite"
echo "============================"

# Test counter
PASS=0
FAIL=0

# Function to run test
run_test() {
    local name="$1"
    local cmd="$2"
    local expected="$3"
    
    echo -n "Testing $name... "
    
    if output=$($cmd 2>&1); then
        if [[ "$output" == *"$expected"* ]]; then
            echo "✅ PASS"
            ((PASS++))
        else
            echo "❌ FAIL (unexpected output)"
            ((FAIL++))
        fi
    else
        echo "❌ FAIL (command failed)"
        ((FAIL++))
    fi
}

# Run tests
run_test "version" "zen --version" "zen, version 1.0.0"
run_test "listmodels" "zen listmodels" "Available Models"
run_test "chat" "zen chat 'Say hello'" "hello"

# Summary
echo "============================"
echo "Tests Passed: $PASS"
echo "Tests Failed: $FAIL"
echo "Total Tests: $((PASS + FAIL))"

exit $FAIL
```

## Known Issues to Test

### Current Issues (as of testing)
1. **MCP Import Error**: Tools may fail with MCP-related import errors
2. **Async Execution**: Some async operations may not work correctly
3. **Complex Schemas**: Multi-part arguments may need special handling

### Workarounds
```bash
# Run from source if installed version fails
cd /Users/wrk/WorkDev/MCP-Dev/zen-cli/src
python3 -m zen_cli.main chat "test"

# Use simple arguments instead of complex
zen chat "test" --model auto  # Instead of complex JSON args
```

## Test Reporting Template

```markdown
## Zen CLI Test Report

**Date**: [DATE]
**Version**: 1.0.0
**Tester**: [NAME]

### Summary
- Total Tests: X
- Passed: X
- Failed: X
- Blocked: X

### Test Results

| Test ID | Test Name | Status | Notes |
|---------|-----------|--------|-------|
| 1.1 | Version Check | ✅ PASS | |
| 1.2 | Help Display | ✅ PASS | |
| 2.1 | Chat Tool | ❌ FAIL | Import error |
| ... | ... | ... | ... |

### Issues Found
1. [Issue description]
2. [Issue description]

### Recommendations
1. [Recommendation]
2. [Recommendation]
```

## Continuous Testing

### Pre-commit Testing
```bash
# Add to .git/hooks/pre-commit
#!/bin/bash
zen --version > /dev/null 2>&1 || exit 1
echo "Zen CLI check passed"
```

### Daily Smoke Test
```bash
# Quick daily test
zen --version && \
zen listmodels && \
zen chat "test" --model gemini-2.0-flash-exp && \
echo "Daily smoke test passed"
```

## Debug and Troubleshooting

### Enable Debug Mode
```bash
# Debug logging
ZEN_DEBUG=1 zen chat "test"

# Verbose output
zen chat "test" --verbose

# Trace execution
python3 -m trace -t $(which zen) chat "test"
```

### Check Dependencies
```bash
# List installed packages
pip3 list | grep -E "zen-cli|google-generativeai|openai"

# Check imports
python3 -c "from zen_cli.main import cli; print('Import successful')"
```

### Test Individual Components
```bash
# Test tool import
python3 -c "from zen_cli.tools.chat import ChatTool; print('OK')"

# Test provider
python3 -c "from zen_cli.providers.gemini import GeminiModelProvider; print('OK')"

# Test configuration
python3 -c "from zen_cli.config import load_config; print(load_config())"
```

## Next Steps

1. **Fix Import Issues**: Resolve MCP dependency problems
2. **Add Unit Tests**: Create pytest suite
3. **Integration Tests**: Test tool interactions
4. **Performance Benchmarks**: Measure token usage and speed
5. **CI/CD Pipeline**: Automated testing on commits