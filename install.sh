#!/bin/bash

# Zen CLI Installation Script
# This script installs the Zen CLI and sets up basic configuration

set -e

echo "🚀 Zen CLI Installation"
echo "======================"

# Check Python version
python_version=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Error: Python 3.11+ required (found $python_version)"
    exit 1
fi

# Install the CLI
echo "📦 Installing Zen CLI..."

# Try to find pip or pip3
if command -v pip3 &> /dev/null; then
    PIP_CMD="pip3"
elif command -v pip &> /dev/null; then
    PIP_CMD="pip"
else
    echo "❌ Error: pip not found. Please install pip first."
    echo "Try: python3 -m ensurepip --upgrade"
    exit 1
fi

echo "Using: $PIP_CMD"
$PIP_CMD install -e .

# Check for API keys
echo ""
echo "🔑 Checking API keys..."
has_key=false

if [ ! -z "$GEMINI_API_KEY" ]; then
    echo "✅ GEMINI_API_KEY found"
    has_key=true
else
    echo "⚠️  GEMINI_API_KEY not set"
fi

if [ ! -z "$OPENAI_API_KEY" ]; then
    echo "✅ OPENAI_API_KEY found"
    has_key=true
else
    echo "⚠️  OPENAI_API_KEY not set"
fi

if [ ! -z "$OPENROUTER_API_KEY" ]; then
    echo "✅ OPENROUTER_API_KEY found"
    has_key=true
else
    echo "⚠️  OPENROUTER_API_KEY not set"
fi

if [ "$has_key" = false ]; then
    echo ""
    echo "❌ No API keys found! You need at least one."
    echo ""
    echo "Set API keys with:"
    echo "  export GEMINI_API_KEY='your-key-here'"
    echo "  export OPENAI_API_KEY='your-key-here'"
    echo ""
    echo "Get keys from:"
    echo "  Gemini: https://makersuite.google.com/app/apikey"
    echo "  OpenAI: https://platform.openai.com/api-keys"
    exit 1
fi

# Create config directory
echo ""
echo "📁 Creating configuration directory..."
mkdir -p ~/.zen

# Test the installation
echo ""
echo "✨ Testing installation..."
if zen --version > /dev/null 2>&1; then
    echo "✅ Zen CLI installed successfully!"
    echo ""
    zen --version
    echo ""
    echo "Available commands:"
    echo "  zen chat       - AI consultation"
    echo "  zen debug      - Systematic debugging"
    echo "  zen codereview - Code quality review"
    echo "  zen consensus  - Multi-model consensus"
    echo "  zen analyze    - Architecture analysis"
    echo "  zen planner    - Project planning"
    echo "  zen listmodels - Show available models"
    echo "  zen config     - Check configuration"
    echo ""
    echo "Try: zen chat 'Hello, Zen!'"
else
    echo "❌ Installation failed. Please check the errors above."
    exit 1
fi

# Optional: Add to Claude instructions
echo ""
echo "📝 Optional: Add Zen CLI to Claude Code"
echo "======================================="
echo ""
echo "To enable Claude Code to use Zen CLI, add to ~/.claude/CLAUDE.md:"
echo ""
echo "## Zen CLI Integration"
echo "Use \`zen\` command for AI assistance:"
echo "- Second opinions: \`zen chat \"question\"\`"
echo "- Debugging: \`zen debug \"issue\" --files code.py\`"
echo "- Code review: \`zen codereview --files src/*.py\`"
echo ""
echo "Installation complete! 🎉"