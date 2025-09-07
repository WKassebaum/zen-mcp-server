# Zen CLI - Post-Review Implementation Plan

## Overview
This plan addresses the 16 remaining issues identified in the code review, prioritized by impact and implementation complexity.

## Priority Matrix

### 🔴 P0 - Critical (Blocks Functionality)
Must fix for tools to work properly.

### 🟡 P1 - High Priority (Major Impact)
Significantly improves reliability and UX.

### 🟢 P2 - Medium Priority (Quality)
Improves code quality and maintainability.

### ⚪ P3 - Low Priority (Nice to Have)
Performance and polish improvements.

---

## Implementation Phases

### Phase 1: Core Functionality (P0) - Day 1
**Goal**: Make all tools fully functional

#### 1.1 Multi-Step Workflow Execution
**Files**: `src/zen_cli/tools/sync_wrapper.py`
**Issue**: Workflow tools only execute first step, missing critical analysis
**Solution**:
```python
def execute_workflow_tool_sync(tool, arguments: dict) -> list[TextContent]:
    # Implement workflow state management
    # Track step_number and continuation_id
    # Loop through steps until next_step_required=False
```
**Affected Tools**: planner, testgen, refactor, secaudit, tracer, docgen, precommit, thinkdeep

#### 1.2 File Reading for All File-Based Tools
**Files**: `src/zen_cli/main_typer.py` (multiple command handlers)
**Issue**: Tools receive file paths but not content
**Solution**: Add file reading to: analyze, secaudit, tracer, docgen, refactor, testgen
```python
from .utils.file_utils import read_files
file_contents = read_files(list(files))
tool_args['file_contents'] = file_contents
```

---

### Phase 2: Reliability (P1) - Day 1-2
**Goal**: Prevent crashes and handle errors gracefully

#### 2.1 Input Validation Layer
**Files**: `src/zen_cli/main_typer.py`, new file: `src/zen_cli/utils/validators.py`
**Implementation**:
```python
# validators.py
def validate_file_paths(paths: List[str]) -> List[str]:
    """Validate file paths exist and are readable."""
    validated = []
    for path in paths:
        if not Path(path).exists():
            raise typer.BadParameter(f"File not found: {path}")
        if not Path(path).is_file():
            raise typer.BadParameter(f"Not a file: {path}")
        validated.append(str(Path(path).absolute()))
    return validated

def validate_model_name(model: str, registry) -> str:
    """Validate model name is available."""
    if model != "auto" and not registry.is_model_available(model):
        available = registry.list_available_models()
        raise typer.BadParameter(
            f"Model '{model}' not available. Choose from: {', '.join(available)}"
        )
    return model
```

#### 2.2 Retry Logic with Exponential Backoff
**Files**: `src/zen_cli/utils/retry.py` (new), `src/zen_cli/tools/sync_wrapper.py`
**Implementation**:
```python
# retry.py
import time
from typing import TypeVar, Callable
import random

T = TypeVar('T')

def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True
) -> T:
    """Retry function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except (ConnectionError, TimeoutError, RateLimitError) as e:
            if attempt == max_retries - 1:
                raise
            
            delay = min(base_delay * (exponential_base ** attempt), max_delay)
            if jitter:
                delay *= (0.5 + random.random())
            
            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s...")
            time.sleep(delay)
```

---

### Phase 3: Testing & Quality (P2) - Day 2-3
**Goal**: Ensure reliability and prevent regressions

#### 3.1 Unit Tests for Critical Paths
**Files**: `tests/test_main_typer.py`, `tests/test_sync_wrapper.py`, `tests/test_validators.py`
**Coverage Targets**:
- Tool execution (success and error paths)
- Input validation
- Retry logic
- Session ID generation
- Model resolution

#### 3.2 Integration Tests
**Files**: `tests/integration/test_commands.py`
**Test Scenarios**:
- Each command with valid inputs
- Each command with invalid inputs
- Workflow continuation
- Concurrent execution

---

### Phase 4: Performance & Polish (P3) - Day 3-4
**Goal**: Optimize startup time and resource usage

#### 4.1 Lazy Tool Loading
**Files**: `src/zen_cli/main_typer.py`
**Implementation**:
```python
class ZenCLI:
    def __init__(self, config: dict):
        self.config = config
        self.registry = ModelProviderRegistry()
        self._tools = {}  # Lazy loading dict
        
    def get_tool(self, tool_name: str):
        """Lazy load tool on first use."""
        if tool_name not in self._tools:
            tool_classes = get_tool_classes()
            if tool_name in tool_classes:
                self._tools[tool_name] = tool_classes[tool_name]()
        return self._tools.get(tool_name)
```

#### 4.2 Response Caching
**Files**: `src/zen_cli/utils/cache.py` (new)
**Implementation**: 
- Cache model responses for identical prompts
- Cache file reads with mtime checking
- TTL-based cache expiration

---

## Implementation Order

### Day 1 - Core Functionality
- [ ] 1.1 Multi-step workflow execution (2-3 hours)
- [ ] 1.2 File reading for all tools (1-2 hours)
- [ ] 2.1 Input validation layer (2-3 hours)

### Day 2 - Reliability
- [ ] 2.2 Retry logic implementation (2-3 hours)
- [ ] 3.1 Critical path unit tests (3-4 hours)

### Day 3 - Quality
- [ ] 3.2 Integration tests (3-4 hours)
- [ ] 4.1 Lazy tool loading (1-2 hours)
- [ ] Documentation updates (1 hour)

### Day 4 - Polish
- [ ] 4.2 Response caching (2-3 hours)
- [ ] Performance profiling (1 hour)
- [ ] Final testing and cleanup (2 hours)

---

## Success Metrics

### Functionality
- ✅ All 16 tools execute completely
- ✅ Multi-step workflows reach completion
- ✅ File-based tools can analyze actual code

### Reliability
- ✅ No crashes on invalid input
- ✅ Graceful handling of API failures
- ✅ Clear error messages for users

### Quality
- ✅ 80%+ test coverage on critical paths
- ✅ All commands have integration tests
- ✅ No regression in existing functionality

### Performance
- ✅ Startup time < 1 second
- ✅ Memory usage < 100MB for typical operations
- ✅ Response caching reduces API calls by 30%+

---

## Risk Mitigation

### Risk 1: Breaking Changes
**Mitigation**: Create comprehensive test suite before refactoring

### Risk 2: Performance Regression
**Mitigation**: Profile before and after changes

### Risk 3: API Rate Limits
**Mitigation**: Implement caching and retry logic

---

## Next Steps
1. Start with Phase 1 (Core Functionality)
2. Test each change thoroughly
3. Commit frequently with clear messages
4. Update documentation as we go