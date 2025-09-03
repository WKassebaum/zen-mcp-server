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
echo "To get started:"
echo "  zen --version      # Check installation"
echo "  zen listmodels     # List available AI models"
echo "  zen chat \"Hello!\"  # Start chatting"
echo ""

# Check if API keys are configured
if grep -q "your_.*_api_key_here" "$CONFIG_DIR/.env" 2>/dev/null; then
    echo "⚠️  Don't forget to add your API keys to $CONFIG_DIR/.env"
fi
