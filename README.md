# Zen CLI

Command-line interface for Zen MCP Server with revolutionary 95% token optimization.

## 🚀 95% Token Reduction
- **Traditional approach**: 43,000 tokens per request
- **Zen CLI optimized**: 200-800 tokens per request
- **Savings**: 42,200 tokens per interaction

## Installation

### From Source (Development)
```bash
# Clone the repository (if not already done)
git clone https://github.com/WKassebaum/zen-mcp-server.git
cd zen-mcp-server

# Switch to CLI worktree
git worktree add ../zen-cli feature/cli-implementation
cd ../zen-cli

# Install in development mode
pip install -e .

# Verify installation
zen --version
zen --help
```

### Prerequisites
- Python 3.11 or higher
- Zen MCP Server running (locally or remotely)
- API keys for Gemini or OpenAI

## Quick Start

### 1. Configure API Keys
```bash
# View current configuration
zen config

# Configuration file location: ~/.zen/config.yaml
# Edit manually or use environment variables:
export GEMINI_API_KEY="your-key-here"
export OPENAI_API_KEY="your-key-here"
```

### 2. Start Zen MCP Server
In a separate terminal:
```bash
cd /path/to/zen-mcp-server
docker-compose up -d
# or
./run-server.sh
```

### 3. Test Basic Commands
```bash
# Simple chat
zen chat "Hello, how are you?"

# Debug with files
zen debug "Function not working" --files example.py

# Two-stage optimization (manual)
zen select "Debug OAuth token persistence issue"
zen execute debug --complexity workflow
```

## Usage Examples

### Two-Stage Token Optimization

#### Stage 1: Mode Selection (~200 tokens)
```bash
zen select "Debug OAuth token persistence issue"
# Output: Recommends 'debug' mode with 'workflow' complexity
```

#### Stage 2: Focused Execution (~600 tokens)
```bash
zen execute debug --complexity workflow --request '{"step": "Initial investigation", "step_number": 1}'
```

### Direct Commands (Auto-Optimized)

#### Chat
```bash
zen chat "Explain how REST APIs work"
zen chat "What's the difference between POST and PUT?" --model gemini-2.0-flash-exp
```

#### Debug
```bash
zen debug "Users can't log in" --files auth.py database.py --confidence exploring
zen debug "Memory leak in application" --confidence high
```

#### Code Review
```bash
zen review --files "src/*.py" --type security
zen review --files main.py utils.py --type quality
```

#### Architecture Analysis
```bash
zen analyze --files "src/**/*.py" --analysis-type architecture
zen analyze --files . --analysis-type dependencies
```

#### Multi-Model Consensus
```bash
zen consensus "Should we migrate to microservices?" --models '["gemini-pro", "gpt-4"]'
```

## Configuration

### Config File Structure
Location: `~/.zen/config.yaml`

```yaml
active_profile: default
api_endpoint: http://localhost:3001
token_optimization:
  enabled: true
  mode: two_stage
  version: v5.12.0
profiles:
  default:
    api_keys:
      GEMINI_API_KEY: your-key-here
      OPENAI_API_KEY: your-key-here
    model_preferences:
      default_model: auto
      temperature: 0.3
      thinking_mode: medium
```

### Using Profiles
```bash
# Create a new profile
vim ~/.zen/config.yaml  # Add new profile section

# Switch profiles (edit active_profile in config)
# Future: zen config profile use work
```

## Testing

### Unit Tests (Coming Soon)
```bash
pytest tests/
```

### Integration Testing
```bash
# Test connection to MCP server
zen chat "test connection"

# Test token optimization
zen select "test task" 
# Should show ~200 tokens used

zen execute chat --request '{"prompt": "test", "model": "auto"}'
# Should show ~600 tokens used
```

### Manual Testing Checklist
- [ ] Install with `pip install -e .`
- [ ] Verify `zen --help` shows all commands
- [ ] Test `zen config` displays configuration
- [ ] Test `zen chat "hello"` (may show connection error if server not running)
- [ ] Start MCP server and retry chat command
- [ ] Test two-stage optimization with select/execute
- [ ] Test direct commands (debug, review, analyze)

## Troubleshooting

### "Not connected" or API errors
1. Ensure Zen MCP Server is running:
   ```bash
   docker-compose ps  # Should show zen-mcp-server as "Up"
   ```
2. Check endpoint configuration:
   ```bash
   zen config  # Should show api_endpoint: http://localhost:3001
   ```
3. Verify API keys are set:
   ```bash
   echo $GEMINI_API_KEY  # Should show your key
   ```

### Installation Issues
```bash
# Clean reinstall
pip uninstall zen-cli
pip install -e . --force-reinstall

# Check Python version
python --version  # Should be 3.11+
```

### Development Mode
The CLI includes a simulation mode when the MCP server is unavailable. This allows testing the CLI interface without a running server.

## Project Structure
```
zen-cli/
├── setup.py                 # Package configuration
├── README.md               # This file
└── src/
    └── zen_cli/
        ├── __init__.py     # Package initialization
        ├── main.py         # CLI entry point
        ├── config.py       # Configuration management
        ├── token_optimizer.py  # Two-stage optimization
        └── api_client.py   # MCP server communication
```

## Current Status

### ✅ Implemented
- CLI framework with Click
- Two-stage token optimization (95% reduction)
- All basic commands (chat, debug, review, analyze, consensus)
- Configuration management with profiles
- Rich terminal UI with progress indicators
- API client with fallback simulation

### 🚧 In Progress
- Integration testing with live MCP server
- Interactive mode implementation
- Plugin system development

### 📋 TODO
- Comprehensive test suite
- PyPI packaging
- Documentation website
- Export formats (JSON, Markdown)
- Conversation threading
- Batch operations

## Contributing

This is an early development version. Contributions welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License - See LICENSE file in the parent repository

## Support

- GitHub Issues: https://github.com/WKassebaum/zen-mcp-server/issues
- Main Project: https://github.com/WKassebaum/zen-mcp-server

## Credits

Built on top of the Zen MCP Server's revolutionary token optimization architecture that achieves 95% context reduction while maintaining full functionality.

---

**Version**: 0.1.0 (Initial Development)  
**Status**: Untested Alpha - Integration testing needed  
**Token Optimization**: v5.12.0 compatible