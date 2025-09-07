# Zen CLI Installation Guide

## Quick Install (Recommended)

### Option 1: Install from GitHub (Latest)
```bash
# Clone the repository
git clone https://github.com/WKassebaum/zen-mcp-server.git zen-cli
cd zen-cli

# Install with pip (user install)
pip3 install --user .

# Or for development (editable install)
pip3 install --user -e .

# Add to PATH if needed (macOS/Linux)
export PATH="$PATH:$HOME/.local/bin"

# For macOS with Python 3.11+
export PATH="$PATH:$HOME/Library/Python/3.11/bin"
```

### Option 2: Direct pip install from GitHub
```bash
# Install directly from GitHub
pip3 install --user git+https://github.com/WKassebaum/zen-mcp-server.git@v5.13.0

# Add to PATH
export PATH="$PATH:$HOME/.local/bin"
```

## Configuration

After installation, configure your API keys:

```bash
# Interactive configuration wizard
zen configure

# Or set environment variables
export GEMINI_API_KEY="your_gemini_api_key"
export OPENAI_API_KEY="your_openai_api_key"
export OPENROUTER_API_KEY="your_openrouter_key"  # Optional
export XAI_API_KEY="your_xai_key"  # Optional
```

## Verify Installation

```bash
# Check version
zen --version

# List available models
zen listmodels

# Test with a simple command
zen chat "Hello, how are you?"
```

## Troubleshooting

### Command Not Found

If `zen` command is not found after installation:

1. **Check installation location:**
```bash
# Find where zen was installed
find ~/.local -name zen 2>/dev/null
find ~/Library/Python -name zen 2>/dev/null
pip3 show -f zen-cli | grep zen$
```

2. **Add to PATH permanently:**
```bash
# For bash
echo 'export PATH="$PATH:$HOME/.local/bin"' >> ~/.bashrc
source ~/.bashrc

# For zsh (macOS default)
echo 'export PATH="$PATH:$HOME/.local/bin"' >> ~/.zshrc
echo 'export PATH="$PATH:$HOME/Library/Python/3.11/bin"' >> ~/.zshrc
source ~/.zshrc
```

3. **Alternative: Create alias:**
```bash
# Find the actual zen path
ZEN_PATH=$(find ~/.local -name zen -type f -perm +111 2>/dev/null | head -1)
# Or for macOS
ZEN_PATH=$(find ~/Library/Python -name zen -type f -perm +111 2>/dev/null | head -1)

# Add alias
echo "alias zen='$ZEN_PATH'" >> ~/.zshrc
source ~/.zshrc
```

### Missing Dependencies

```bash
# Install all required dependencies
pip3 install --user typer rich pyyaml httpx pydantic python-dotenv google-generativeai openai redis tiktoken
```

### Permission Issues

```bash
# If you get permission errors, use --user flag
pip3 install --user zen-cli

# Or use pipx for isolated install
pipx install git+https://github.com/WKassebaum/zen-mcp-server.git
```

## Docker Alternative

If you prefer not to install locally, use Docker:

```bash
# Create Dockerfile
cat > Dockerfile <<'EOF'
FROM python:3.11-slim
RUN pip install git+https://github.com/WKassebaum/zen-mcp-server.git@v5.13.0
ENV GEMINI_API_KEY=${GEMINI_API_KEY}
ENV OPENAI_API_KEY=${OPENAI_API_KEY}
ENTRYPOINT ["zen"]
EOF

# Build and run
docker build -t zen-cli .
docker run -it --rm \
  -e GEMINI_API_KEY="$GEMINI_API_KEY" \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  zen-cli chat "Hello"
```

## System Requirements

- Python 3.11 or higher
- pip or pipx
- At least one API key (Gemini, OpenAI, OpenRouter, or XAI)

## Uninstall

```bash
# Uninstall zen-cli
pip3 uninstall zen-cli

# Or if installed with pipx
pipx uninstall zen-cli
```