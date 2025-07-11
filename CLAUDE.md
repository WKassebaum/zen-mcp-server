# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Zen MCP Server** is a Model Context Protocol (MCP) server that acts as an AI orchestration hub, enabling Claude to delegate tasks to specialized AI models (Gemini, OpenAI O3) for enhanced code analysis and problem-solving. The server maintains conversation threading across different AI tools while Claude remains the primary coordinator.

## Development Commands

### Testing
```bash
# Run unit tests (no API keys required)
python -m pytest tests/ -v

# Run simulation tests (requires API keys)
python communication_simulator_test.py

# Run specific test file
python -m pytest tests/test_providers.py -v
```

### Code Quality
```bash
# Format and lint code
black . && isort . && ruff check .

# Individual commands
black .                    # Format code
isort .                    # Sort imports  
ruff check .              # Lint code
```

### Docker Development
```bash
# Start all services (Redis + MCP Server)
docker-compose up -d

# View server logs
docker-compose logs -f zen-mcp

# Stop services
docker-compose down

# Rebuild after code changes
docker-compose up --build -d
```

## Architecture Overview

### Core Components

1. **MCP Server** (`server.py`): Main protocol handler managing JSON-RPC communication and tool routing
2. **Provider Layer** (`providers/`): Abstraction for AI models with unified interface and capability management
3. **Tool System** (`tools/`): Specialized AI-powered tools with distinct expertise areas
4. **Conversation Memory** (`utils/conversation_memory.py`): Redis-based threading for cross-tool context preservation

### Provider Abstraction

The `providers/` directory implements a clean abstraction layer:
- `base.py`: Defines `ModelProvider` interface and model capabilities
- `registry.py`: Handles dynamic provider discovery and instantiation
- Each provider (Gemini, OpenAI) implements standardized methods with model-specific constraints

### Tool Architecture

Tools in `tools/` inherit from `BaseTool` and implement:
- `get_system_prompt()`: Tool-specific expertise definition
- `process_request()`: Main processing logic with file handling
- Automatic conversation threading and token management

### Key Utilities

- `conversation_memory.py`: Redis-based threading with 1-hour expiry
- `file_utils.py`: Intelligent file reading with token budgets
- `token_utils.py`: Model-aware token counting and management
- `model_context.py`: Model-specific context handling and limits

## Configuration

### Environment Variables
```bash
GEMINI_API_KEY          # Google AI Studio API key
OPENAI_API_KEY          # OpenAI Platform API key
DEFAULT_MODEL=auto      # Auto-selection or specific model
REDIS_URL              # Redis connection (defaults to localhost:6379)
WORKSPACE_ROOT         # File access root (defaults to $HOME)
LOG_LEVEL=INFO         # Logging verbosity
```

### Model Selection Strategy
- `auto`: Claude intelligently selects optimal model per task
- `gemini-2.5-pro`: Deep analysis and complex reasoning
- `gemini-2.5-flash`: Fast responses and code assistance
- `o3-mini`: Logical reasoning and problem-solving

## Development Notes

### Adding New Tools
1. Create new file in `tools/` inheriting from `BaseTool`
2. Implement required methods with specialized system prompts
3. Tools are auto-discovered via `tools/__init__.py`

### Adding New Providers
1. Implement `ModelProvider` interface in `providers/`
2. Define model capabilities and constraints
3. Register in `providers/registry.py`

### Conversation Threading
Tools automatically access conversation history through `self.conversation_memory`. Context persists across tool switches, enabling complex multi-turn workflows where Claude can delegate different tasks to different tools while maintaining full context.

### File Processing
Use `self._read_files_with_budget()` for intelligent file handling that:
- Respects token budgets per model
- Avoids re-processing files already in conversation
- Handles large files through MCP's file mechanism

### Testing Strategy
- Unit tests focus on core logic without API calls
- Simulation tests validate end-to-end workflows with real APIs
- Provider tests use mocking for consistent results