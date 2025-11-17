# Getting Started with Zen MCP Server

This guide walks you through setting up the Zen MCP Server from scratch, including installation, configuration, and first usage.

## Prerequisites

- **Python 3.10+** (3.12 recommended)
- **Git**
- **[uv installed](https://docs.astral.sh/uv/getting-started/installation/)** (for uvx method)
- **Windows users**: WSL2 required for Claude Code CLI

## Step 1: Get API Keys

You need at least one API key. Choose based on your needs:

### Option A: OpenRouter (Recommended for beginners)
**One API for multiple models**
- Visit [OpenRouter](https://openrouter.ai/) and sign up
- Generate an API key
- Control spending limits in your dashboard
- Access GPT-4, Claude, Gemini, and more through one API

### Option B: Native Provider APIs

**Gemini (Google):**
- Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
- Generate an API key
- **Note**: For Gemini 2.5 Pro, use a paid API key (free tier has limited access)

**OpenAI:**
- Visit [OpenAI Platform](https://platform.openai.com/api-keys)
- Generate an API key for O3, GPT-5 access

**X.AI (Grok):**
- Visit [X.AI Console](https://console.x.ai/)
- Generate an API key for Grok models

**DIAL Platform:**
- Visit [DIAL Platform](https://dialx.ai/)
- Generate API key for vendor-agnostic model access

### Option C: Local Models (Free)

**Ollama:**
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
ollama serve

# Pull a model (e.g., Llama 3.2)
ollama pull llama3.2
```

**Other local options:**
- **vLLM**: Self-hosted inference server
- **LM Studio**: Local model hosting with OpenAI-compatible API
- **Text Generation WebUI**: Popular local interface

👉 **[Complete custom model setup guide](custom_models.md)**

## Step 2: Installation

Choose your preferred installation method:

### Method A: Instant Setup with uvx (Recommended)

**Prerequisites**: [Install uv first](https://docs.astral.sh/uv/getting-started/installation/)

Choose your AI coding assistant and add the corresponding configuration:

**For Claude Desktop:**
1. Open Claude Desktop → Settings → Developer → Edit Config
2. Add this configuration:

```json
{
  "mcpServers": {
    "zen": {
      "command": "sh",
      "args": [
        "-c", 
        "for p in $(which uvx 2>/dev/null) $HOME/.local/bin/uvx /opt/homebrew/bin/uvx /usr/local/bin/uvx uvx; do [ -x \"$p\" ] && exec \"$p\" --from git+https://github.com/BeehiveInnovations/zen-mcp-server.git zen-mcp-server; done; echo 'uvx not found' >&2; exit 1"
      ],
      "env": {
        "PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:~/.local/bin",
        "GEMINI_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

**For Claude Code CLI:**
Create `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "zen": {
      "command": "sh", 
      "args": [
        "-c",
        "for p in $(which uvx 2>/dev/null) $HOME/.local/bin/uvx /opt/homebrew/bin/uvx /usr/local/bin/uvx uvx; do [ -x \"$p\" ] && exec \"$p\" --from git+https://github.com/BeehiveInnovations/zen-mcp-server.git zen-mcp-server; done; echo 'uvx not found' >&2; exit 1"
      ],
      "env": {
        "PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:~/.local/bin",
        "GEMINI_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

**For Gemini CLI:**
Edit `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "zen": {
      "command": "sh",
      "args": [
        "-c",
        "for p in $(which uvx 2>/dev/null) $HOME/.local/bin/uvx /opt/homebrew/bin/uvx /usr/local/bin/uvx uvx; do [ -x \"$p\" ] && exec \"$p\" --from git+https://github.com/BeehiveInnovations/zen-mcp-server.git zen-mcp-server; done; echo 'uvx not found' >&2; exit 1"  
      ],
      "env": {
        "PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:~/.local/bin",
        "GEMINI_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

**For Codex CLI:**
Edit `~/.codex/config.toml`:

```toml
[mcp_servers.zen]
command = "bash"
args = ["-c", "for p in $(which uvx 2>/dev/null) $HOME/.local/bin/uvx /opt/homebrew/bin/uvx /usr/local/bin/uvx uvx; do [ -x \\\"$p\\\" ] && exec \\\"$p\\\" --from git+https://github.com/BeehiveInnovations/zen-mcp-server.git zen-mcp-server; done; echo 'uvx not found' >&2; exit 1"]
tool_timeout_sec = 1200  # 20 minutes; added automatically by the setup script so upstream providers can respond

[mcp_servers.zen.env]
PATH = "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:$HOME/.local/bin:$HOME/.cargo/bin:$HOME/bin"
GEMINI_API_KEY = "your_api_key_here"
```

Enable Codex's built-in web-search tool so Zen's `apilookup` instructions can execute successfully:

```toml
[tools]
web_search = true
```

Add the block above if `[tools]` is missing from the file; otherwise ensure `web_search = true` appears in that section.


**For Qwen Code CLI:**
Create or edit `~/.qwen/settings.json`:

```json
{
  "mcpServers": {
    "zen": {
      "command": "bash",
      "args": [
        "-c",
        "for p in $(which uvx 2>/dev/null) $HOME/.local/bin/uvx /opt/homebrew/bin/uvx /usr/local/bin/uvx uvx; do [ -x \"$p\" ] && exec \"$p\" --from git+https://github.com/BeehiveInnovations/zen-mcp-server.git zen-mcp-server; done; echo 'uvx not found' >&2; exit 1"
      ],
      "cwd": "/path/to/zen-mcp-server",
      "env": {
        "PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:~/.local/bin",
        "GEMINI_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

Replace the placeholder API key with the providers you use (Gemini, OpenAI, OpenRouter, etc.).

**For OpenCode CLI:**
Edit `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "zen": {
      "type": "local",
      "command": [
        "/path/to/zen-mcp-server/.zen_venv/bin/python",
        "/path/to/zen-mcp-server/server.py"
      ],
      "cwd": "/path/to/zen-mcp-server",
      "enabled": true,
      "environment": {
        "GEMINI_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

Add any other API keys you rely on (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, etc.).

#### IDE Clients (Cursor & VS Code)

Zen works in GUI IDEs that speak MCP. The configuration mirrors the CLI examples above—point the client at the `uvx` launcher and set any required environment variables.

**Cursor IDE**

1. Open Cursor → `Settings` (`Cmd+,`/`Ctrl+,`) → **Integrations › Model Context Protocol (MCP)**.
2. Click **Add MCP Server** and supply the following values:
   - Command: `sh`
   - Args: `-c` and `for p in $(which uvx 2>/dev/null) $HOME/.local/bin/uvx /opt/homebrew/bin/uvx /usr/local/bin/uvx uvx; do [ -x "$p" ] && exec "$p" --from git+https://github.com/BeehiveInnovations/zen-mcp-server.git zen-mcp-server; done; echo 'uvx not found' >&2; exit 1`
   - Environment (example):
     - `PATH=/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:~/.local/bin`
     - `GEMINI_API_KEY=your_api_key_here`
3. Save the configuration—Cursor will launch the MCP server on demand. See the [Cursor MCP guide](https://cursor.com/docs) for screenshots of the UI.

**Visual Studio Code (Claude Dev extension)**

1. Install the [Claude Dev extension](https://marketplace.visualstudio.com/items?itemName=Anthropic.claude-vscode) v0.6.0 or later.
2. Open the Command Palette (`Cmd+Shift+P`/`Ctrl+Shift+P`) → **Claude: Configure MCP Servers** → **Add server**.
3. When prompted, use the same values as above:
   - Command: `sh`
   - Args: `-c` and the `uvx` bootstrap loop
   - Environment: add the API keys you need (e.g. `GEMINI_API_KEY`, `OPENAI_API_KEY`)
4. Save the JSON snippet the extension generates. VS Code will reload the server automatically the next time you interact with Claude.

👉 Pro tip: If you prefer a one-line command, replace the long loop with `uvx --from git+https://github.com/BeehiveInnovations/zen-mcp-server.git zen-mcp-server`—just make sure `uvx` is on your PATH for every client.

**Benefits of uvx method:**
- ✅ Zero manual setup required
- ✅ Always pulls latest version
- ✅ No local dependencies to manage
- ✅ Works without Python environment setup

### Method B: Clone and Setup

```bash
# Clone the repository
git clone https://github.com/BeehiveInnovations/zen-mcp-server.git
cd zen-mcp-server

# One-command setup (handles everything)
./run-server.sh

# Or for Windows PowerShell:
./run-server.ps1

# View configuration for Claude Desktop
./run-server.sh -c

# See all options
./run-server.sh --help
```

**What the setup script does:**
- ✅ Creates Python virtual environment
- ✅ Installs all dependencies  
- ✅ Creates .env file for API keys
- ✅ Configures Claude integrations
- ✅ Provides copy-paste configuration

**After updates:** Always run `./run-server.sh` again after `git pull`.

**Windows users**: See the [WSL Setup Guide](wsl-setup.md) for detailed WSL configuration.

## Step 3: Configure API Keys

### For uvx installation:
Add your API keys directly to the MCP configuration shown above.

### For clone installation:
Edit the `.env` file:

```bash
nano .env
```

Add your API keys (at least one required):
```env
# Choose your providers (at least one required)
GEMINI_API_KEY=your-gemini-api-key-here      # For Gemini models  
OPENAI_API_KEY=your-openai-api-key-here      # For O3, GPT-5
XAI_API_KEY=your-xai-api-key-here            # For Grok models
OPENROUTER_API_KEY=your-openrouter-key       # For multiple models

# DIAL Platform (optional)
DIAL_API_KEY=your-dial-api-key-here
DIAL_API_HOST=https://core.dialx.ai          # Default host (optional)
DIAL_API_VERSION=2024-12-01-preview          # API version (optional) 
DIAL_ALLOWED_MODELS=o3,gemini-2.5-pro       # Restrict models (optional)

# Custom/Local models (Ollama, vLLM, etc.)
CUSTOM_API_URL=http://localhost:11434/v1     # Ollama example
CUSTOM_API_KEY=                              # Empty for Ollama
CUSTOM_MODEL_NAME=llama3.2                   # Default model name
```

## Prevent Client Timeouts

Some MCP clients default to short timeouts and can disconnect from Zen during long tool runs. Configure each client with a generous ceiling (we recommend at least five minutes); the Zen setup script now writes a 20-minute tool timeout for Codex so upstream providers contacted by the server have time to respond.

### Claude Code & Claude Desktop

Claude reads MCP-related environment variables either from your shell or from `~/.claude/settings.json`. Add (or update) the `env` block so both startup and tool execution use a 5-minute limit:

```json
{
  "env": {
    "MCP_TIMEOUT": "300000",
    "MCP_TOOL_TIMEOUT": "300000"
  }
}
```

You can scope this block at the top level of `settings.json` (applies to every session) or under a specific `mcpServers.<name>.env` entry if you only want it for Zen. The values are in milliseconds. Note: Claude’s SSE transport still enforces an internal ceiling of roughly five minutes; long-running HTTP/SSE servers may need retries until Anthropic ships their fix.

### Codex CLI

Codex exposes per-server timeouts in `~/.codex/config.toml`. Add (or bump) these keys under `[[mcp_servers.<name>]]`:

```toml
[mcp_servers.zen]
command = "..."
args = ["..."]
startup_timeout_sec = 300    # default is 10 seconds
tool_timeout_sec = 1200      # default is 60 seconds; setup script pre-populates 20 minutes so upstream providers can respond
```

`startup_timeout_sec` covers the initial handshake/list tools step, while `tool_timeout_sec` governs each tool call. Raise the latter if the providers your MCP server invokes routinely need more than 20 minutes.

### Gemini CLI

Gemini uses a single `timeout` field per server inside `~/.gemini/settings.json`. Set it to at least five minutes (values are milliseconds):

```json
{
  "mcpServers": {
    "zen": {
      "command": "uvx",
      "args": ["zen-mcp-server"],
      "timeout": 300000
    }
  }
}
```

Versions 0.2.1 and newer currently ignore values above ~60 seconds for some transports due to a known regression; if you still see premature disconnects we recommend breaking work into smaller calls or watching the Gemini CLI release notes for the fix.

**Important notes:**
- ⭐ **No restart needed** - Changes take effect immediately 
- ⭐ If multiple APIs configured, native APIs take priority over OpenRouter
- ⭐ Configure model aliases in [`conf/custom_models.json`](../conf/custom_models.json)

## Step 4: Test the Installation

### For Claude Desktop:
1. Restart Claude Desktop
2. Open a new conversation
3. Try: `"Use zen to list available models"`

### For Claude Code CLI:
1. Exit any existing Claude session
2. Run `claude` from your project directory  
3. Try: `"Use zen to chat about Python best practices"`

### For Gemini CLI:
**Note**: While Zen MCP connects to Gemini CLI, tool invocation isn't working correctly yet. See [Gemini CLI Setup](gemini-setup.md) for updates.

### For Qwen Code CLI:
1. Restart the Qwen Code CLI if it's running (`qwen exit`).
2. Run `qwen mcp list --scope user` and confirm `zen` shows `CONNECTED`.
3. Try: `"/mcp"` to inspect available tools or `"Use zen to analyze this repo"`.

### For OpenCode CLI:
1. Restart OpenCode (or run `OpenCode: Reload Config`).
2. Open **Settings › Tools › MCP** and confirm `zen` is enabled.
3. Start a new chat and try: `"Use zen to list available models"`.

### For Codex CLI:
1. Restart Codex CLI if running
2. Open a new conversation
3. Try: `"Use zen to list available models"`

### Test Commands:
```
"Use zen to list available models"
"Chat with zen about the best approach for API design"
"Use zen thinkdeep with gemini pro about scaling strategies"  
"Debug this error with o3: [paste error]"
```

**Note**: Codex CLI provides excellent MCP integration with automatic environment variable configuration when using the setup script.

## Step 5: Start Using Zen

### Via MCP (Claude Code, Cursor, IDE clients)

**Let Claude pick the model:**
```
"Use zen to analyze this code for security issues"
"Debug this race condition with zen"
"Plan the database migration with zen"
```

**Specify the model:**
```
"Use zen with gemini pro to review this complex algorithm"
"Debug with o3 using zen for logical analysis"
"Get flash to quickly format this code via zen"
```

**Multi-model workflows:**
```
"Use zen to get consensus from pro and o3 on this architecture"
"Code review with gemini, then precommit validation with o3"
"Analyze with flash, then deep dive with pro if issues found"
```

### Via Standalone CLI

Want to use `zen` directly from your terminal without MCP server integration? Follow this setup guide.

#### Prerequisites
- **Python 3.10+**
- **Git**
- **API Keys** from at least one provider (see [API Keys Configuration](#api-keys-configuration) above)

#### Installation Steps

**1. Clone the Repository**
```bash
git clone https://github.com/BeehiveInnovations/zen-mcp-server.git
cd zen-mcp-server
```

**2. Run Setup Script**
```bash
# Sets up Python virtual environment, installs dependencies, creates .env file
./run-server.sh
```

**3. Install CLI Tool**
```bash
# Activate virtual environment
source .zen_venv/bin/activate

# Install zen CLI in editable mode
pip install -e .
```

**4. Verify Installation**
```bash
zen --version
# Output: zen, version 9.1.3

zen listmodels
# Shows all available models across configured providers
```

#### Configuration

**After completing the installation steps above**, configure your API keys:

**Option 1: Interactive Setup Wizard (Recommended)**

Run the interactive wizard to configure your API keys:

```bash
# Run the setup wizard
zen setup
```

This wizard will:
- Guide you through configuring API keys
- Create or update `~/.zen/.env` file
- Mask existing API keys for security
- Allow you to update individual keys without re-entering all of them

**Option 2: Manual Configuration**

Zen CLI reads API keys from these sources (in priority order):

1. **System environment variables**
   ```bash
   export GEMINI_API_KEY="your-key-here"
   export OPENAI_API_KEY="your-key-here"
   export XAI_API_KEY="your-key-here"
   ```

2. **~/.zen/.env file** (created by `./run-server.sh` or `zen setup`)
   ```bash
   # Edit this file to add your API keys
   nano ~/.zen/.env
   ```

3. **.env file in current directory**
   ```bash
   # Project-specific API keys
   cp .env.example .env
   nano .env
   ```

#### Usage Examples

```bash
# List all available models
zen listmodels

# Chat with AI
zen chat "Explain REST API best practices" --model gemini-2.5-pro

# Debug an issue
zen debug "OAuth tokens expire after 2 minutes" \
  -f src/auth/oauth.py \
  -f src/middleware/session.py

# Get multi-model consensus
zen consensus "Should we migrate to microservices or stay monolithic?" \
  --models gemini-2.5-pro,gpt-5,o3 \
  -f docs/architecture.md

# Code review
zen codereview -f src/*.py --review-type security

# Architecture analysis
zen analyze -f src/app.py --analysis-type architecture

# Sequential task planning
zen planner "Implement OAuth2 authentication with refresh tokens"

# Pre-commit validation
zen precommit -f src/*.py

# Security audit
zen secaudit -f src/api/*.py --focus auth
```

#### All Available Commands

```bash
zen setup        # Interactive setup wizard for API keys and configuration
zen chat         # General AI consultation and brainstorming
zen debug        # Systematic debugging with hypothesis testing
zen consensus    # Multi-model consensus for complex decisions
zen codereview   # Comprehensive code review with severity levels
zen analyze      # Architecture and code analysis
zen planner      # Sequential task planning for complex goals
zen thinkdeep    # Extended reasoning mode for difficult problems
zen refactor     # Code refactoring suggestions and improvements
zen testgen      # Test generation with edge case coverage
zen precommit    # Pre-commit validation and quality checks
zen secaudit     # Security audit with OWASP analysis
zen tracer       # Code execution flow tracing
zen docgen       # Generate comprehensive documentation
zen clink        # CLI-to-CLI bridge - spawn external AI CLIs
zen apilookup    # Look up API documentation and usage
zen challenge    # Challenge assumptions and explore alternatives
zen listmodels   # List all available AI models
zen --help       # Show full command reference
```

#### Get Help

```bash
# General help
zen --help

# Command-specific help
zen chat --help
zen debug --help
zen consensus --help
```

#### Troubleshooting

**"zen: command not found"**
```bash
# Make sure virtual environment is activated
source .zen_venv/bin/activate

# Verify installation
which zen
# Should show: /path/to/zen-mcp-server/.zen_venv/bin/zen
```

**"No API keys configured"**
```bash
# Check if .env file exists and has keys
cat ~/.zen/.env

# Or set environment variables
export GEMINI_API_KEY="your-key-here"
```

**"Model not available"**
```bash
# List configured models
zen listmodels

# Check provider status and available models
```

👉 **[Load zen-skill](../skills/zen-skill/SKILL.md)** via `Skill(skill="zen-skill")` in Claude Code for comprehensive CLI documentation

### Quick Tool Reference:

**🤝 Collaboration**: `chat`, `thinkdeep`, `planner`, `consensus`
**🔍 Code Analysis**: `analyze`, `codereview`, `debug`, `precommit`  
**⚒️ Development**: `refactor`, `testgen`, `secaudit`, `docgen`
**🔧 Utilities**: `challenge`, `tracer`, `listmodels`, `version`

👉 **[Complete Tools Reference](tools/)** with detailed examples and parameters

## Common Issues and Solutions

### "zen not found" or "command not found"

**For uvx installations:**
- Ensure `uv` is installed and in PATH
- Try: `which uvx` to verify uvx is available
- Check PATH includes `/usr/local/bin` and `~/.local/bin`

**For clone installations:**
- Run `./run-server.sh` again to verify setup
- Check virtual environment: `which python` should show `.zen_venv/bin/python`

### API Key Issues

**"Invalid API key" errors:**
- Verify API keys in `.env` file or MCP configuration
- Test API keys directly with provider's API
- Check for extra spaces or quotes around keys

**"Model not available":**
- Run `"Use zen to list available models"` to see what's configured
- Check model restrictions in environment variables
- Verify API key has access to requested models

### Performance Issues

**Slow responses:**
- Use faster models: `flash` instead of `pro`  
- Lower thinking modes: `minimal` or `low` instead of `high`
- Restrict model access to prevent expensive model selection

**Token limit errors:**
- Use models with larger context windows
- Break large requests into smaller chunks
- See [Working with Large Prompts](advanced-usage.md#working-with-large-prompts)

### More Help

👉 **[Complete Troubleshooting Guide](troubleshooting.md)** with detailed solutions

👉 **[Advanced Usage Guide](advanced-usage.md)** for power-user features

👉 **[Configuration Reference](configuration.md)** for all options

## What's Next?

### Add Zen to Your CLAUDE.md

For best integration with Claude Code and other AI assistants, add Zen MCP integration to your CLAUDE.md files:

**Quick Start (5 minutes):**
```bash
# Copy quick start template to project CLAUDE.md
cat templates/CLAUDE_MD_QUICKSTART.md >> CLAUDE.md
```

**Comprehensive Setup:**
```bash
# For project-specific documentation
cat templates/CLAUDE_MD_USER_TEMPLATE.md >> /path/to/project/CLAUDE.md

# For global configuration
cat templates/CLAUDE_MD_GLOBAL_TEMPLATE.md >> ~/.claude/CLAUDE.md
```

**Templates Available:**
- **Quick Start** (`templates/CLAUDE_MD_QUICKSTART.md`) - Essential tools and patterns
- **Full User Template** (`templates/CLAUDE_MD_USER_TEMPLATE.md`) - Comprehensive reference
- **Global Template** (`templates/CLAUDE_MD_GLOBAL_TEMPLATE.md`) - System-wide configuration

👉 **[Template Guide](../templates/README.md)** for choosing the right template

---

### Continue Learning

🎯 **Try the example workflows in the main README**

📚 **Explore the [Tools Reference](tools/)** to understand what each tool can do

⚡ **Read the [Advanced Usage Guide](advanced-usage.md)** for complex workflows

🔧 **Check out [Configuration Options](configuration.md)** to customize behavior

💡 **Join discussions and get help** in the project issues or discussions

## Quick Configuration Templates

### Development Setup (Balanced)
```env
DEFAULT_MODEL=auto
GEMINI_API_KEY=your-key
OPENAI_API_KEY=your-key
GOOGLE_ALLOWED_MODELS=flash,pro
OPENAI_ALLOWED_MODELS=o4-mini,o3-mini
```

### Cost-Optimized Setup
```env  
DEFAULT_MODEL=flash
GEMINI_API_KEY=your-key
GOOGLE_ALLOWED_MODELS=flash
```

### High-Performance Setup  
```env
DEFAULT_MODEL=auto
GEMINI_API_KEY=your-key
OPENAI_API_KEY=your-key
GOOGLE_ALLOWED_MODELS=pro
OPENAI_ALLOWED_MODELS=o3
```

### Local-First Setup
```env
DEFAULT_MODEL=auto
CUSTOM_API_URL=http://localhost:11434/v1
CUSTOM_MODEL_NAME=llama3.2
# Add cloud APIs as backup
GEMINI_API_KEY=your-key
```

Happy coding with your AI development team! 🤖✨
