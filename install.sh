#!/bin/bash
# Zen CLI Installation Script

set -e

echo "🚀 Installing Zen CLI..."

# Check if pipx is installed
if ! command -v pipx &> /dev/null; then
    echo "📦 pipx not found. Installing pipx..."
    if command -v brew &> /dev/null; then
        brew install pipx
    else
        python3 -m pip install --user pipx
    fi
    pipx ensurepath
fi

# Install zen-cli with pipx
echo "📦 Installing zen-cli package..."
pipx install . --force

# Create config directory
CONFIG_DIR="$HOME/.zen-cli"
mkdir -p "$CONFIG_DIR"

# Check if .env exists
if [ ! -f "$CONFIG_DIR/.env" ]; then
    echo "📝 Setting up configuration..."
    
    # Check for existing .env in various locations
    if [ -f "/Users/wrk/WorkDev/MCP-Dev/zen-mcp-server/.env" ]; then
        echo "📋 Copying existing .env from zen-mcp-server..."
        cp "/Users/wrk/WorkDev/MCP-Dev/zen-mcp-server/.env" "$CONFIG_DIR/.env"
    elif [ -f ".env.example" ]; then
        echo "📋 Creating .env from example..."
        cp ".env.example" "$CONFIG_DIR/.env"
        echo ""
        echo "⚠️  Please edit $CONFIG_DIR/.env and add your API keys:"
        echo "   - GEMINI_API_KEY"
        echo "   - OPENAI_API_KEY"
    else
        echo "⚠️  No .env file found. Creating empty configuration..."
        touch "$CONFIG_DIR/.env"
        echo "# Zen CLI Configuration" > "$CONFIG_DIR/.env"
        echo "GEMINI_API_KEY=your_gemini_api_key_here" >> "$CONFIG_DIR/.env"
        echo "OPENAI_API_KEY=your_openai_api_key_here" >> "$CONFIG_DIR/.env"
        echo ""
        echo "⚠️  Please edit $CONFIG_DIR/.env and add your API keys"
    fi
else
    echo "✅ Configuration already exists at $CONFIG_DIR/.env"
fi

echo ""
echo "✅ Zen CLI installed successfully!"
echo ""

# Check for Claude Code installation and offer template integration
echo "🔍 Checking for Claude Code integration opportunity..."
CLAUDE_CODE_DETECTED=false

if [ -f "$HOME/.claude/config.json" ] || command -v claude-code &> /dev/null || [ -d "$HOME/.claude" ]; then
    CLAUDE_CODE_DETECTED=true
    echo "🤖 Claude Code detected!"
    echo ""
    echo "Zen CLI can integrate with Claude Code to provide enhanced AI development assistance."
    echo "This allows Claude Code to automatically use Zen CLI for complex debugging, architecture"
    echo "decisions, code reviews, and multi-model consensus."
    echo ""
    
    read -p "Would you like to install the Claude Code integration template? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        if [ -f "./install-claude-template.sh" ]; then
            echo "📦 Running Claude Code template installer..."
            bash ./install-claude-template.sh
        else
            echo "⚠️  Template installer not found. Manual installation instructions:"
            echo ""
            echo "1. Add the following to your ~/.claude/CLAUDE.md file:"
            echo "2. See CLAUDE_CODE_TEMPLATE.md for complete integration guide"
            echo "3. Or download and run: https://github.com/WKassebaum/zen-mcp-server/blob/v2.0/install-claude-template.sh"
        fi
    else
        echo ""
        echo "💡 You can install Claude Code integration later by running:"
        echo "   ./install-claude-template.sh"
        echo ""
        echo "📖 See CLAUDE_CODE_TEMPLATE.md for manual integration instructions"
    fi
    echo ""
fi

echo "To get started with Zen CLI:"
echo "  zen --version      # Check installation"
echo "  zen listmodels     # List available AI models"  
echo "  zen chat \"Hello!\"  # Start chatting"

if [ "$CLAUDE_CODE_DETECTED" = true ]; then
    echo ""
    echo "With Claude Code integration:"
    echo "  • Claude Code can automatically use zen debug, zen consensus, etc."
    echo "  • Get second opinions from specialized AI models"
    echo "  • Multi-model consensus for critical decisions"
    echo "  • Enhanced debugging and code review capabilities"
fi

echo ""

# Check if API keys are configured
if grep -q "your_.*_api_key_here" "$CONFIG_DIR/.env" 2>/dev/null; then
    echo "⚠️  Don't forget to add your API keys to $CONFIG_DIR/.env"
    echo "   Required: GEMINI_API_KEY and/or OPENAI_API_KEY"
fi

echo ""
