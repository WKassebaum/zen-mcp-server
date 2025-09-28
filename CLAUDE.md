# CLAUDE.md - Zen CLI Project Instructions

## Project Overview
Zen CLI is a production-ready standalone command-line interface that implements all Zen MCP Server features directly without requiring an MCP server. It provides AI-powered development assistance with 95% token optimization, enterprise-grade multi-backend storage, and comprehensive project management.

## Current Status (Post-Autonomous Development Session)
✅ **Production Ready**: Enterprise-grade CLI with comprehensive feature set
✅ **Multi-Backend Storage**: File, Redis, and In-Memory storage with graceful fallback
✅ **Project Management**: Full project isolation with per-project configuration
✅ **Configuration System**: Hierarchical config with environment overrides
✅ **CLI UX Excellence**: Interactive mode, session continuity, output formatting
✅ **Test Infrastructure**: Comprehensive test suite with 44+ test methods
✅ **Redis Integration**: Connection pooling, TTL, health checks, error recovery
✅ **Thread-Safe Operations**: Proper locking and atomic file operations
⚠️ **API Keys Required**: Set GEMINI_API_KEY and OPENAI_API_KEY environment variables

## Architecture Overview

### Current Production Architecture
- **Multi-Backend Storage**: Redis → File → Memory with automatic fallback
- **Project Isolation**: Complete separation of conversations, configs, and API keys
- **Configuration Hierarchy**: Environment → Project → Global → Defaults
- **Thread-Safe Design**: Proper locking, atomic operations, connection pooling
- **Token Optimization**: Maintained 95% reduction with two-stage architecture
- **Enterprise Scalability**: Redis clustering, connection pooling, health monitoring

### Storage Backend Architecture
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   File Storage  │    │  Redis Storage  │    │ Memory Storage  │
│   (Default)     │    │  (Scalable)     │    │   (Testing)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────────┐
                    │  Storage Factory    │
                    │  (Auto-selection)   │
                    └─────────────────────┘
                                 │
                    ┌─────────────────────┐
                    │ Configuration Mgr   │
                    │ (Project context)   │
                    └─────────────────────┘
```

### Configuration Management
- **Thread-Safe Singleton**: Global config manager with proper locking
- **Atomic File Operations**: Prevent corruption during concurrent access
- **Environment Variable Overrides**: All settings configurable via env vars
- **Project Inheritance**: API keys and settings cascade from global to project
- **Validation**: Dataclass-based schema enforcement and type safety

## Future Enhancements & Technical Concerns

### High Priority - Concurrency & Reliability
1. **Session-Level File Locking** ⚠️ CRITICAL
   - **Risk**: Multiple zen processes using same session ID can cause race conditions
   - **Impact**: Conversation corruption, message loss, inconsistent state
   - **Solution**: Implement advisory file locking with timeout and retry logic
   - **Files**: `storage_backend.py`, `conversation_memory.py`

2. **Async Support and Background Task Management**
   - **Need**: Long-running operations with progress indicators
   - **Features**: Cancellable operations, real-time progress updates, background model loading
   - **Architecture**: Async/await throughout tool pipeline with task queues

3. **Performance Optimization and Monitoring**
   - **Benchmarking**: Automated performance tests and regression detection
   - **Profiling**: Token usage optimization and response time monitoring
   - **Caching**: Model response caching and conversation context optimization

### Medium Priority - Advanced Features
4. **Smart Conversation Continuity**
   - **Context Summarization**: AI-powered compression for long conversations
   - **Session Branching**: Fork conversations at decision points
   - **Cross-Device Sync**: Cloud synchronization with conflict resolution

5. **Advanced Project Management**
   - **Auto-Detection**: Automatically detect project context from directory structure
   - **Team Collaboration**: Shared project configurations and conversation templates
   - **Migration Tools**: Export/import projects and conversations

6. **Enterprise Integration**
   - **SSO Integration**: Authentication with corporate identity providers
   - **Audit Logging**: Comprehensive activity tracking for compliance
   - **Policy Enforcement**: Configurable usage policies and restrictions

### Low Priority - Analytics & Insights
7. **Comprehensive Testing Strategy**
   - **User Acceptance Testing**: Real-world workflow validation scenarios
   - **CI/CD Pipeline**: GitHub Actions for cross-platform testing and integration
   - **Load Testing**: Concurrent session handling and resource utilization

8. **Telemetry & Analytics Framework** (Privacy-First)
   - **Local Analytics**: Usage patterns and performance metrics (no external transmission)
   - **Opt-in Cloud Sync**: Anonymous usage statistics for improvement
   - **Error Tracking**: Automated crash reporting with user consent

## Technical Concerns & Risk Assessment

### Conversation Collision Risk Analysis
**Question**: "Since each zen call is a different thread, how much risk of conversation collision is there?"

**Technical Analysis**:
- **Risk Level**: MEDIUM-HIGH for file storage, LOW for Redis, NONE for memory
- **Scenario**: Multiple `zen` commands with same `--session ID` running concurrently
- **Current State**: No explicit locking mechanism implemented

**Specific Risks**:
1. **File Storage**: Race conditions during JSON read-modify-write operations
2. **Redis Storage**: Better atomicity but still potential for connection conflicts
3. **Memory Storage**: No collision risk (each process has isolated memory)

**Recommended Solution**:
```python
# Implement advisory file locking
import fcntl, time

class FileBasedStorage:
    def _acquire_session_lock(self, session_id: str, timeout: float = 5.0):
        lock_file = self.storage_dir / f"{session_id}.lock"
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                lock_fd = os.open(lock_file, os.O_CREAT | os.O_WRONLY | os.O_EXCL)
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return lock_fd
            except (OSError, IOError):
                time.sleep(0.1)
        
        raise TimeoutError(f"Could not acquire lock for session {session_id}")
```

**Redis Atomic Operations**:
```python
# Use Redis transactions for atomic operations
def add_message_atomic(self, session_id: str, role: str, content: str):
    with self.redis.pipeline(transaction=True) as pipe:
        pipe.multi()
        pipe.lpush(f"session:{session_id}:messages", json.dumps({...}))
        pipe.expire(f"session:{session_id}:messages", self.ttl)
        pipe.execute()
```

### Performance Considerations
- **Memory Usage**: Conversation growth over time needs cleanup strategies
- **Network Latency**: Redis backend adds network overhead vs file storage
- **Concurrent Connections**: Connection pool sizing for team environments
- **Storage Scalability**: File system limits vs Redis memory constraints

### Security Considerations
- **API Key Storage**: Currently stored in plaintext in config files
- **Session Data**: Conversation content stored without encryption
- **Network Security**: Redis connections should use TLS in production
- **Access Control**: No user-based access restrictions implemented

## Architecture Notes

### Current Architecture
- **Standalone CLI**: Direct tool implementation without MCP protocol
- **In-Memory Storage**: Conversation memory per session (no persistence)
- **Token Optimization**: Two-stage architecture (select → execute)
- **Installation**: User Python packages at `~/Library/Python/3.13/bin/`

### Proposed Redis Architecture
```python
# Storage backend selection
storage_type = config.get('storage', {}).get('type', 'memory')
if storage_type == 'redis':
    storage = RedisStorage(config['storage']['redis'])
else:
    storage = InMemoryStorage()
```

### Project Configuration Schema
```json
{
  "current_project": "project1",
  "projects": {
    "project1": {
      "redis": {
        "host": "localhost",
        "port": 6379,
        "db": 0,
        "key_prefix": "zen:project1:"
      },
      "api_keys": {
        "gemini": "...",
        "openai": "..."
      }
    },
    "project2": {
      "redis": {
        "host": "redis2.example.com",
        "port": 6380,
        "db": 1,
        "key_prefix": "zen:project2:"
      },
      "api_keys": {
        "gemini": "...",
        "openai": "..."
      }
    }
  }
}
```

## Quick Start

### Setup
```bash
# Set API keys in your shell configuration (~/.zshrc or ~/.bashrc)
export GEMINI_API_KEY="your_actual_gemini_api_key"
export OPENAI_API_KEY="your_actual_openai_api_key"

# Source your configuration
source ~/.zshrc  # or ~/.bashrc

# Test the CLI
zen --version
zen listmodels  # Should show available models
zen chat "Hello, how are you?"
```

### Usage Examples
```bash
# Chat with AI
zen chat "Explain REST APIs"

# Debug issues
zen debug "OAuth tokens not persisting" --files auth.py

# Code review
zen codereview --files src/*.py

# Get consensus from multiple models
zen consensus "Should we use microservices?"

# Generate tests
zen testgen --files mycode.py
```

## Development Commands

### Testing
```bash
# Test CLI directly without installation
cd src
python3 -m zen_cli.main --version

# Run specific tool
python3 -m zen_cli.main chat "test message"

# Use installed version
zen --version
zen chat "Hello"
```

### Installation
```bash
# Install with user packages (macOS with PEP 668)
pip3 install --user --break-system-packages .

# Ensure PATH includes user bin
export PATH="$PATH:$HOME/Library/Python/3.13/bin"
```

### Debugging Import Issues
```bash
# Check which zen is being used
which zen

# Test imports directly
python3 -c "from google.generativeai import GenerativeModel; print('OK')"

# Check Python path
python3 -c "import sys; print('\n'.join(sys.path))"
```

## Important Files
- `src/zen_cli/main.py` - Main CLI entry point
- `src/zen_cli/config.py` - Configuration management (includes CLI config functions)
- `src/zen_cli/utils/storage_backend.py` - Storage abstraction (currently in-memory)
- `src/zen_cli/providers/` - AI model providers
- `src/zen_cli/tools/` - Individual tool implementations
- `src/zen_cli/systemprompts/` - System prompts for each tool

## Fixed Issues
1. **Import errors**: Changed `from google import genai` to `import google.generativeai as genai`
2. **Module paths**: Fixed all imports to use `zen_cli.` prefix (16 files)
3. **Tool class names**: Updated to use actual class names (DebugIssueTool, etc.)
4. **PATH conflicts**: Removed conflicting venv installation
5. **Server module dependency**: Removed all imports and dependencies on MCP server:
   - `version.py`: Removed client info functionality (lines 196-209)
   - `simple/base.py`: Removed follow-up instructions (line 386)
   - `conversation_memory.py`: Removed tool-specific formatting (line 1033)
6. **Provider registration**: Added `_initialize_providers()` in main.py to register AI providers
7. **Execute method**: Fixed tool execution to use async `execute()` instead of `process_request()`

## Notes for Claude
- This is a standalone CLI, not an MCP client
- Uses in-memory storage by default (Redis support planned)
- Token optimization is critical - maintain two-stage architecture
- All file paths must be absolute for security
- Tools don't take constructor parameters (initialized empty)
- User has multiple Redis instances for different projects - needs project switching
- The zen command is installed at `/Users/wrk/Library/Python/3.13/bin/zen`

---

# Zen CLI Integration for Claude Code

## Auto-Trigger Patterns

You have access to the Zen CLI tool. Use it automatically when you encounter these situations:

### Low Confidence Situations
When confidence < high on critical decisions:
```bash
zen consensus "Should we use microservices or monolith for this e-commerce platform?" \
  --models gemini-pro,o3 \
  --context-files architecture.md,requirements.txt
```

### Complex Debugging
When stuck on difficult bugs:
```bash
zen debug "OAuth tokens not persisting across sessions" \
  --files src/auth.py,src/session.py \
  --confidence exploring \
  --model gemini-pro
```

### Architecture Decisions
For important architectural choices:
```bash
zen analyze --files src/**/*.py \
  --analysis-type architecture \
  --model gemini-pro
```

### Security Reviews
Before handling sensitive data:
```bash
zen codereview --files auth_handler.py payment.py \
  --type security \
  --model o3
```

### Usage Patterns for Claude Code

#### NEW! Direct Content Support (Avoids File Path Confusion)
```bash
# Pass content directly via stdin (natural for Claude!)
echo "$file_content" | zen debug "Issue description" --stdin
cat file.py | zen codereview --stdin --type security

# Pass content as argument
zen analyze --content "$CODE_VARIABLE" --analysis-type architecture
zen chat "Explain this" --content "def foo(): pass"

# Traditional file paths still work
zen debug "Issue" -f file.py
```

#### Pattern 1: Quick Consultation
When you need a second opinion:
```bash
# Get quick advice
zen chat "Is using Redis for session storage a good idea for our scale?"

# With specific model
zen chat "Explain the tradeoffs of JWT vs session cookies" --model gemini-pro

# With direct content (NEW!)
zen chat "What does this code do?" --content "$CODE_SNIPPET"
```

#### Pattern 2: Systematic Debugging
When facing complex bugs:
```bash
# Start exploration
zen debug "Memory leak in production" --confidence exploring

# Provide more context with files
zen debug "Memory leak occurs after 1000 requests" \
  -f app.py -f worker.py \
  --confidence medium

# Or with direct content (NEW!)
cat app.py | zen debug "Memory leak after 1000 requests" --stdin --confidence medium
```

#### Pattern 3: Code Quality Checks
Before important commits:
```bash
# Full review
zen codereview --files src/*.py --type all

# Security focus
zen codereview --files auth/*.py --type security --model o3

# Performance analysis
zen codereview --files api/*.py --type performance --model gemini-flash
```

#### Pattern 4: Multi-Model Consensus
For critical decisions:
```bash
# Architecture decisions
zen consensus "Should we migrate from REST to GraphQL?" \
  --models gemini-pro,o3,gpt-4 \
  --context-files api_spec.yaml

# Technology choices
zen consensus "PostgreSQL vs MongoDB for our use case?" \
  --models gemini-pro,o3
```

### When to Use Each Tool

| Situation | Command | Purpose |
|-----------|---------|---------|
| Stuck on bug | `zen debug` | Systematic investigation |
| Need validation | `zen chat` | Quick consultation |
| Code quality | `zen codereview` | Professional review |
| Big decision | `zen consensus` | Multiple perspectives |
| Complex analysis | `zen analyze` | Architecture understanding |
| Project breakdown | `zen planner` | Task decomposition |

### Performance Tips

1. **Model Selection**:
   - `gemini-flash`: Fast responses for simple queries
   - `gemini-pro`: Deep analysis and complex reasoning
   - `o3`: Strong logical reasoning
   - `auto`: Let Zen choose based on task

2. **File Context**:
   - Use `--files` to provide relevant context
   - Glob patterns work: `--files "src/**/*.py"`
   - Keep file count reasonable for token limits

3. **Output Formats**:
   - Use `--json` for structured data
   - Default markdown output for readability
   - Pipe to files for documentation: `> analysis.md`