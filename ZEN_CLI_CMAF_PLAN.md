# Zen CLI Development with CMAF

## Overview
Build a standalone CLI version of Zen MCP Server using CMAF for persistent task management.

## Architecture Benefits with CMAF

### Why CMAF is Perfect for This
1. **Persistent Memory**: CLI development spans multiple sessions - CMAF remembers everything
2. **Branch Management**: Automatically handles zen-cli worktree
3. **Token Optimization**: Can leverage our 95% reduction achievement
4. **Task Delegation**: Perfect for complex CLI features

## Development Tasks for CMAF

### Phase 1: Core CLI Structure
```bash
./cma execute "Create zen CLI with Click framework in zen-cli branch. Include commands: chat, debug, review, analyze, consensus. Use two-stage token optimization from main branch."
```

### Phase 2: Token Optimization Integration
```bash
./cma execute "Port two-stage token optimization to CLI. Create zen select and zen execute commands. Maintain 95% token reduction (43k to 800 tokens)."
```

### Phase 3: Interactive Features
```bash
./cma execute "Add interactive mode with rich terminal UI. Include: syntax highlighting, progress bars, markdown rendering, conversation threading."
```

### Phase 4: Configuration Management
```bash
./cma execute "Create config system: ~/.zen/config.yaml for API keys, model preferences, optimization settings. Support multiple profiles."
```

### Phase 5: Plugin System
```bash
./cma execute "Design plugin architecture for custom tools. Allow users to add their own Zen tools via Python modules."
```

## CLI Command Structure

```bash
# Two-stage optimization commands
zen select "Debug OAuth issue"              # Stage 1: ~200 tokens
zen execute debug --mode workflow          # Stage 2: ~600 tokens

# Direct commands (auto-optimize behind scenes)
zen chat "Explain REST APIs"
zen debug "Token persistence issue" --files auth.py
zen review --security /path/to/code
zen analyze --architecture ./src
zen consensus "Should we use microservices?"

# Interactive mode
zen interactive                            # Rich TUI with all features
zen shell                                  # REPL mode

# Configuration
zen config set api.gemini KEY
zen config profile create work
zen config profile use work

# Plugin management
zen plugin install custom-tool
zen plugin list
zen plugin remove custom-tool
```

## Implementation Priority

1. **Week 1**: Basic CLI structure with Click
2. **Week 2**: Port token optimization 
3. **Week 3**: Add rich terminal UI
4. **Week 4**: Configuration system
5. **Week 5**: Plugin architecture
6. **Week 6**: Testing and documentation

## CMAF Advantages for This Project

### Persistent Context
- CMAF remembers which files implement which features
- No need to re-explain architecture between sessions
- Automatic tracking of dependencies

### Intelligent Task Breakdown
```bash
# CMAF automatically handles:
- Creating appropriate file structure
- Managing imports between modules
- Maintaining consistent code style
- Running tests after changes
```

### Branch Coordination
- zen-cli worktree for CLI development
- zen-dynamic for dynamic tool loading
- Main branch for stable MCP server

## Quick Start with CMAF

```bash
# Terminal 1: Start agent worker
cd /Users/wrk/WorkDev/MCP-Dev/claude-multi-agent
source .venv/bin/activate
python3 start_agent_worker.py

# Terminal 2: Begin CLI development
./cma execute "Create Zen CLI foundation with Click in zen-cli branch. Include main entry point, command groups for chat/debug/review/analyze/consensus, and config loader."

# Monitor progress
./cma status
./cma decisions  # Approve as needed
```

## Success Metrics

- [ ] CLI achieves same 95% token reduction as MCP server
- [ ] All Zen tools accessible via command line
- [ ] Rich terminal UI for better UX
- [ ] Plugin system for extensibility
- [ ] <1 second response time for mode selection
- [ ] Configuration profiles for different use cases

## Testing Strategy

```bash
# CMAF can run comprehensive tests
./cma execute "Create test suite for Zen CLI. Test two-stage optimization, all command modes, config management, and plugin system. Ensure 95% token reduction is maintained."
```

## Documentation Tasks

```bash
# Generate comprehensive docs
./cma execute "Create documentation for Zen CLI: README with examples, API docs for plugin development, migration guide from MCP to CLI, performance benchmarks showing token savings."
```

---

This plan leverages CMAF's persistent memory to build a production-ready CLI that maintains our 95% token optimization achievement while providing a superior developer experience.