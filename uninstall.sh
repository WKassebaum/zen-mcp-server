#!/bin/bash

# Zen CLI Uninstallation Script
# This script removes the Zen CLI and optionally cleans up configuration

set -e

echo "🗑️  Zen CLI Uninstallation"
echo "========================"

# Uninstall the package
echo "📦 Removing Zen CLI package..."
if pip show zen-cli > /dev/null 2>&1; then
    pip uninstall -y zen-cli
    echo "✅ Package removed"
else
    echo "⚠️  Package not found (may already be uninstalled)"
fi

# Ask about configuration
echo ""
read -p "Remove configuration directory ~/.zen? (y/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ -d ~/.zen ]; then
        rm -rf ~/.zen
        echo "✅ Configuration removed"
    else
        echo "⚠️  Configuration directory not found"
    fi
else
    echo "ℹ️  Configuration preserved at ~/.zen"
fi

# Check if command still exists
echo ""
if command -v zen > /dev/null 2>&1; then
    echo "⚠️  Warning: 'zen' command still found in PATH"
    echo "   This might be from a different installation"
    echo "   Location: $(which zen)"
else
    echo "✅ 'zen' command removed from PATH"
fi

echo ""
echo "Uninstallation complete!"
echo ""
echo "Note: API keys in environment variables were not modified."
echo "Remove them from your shell config if no longer needed:"
echo "  - GEMINI_API_KEY"
echo "  - OPENAI_API_KEY"
echo "  - OPENROUTER_API_KEY"
echo "  - XAI_API_KEY"