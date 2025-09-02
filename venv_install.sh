#!/bin/bash

# Virtual environment install script for Zen CLI
# Cleanest approach for macOS with PEP 668 protection

echo "🚀 Zen CLI Virtual Environment Install"
echo "======================================"

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv zen-venv

# Activate it
echo "Activating virtual environment..."
source zen-venv/bin/activate

# Install zen-cli
echo "Installing Zen CLI..."
if pip install -e .; then
    echo "✅ Zen CLI installed successfully!"
else
    echo "❌ Installation failed. Check the error messages above."
    exit 1
fi

# Create activation script
cat > activate_zen.sh << 'EOF'
#!/bin/bash
# Activate Zen CLI environment
source "$(dirname "$0")/zen-venv/bin/activate"
echo "✅ Zen CLI environment activated"
echo "You can now use: zen --help"
EOF

chmod +x activate_zen.sh

echo ""
echo "✅ Installation complete!"
echo ""
echo "To use Zen CLI, you have two options:"
echo ""
echo "Option 1: Activate each time (recommended):"
echo "  source zen-venv/bin/activate"
echo "  zen --help"
echo ""
echo "Option 2: Use the helper script:"
echo "  ./activate_zen.sh"
echo "  zen --help"
echo ""
echo "Don't forget to set your API key:"
echo "  export GEMINI_API_KEY='your-key-here'"