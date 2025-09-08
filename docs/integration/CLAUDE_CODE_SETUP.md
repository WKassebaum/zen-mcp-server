# Claude Code + Zen CLI Integration Setup

Quick setup guide for installing Zen CLI with Claude Code integration.

## 🚀 Quick Installation

### Option 1: Automated Installation (Recommended)

```bash
# Clone the repository
git clone https://github.com/WKassebaum/zen-mcp-server.git zen-cli
cd zen-cli
git checkout v2.0

# Run the installer (will auto-detect Claude Code)
./install.sh

# Follow the prompts to install Claude Code integration
```

The installer will:
- ✅ Install Zen CLI with pipx
- ✅ Detect if Claude Code is installed
- ✅ Offer to install the integration template
- ✅ Add the template to your `~/.claude/CLAUDE.md`

### Option 2: Manual Template Installation

If you already have Zen CLI installed:

```bash
# Install just the Claude Code template
./install-claude-template.sh
```

### Option 3: Direct from GitHub

```bash
# Install Zen CLI directly from GitHub
pipx install git+https://github.com/WKassebaum/zen-mcp-server.git@v2.0

# Download and run template installer
curl -sSL https://raw.githubusercontent.com/WKassebaum/zen-mcp-server/v2.0/install-claude-template.sh | bash
```

## 📋 Prerequisites

- **Python 3.11+**
- **pipx** (will be installed automatically if missing)
- **Claude Code** (https://claude.ai/code)
- **API Keys** for at least one provider:
  - Gemini: `GEMINI_API_KEY`
  - OpenAI: `OPENAI_API_KEY`

## ✅ Verification

After installation, verify everything works:

```bash
# Test Zen CLI
zen --version
zen listmodels

# Test basic functionality
zen chat "Hello, this is a test from Claude Code integration!"

# Test with Claude Code
# Start a new Claude Code session and ask it to debug something complex
# Claude Code should automatically use zen debug, zen consensus, etc.
```

## 🔧 API Key Setup

Set your API keys in environment variables:

```bash
# Add to your ~/.zshrc or ~/.bashrc
export GEMINI_API_KEY="your-gemini-key-here"
export OPENAI_API_KEY="your-openai-key-here"

# Reload your shell
source ~/.zshrc  # or ~/.bashrc
```

## 🎯 What the Integration Does

Once installed, Claude Code will automatically:

### 🔍 Use zen debug when stuck on complex bugs
```
User: "Help debug this authentication issue..."
Claude: *internally runs zen debug with relevant files*
Claude: "I've analyzed this with specialized debugging AI..."
```

### 🏗️ Use zen consensus for architectural decisions
```
User: "Should we use microservices or monolith?"
Claude: *runs zen consensus with multiple AI models*
Claude: "After consulting multiple AI experts, here's the consensus..."
```

### 🛡️ Use zen codereview for security reviews
```
User: "Review this authentication code for security issues"
Claude: *runs zen codereview --type security*
Claude: "Security analysis reveals these concerns..."
```

### 💡 Use zen chat for second opinions
```
Claude: *when confidence < 80% on technical decisions*
Claude: *runs zen chat "validation question"*
Claude: "Let me validate this approach..." 
```

## 🎮 Manual Usage Examples

You can also use Zen CLI directly:

```bash
# Quick consultation
zen chat "Is Redis appropriate for session storage at our scale?"

# Debug with context
zen debug "OAuth tokens not persisting" --files auth.py,session.py

# Multi-model consensus
zen consensus "GraphQL vs REST for our API?" --models gemini-pro,o3

# Code review
zen codereview --files src/auth/*.py --type security

# Architecture analysis
zen analyze --files src/ --analysis-type architecture
```

## 📖 Full Documentation

- **ADVANCED_README.md** - Complete technical documentation
- **CLAUDE_CODE_TEMPLATE.md** - Detailed integration guide
- **README.md** - User guide and installation instructions

## 🆘 Troubleshooting

### Template Not Working?
```bash
# Check if template is installed
grep -n "Zen CLI Integration" ~/.claude/CLAUDE.md

# Reinstall template
./install-claude-template.sh
```

### Zen CLI Not Found?
```bash
# Check if zen is in PATH
which zen

# Add pipx to PATH
pipx ensurepath

# Restart terminal and try again
```

### API Keys Not Working?
```bash
# Check if keys are set
echo $GEMINI_API_KEY
echo $OPENAI_API_KEY

# Test directly
zen listmodels  # Should show available models
```

## 🎉 Success Indicators

You'll know it's working when:
- ✅ `zen --version` shows v2.0+
- ✅ `zen listmodels` shows available AI models  
- ✅ Claude Code mentions "consulting specialized AI" or "getting validation"
- ✅ You see zen commands being executed in Claude Code sessions
- ✅ Claude Code provides more detailed technical analysis

---

**Ready to use!** 🚀 Your Claude Code sessions now have access to multiple specialized AI models through Zen CLI integration.