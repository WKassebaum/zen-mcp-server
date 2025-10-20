#!/bin/bash
# Test script for Claude CLI detection logic
# Tests the multi-location detection implemented in run-server.sh

echo "=== Testing Claude CLI Detection Logic ==="
echo

# Simulate the detection logic from run-server.sh
detect_claude_cli() {
    local claude_cmd=""

    # Try multiple common locations for Claude CLI
    if command -v claude &> /dev/null; then
        # Found in PATH
        claude_cmd="claude"
        echo "✓ Method 1: Found in PATH"
    elif [[ -x "$HOME/.claude/local/claude" ]]; then
        # Found in standard Claude CLI location (wrapper script)
        claude_cmd="$HOME/.claude/local/claude"
        echo "✓ Method 2: Found at ~/.claude/local/claude"
    elif [[ -x "$HOME/.claude/local/node_modules/.bin/claude" ]]; then
        # Found in npm modules location (actual binary)
        claude_cmd="$HOME/.claude/local/node_modules/.bin/claude"
        echo "✓ Method 3: Found at ~/.claude/local/node_modules/.bin/claude"
    elif [[ -x "/usr/local/bin/claude" ]]; then
        # Found in global installation
        claude_cmd="/usr/local/bin/claude"
        echo "✓ Method 4: Found at /usr/local/bin/claude"
    fi

    if [[ -z "$claude_cmd" ]]; then
        echo "✗ Claude CLI not detected in any location"
        return 1
    fi

    # Verify the command actually works
    if ! $claude_cmd --version &> /dev/null; then
        echo "✗ Found Claude CLI at $claude_cmd but it doesn't execute correctly"
        return 1
    fi

    echo "✓ Successfully detected and verified: $claude_cmd"
    $claude_cmd --version
    return 0
}

echo "Test 1: Detection Logic"
echo "------------------------"
detect_claude_cli
detection_result=$?

echo
echo "Test 2: Checking Installation Locations"
echo "----------------------------------------"

if command -v claude &> /dev/null; then
    echo "✓ Claude CLI found in PATH: $(command -v claude)"
else
    echo "✗ Claude CLI not in PATH"
fi

if [[ -x "$HOME/.claude/local/claude" ]]; then
    echo "✓ Claude CLI found at: ~/.claude/local/claude"
    ls -lh "$HOME/.claude/local/claude"
else
    echo "✗ ~/.claude/local/claude not found or not executable"
fi

if [[ -x "$HOME/.claude/local/node_modules/.bin/claude" ]]; then
    echo "✓ Binary found at: ~/.claude/local/node_modules/.bin/claude"
else
    echo "✗ ~/.claude/local/node_modules/.bin/claude not found"
fi

if [[ -x "/usr/local/bin/claude" ]]; then
    echo "✓ Global installation found at: /usr/local/bin/claude"
else
    echo "✗ /usr/local/bin/claude not found"
fi

echo
echo "Test 3: Shell Alias Detection"
echo "------------------------------"
alias_check=$(alias claude 2>/dev/null)
if [[ -n "$alias_check" ]]; then
    echo "✓ Shell alias detected: $alias_check"
    echo "  Note: Aliases won't work in non-interactive scripts"
else
    echo "✗ No shell alias for 'claude' detected"
fi

echo
echo "=== Test Summary ==="
if [[ $detection_result -eq 0 ]]; then
    echo "✓ SUCCESS: Claude CLI detection working correctly"
    exit 0
else
    echo "✗ FAILURE: Claude CLI not detected"
    echo ""
    echo "This is expected if you don't have Claude CLI installed."
    echo "To install, visit: https://docs.anthropic.com/en/docs/claude-code/cli-usage"
    exit 1
fi
