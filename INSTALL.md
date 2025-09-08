# Zen CLI Installation Guide

## 🚨 For "externally-managed-environment" Error

If you get this error, your Python is managed by Homebrew/system package manager. **Use one of these solutions:**

### Option 1: pipx (Recommended - Easiest)
```bash
# Install pipx if you don't have it
brew install pipx

# Install zen-cli with pipx (handles virtual env automatically)
pipx install git+https://github.com/WKassebaum/zen-mcp-server.git@v5.13.0

# Verify installation
zen --version
```

### Option 2: Virtual Environment (Development)
```bash
# Clone and create virtual environment
git clone https://github.com/WKassebaum/zen-mcp-server.git zen-cli
cd zen-cli

# Create and activate virtual environment
python3 -m venv zen-venv
source zen-venv/bin/activate  # On Windows: zen-venv\Scripts\activate

# Install in virtual environment
pip install -e .

# Add alias for easy access (add to ~/.zshrc or ~/.bashrc)
echo "alias zen='$(pwd)/zen-venv/bin/zen'" >> ~/.zshrc
source ~/.zshrc
```

### Option 3: Force Install (If Other Options Don't Work)
```bash
# Clone the repository
git clone https://github.com/WKassebaum/zen-mcp-server.git zen-cli
cd zen-cli

# Force install with --break-system-packages (requires BOTH flags)
pip3 install --user --break-system-packages -e .

# Add to PATH (check your Python version first: python3 --version)
export PATH="$PATH:$HOME/Library/Python/3.13/bin"  # Adjust version as needed

# Make PATH permanent
echo 'export PATH="$PATH:$HOME/Library/Python/3.13/bin"' >> ~/.zshrc
source ~/.zshrc
```

## Legacy Install (If Above Don't Work)

### Option 4: System Python
```bash
# If you have system Python (not Homebrew)
pip3 install --user git+https://github.com/WKassebaum/zen-mcp-server.git@v5.13.0
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

### "externally-managed-environment" Specific Fixes

If `--break-system-packages` didn't work, try these:

```bash
# 1. Make sure you use BOTH flags together
pip3 install --user --break-system-packages -e .

# 2. Check if pip.conf is blocking it
ls ~/.pip/pip.conf ~/.config/pip/pip.conf
# If these exist, temporarily rename them and try again

# 3. Use correct Python version
which python3
python3 --version
# Then use the specific version: pip3.13 instead of pip3

# 4. Force with specific Python
/opt/homebrew/bin/python3 -m pip install --user --break-system-packages -e .
```

### Permission Issues

```bash
# If you get permission errors, use --user flag
pip3 install --user zen-cli

# Or use pipx for isolated install (RECOMMENDED)
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