#!/bin/bash

# Quick install script for Zen CLI
# Uses --user flag to avoid PEP 668 issues on macOS

echo "🚀 Zen CLI Quick Install (User Directory)"
echo "========================================="

# Install to user directory
echo "Installing to user directory (~/.local)..."
pip3 install --user -e .

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo "⚠️  IMPORTANT: Add ~/.local/bin to your PATH"
    echo ""
    echo "Add this to your ~/.bashrc or ~/.zshrc:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "Then reload your shell:"
    echo "  source ~/.zshrc  # or ~/.bashrc"
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "Set your API key:"
echo "  export GEMINI_API_KEY='your-key-here'"
echo ""
echo "Test with:"
echo "  zen --version"