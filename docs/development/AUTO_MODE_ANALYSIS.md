# Auto Model Selection Analysis

## Problem Summary

**Issue**: `zen chat "test" --model auto` fails with "Model 'auto' is not available" even though help text shows `(default: auto)`.

**Impact**:
- Direct CLI usage fails (zen chat, zen debug, etc.)
- SuperClaude MCP integration forced to implement custom model selection
- User confusion between advertised vs actual behavior

## Root Cause Analysis

### Architecture Overview

Zen has **two execution paths**:

1. **MCP Protocol Path** (Claude Desktop → server.py → tool.execute())
   - Used when Claude Desktop or other MCP clients invoke tools
   - Goes through `server.py`'s `handle_call_tool()` function
   - ✅ **HAS auto mode resolution** (lines 811-818)

2. **Direct CLI Path** (zen chat → ChatTool().execute())
   - Used when running `zen chat`, `zen debug`, etc. from command line
   - Directly instantiates tool and calls `execute()`
   - ❌ **MISSING auto mode resolution**

### The Working Code (MCP Path)

Located in `server.py:811-818`:

```python
# Handle auto mode at MCP boundary - resolve to specific model
if model_name.lower() == "auto":
    # Get tool category to determine appropriate model
    tool_category = tool.get_model_category()
    resolved_model = ModelProviderRegistry.get_preferred_fallback_model(tool_category)
    logger.info(f"Auto mode resolved to {resolved_model} for {name} (category: {tool_category.value})")
    model_name = resolved_model
    # Update arguments with resolved model
    arguments["model"] = model_name
```

This code:
1. Detects `model == "auto"`
2. Gets tool's category (FAST_RESPONSE, BALANCED, EXTENDED_REASONING)
3. Calls intelligent model selection: `get_preferred_fallback_model(tool_category)`
4. Resolves to optimal model (e.g., gemini-2.5-flash for FAST_RESPONSE)
5. Updates arguments with resolved model

### The Missing Code (Direct CLI Path)

When CLI calls tools directly in `src/zen_cli/main.py`:

```python
# Prepare arguments for chat tool
arguments = {
    "prompt": message,
    "model": model,  # Passes "auto" literally
    "working_directory": os.getcwd(),
}

# Execute chat tool asynchronously - BYPASSES server.py
from tools.chat import ChatTool
result = asyncio.run(ChatTool().execute(arguments))
```

The tool's `execute()` method receives `model="auto"` but has no resolution logic:

```python
# In base_tool.py:1296-1298
def _should_require_model_selection(self, model_name: str) -> bool:
    # Case 1: Model is explicitly "auto"
    if model_name.lower() == "auto":
        return True  # ❌ Treats "auto" as error, not routing trigger
```

This raises `ValueError` with error message instead of performing intelligent selection.

## Technical Details

### Tool Categories (tools/models.py)

```python
class ToolModelCategory(Enum):
    EXTENDED_REASONING = "extended_reasoning"  # Deep thinking (debug, thinkdeep)
    FAST_RESPONSE = "fast_response"           # Speed/cost (chat, analyze)
    BALANCED = "balanced"                      # Balance (codereview, consensus)
```

Each tool declares its category via `get_model_category()`:

- **chat.py**: Returns `ToolModelCategory.FAST_RESPONSE`
- **debug.py**: Returns `ToolModelCategory.EXTENDED_REASONING`
- **codereview.py**: Returns `ToolModelCategory.BALANCED`

### Intelligent Selection Logic (providers/registry.py)

```python
@classmethod
def get_preferred_fallback_model(cls, tool_category: Optional["ToolModelCategory"] = None) -> str:
    """Get the preferred fallback model based on provider priority and tool category.

    This method orchestrates model selection by:
    1. Getting allowed models for each provider (respecting restrictions)
    2. Asking providers for their preference from the allowed list
    3. Falling back to first available model if no preference given
    """
```

Provider priority order:
1. Native APIs (Gemini, OpenAI, XAI, Anthropic) - most direct
2. Custom endpoints (Ollama, vLLM) - local models
3. OpenRouter - catch-all for everything else

Each provider implements `get_preferred_model(category, allowed_models)` to return optimal choice.

### Current CLI Behavior

```bash
$ zen chat "test" --model auto
Error: Model 'auto' is not available with current API keys.
Available models: gemini-2.5-pro, gemini-2.5-flash, gpt-5-pro, o3, grok-4, claude-opus-4.1, ...
Suggested model for chat: 'gemini-2.5-flash' (category: fast_response).
```

The error message ironically **suggests the correct model** ("gemini-2.5-flash") but still fails!

## Solution Options

### Option 1: Fix at CLI Level (Recommended)

Add auto mode resolution in `src/zen_cli/main.py` before calling `tool.execute()`:

```python
def resolve_auto_mode(model: str, tool) -> str:
    """Resolve 'auto' model to specific model using intelligent selection."""
    if model.lower() != "auto":
        return model

    from providers.registry import ModelProviderRegistry
    tool_category = tool.get_model_category()
    resolved_model = ModelProviderRegistry.get_preferred_fallback_model(tool_category)

    # Log for transparency
    logging.info(f"Auto mode resolved to {resolved_model} for {tool.get_name()} (category: {tool_category.value})")

    return resolved_model

# In each CLI command:
@click.option('--model', default='auto', help='Model to use (default: auto)')
def chat(ctx, message, model, files, output_json):
    # ... setup code ...

    # Resolve auto mode before tool execution
    tool = ChatTool()
    resolved_model = resolve_auto_mode(model, tool)

    arguments = {
        "prompt": message,
        "model": resolved_model,  # Pass resolved model
        "working_directory": os.getcwd(),
    }

    result = asyncio.run(tool.execute(arguments))
```

**Pros**:
- Minimal code change (single helper function)
- Consistent with MCP behavior
- Maintains existing tool architecture

**Cons**:
- Need to update ~12 CLI commands
- Duplication of logic from server.py

### Option 2: Fix at Tool Level

Modify `base_tool.py:_resolve_model_context()` to handle "auto" mode:

```python
def _resolve_model_context(self, arguments: dict, request) -> tuple[str, Any]:
    """Resolve model context and name using centralized logic."""

    # Extract model from request
    model_name = getattr(request, "model", None)
    if not model_name:
        from config import DEFAULT_MODEL
        model_name = DEFAULT_MODEL

    # NEW: Handle auto mode at tool level
    if model_name.lower() == "auto":
        tool_category = self.get_model_category()
        model_name = ModelProviderRegistry.get_preferred_fallback_model(tool_category)
        logger.info(f"Auto mode resolved to {model_name} for {self.get_name()} (category: {tool_category.value})")

    # Check if we should require model selection (unavailable model)
    if self._should_require_model_selection(model_name):
        error_message = self._build_model_unavailable_message(model_name)
        raise ValueError(error_message)

    # Create model context
    from utils.model_context import ModelContext
    model_context = ModelContext(model_name)

    return model_name, model_context
```

Then remove the "auto" check from `_should_require_model_selection()`:

```python
def _should_require_model_selection(self, model_name: str) -> bool:
    """Check if we should require model selection (model unavailable)."""

    # REMOVED: Case 1: Model is explicitly "auto"
    # if model_name.lower() == "auto":
    #     return True

    # Check if requested model is available
    from providers.registry import ModelProviderRegistry
    provider = ModelProviderRegistry.get_provider_for_model(model_name)
    if not provider:
        logger.warning(f"Model '{model_name}' is not available with current API keys.")
        return True

    return False
```

**Pros**:
- Single fix point (affects all tools automatically)
- No CLI changes needed
- Consistent behavior across MCP and CLI
- Tools become self-contained

**Cons**:
- Small behavior change in tool layer
- Need to ensure thread-safety

### Option 3: Hybrid Approach (Most Robust)

Implement Option 2 (tool-level fix) AND add explicit error message improvement:

```python
def _should_require_model_selection(self, model_name: str) -> bool:
    """Check if model selection is required."""

    # Special case: "auto" should have been resolved by now
    if model_name.lower() == "auto":
        # This should not happen - auto should be resolved earlier
        logger.error(
            f"Auto mode reached validation without resolution in {self.get_name()}. "
            "This indicates a code path that bypassed model resolution."
        )
        return True

    # Normal case: check if requested model is available
    from providers.registry import ModelProviderRegistry
    provider = ModelProviderRegistry.get_provider_for_model(model_name)
    if not provider:
        logger.warning(f"Model '{model_name}' is not available with current API keys.")
        return True

    return False
```

**Pros**:
- Defensive programming (catches edge cases)
- Clear error logging for debugging
- Graceful degradation

## Recommended Fix: Option 2 (Tool Level)

**Why**:
1. **Single point of fix**: All tools automatically get auto mode support
2. **Consistency**: Matches MCP behavior without duplication
3. **Maintainability**: Future tools automatically work correctly
4. **Transparency**: Log messages show model selection decisions

**Implementation Steps**:

1. **Modify `tools/shared/base_tool.py:_resolve_model_context()`** to handle "auto" mode
2. **Update `_should_require_model_selection()`** to remove "auto" special case
3. **Add transparency logging** to show what model was selected and why
4. **Update tests** to verify auto mode resolution works correctly

**Testing Strategy**:

```bash
# Test direct CLI with auto mode (should now work)
zen chat "test" --model auto

# Test explicit model still works
zen chat "test" --model gemini-2.5-flash

# Test invalid model still produces error
zen chat "test" --model nonexistent-model

# Test MCP integration still works (via Claude Desktop)
# Should continue working since server.py resolution remains unchanged
```

## Additional Benefits of Fix

1. **Transparent model selection**: Logs show which model was chosen and why
2. **Tool category awareness**: Different tools get appropriate models
3. **Provider priority respected**: Follows Gemini → OpenAI → Custom → OpenRouter
4. **Restriction compliance**: Respects `ALLOWED_MODELS` environment variables
5. **SuperClaude compatibility**: MCP integration can rely on native auto mode

## Related Files

- `config.py:28` - DEFAULT_MODEL = "auto"
- `server.py:811-818` - MCP auto mode resolution (working)
- `tools/shared/base_tool.py:1296-1308` - Tool validation (needs fix)
- `tools/shared/base_tool.py:1363-1412` - Model context resolution (needs enhancement)
- `tools/models.py:11-17` - Tool category definitions
- `providers/registry.py:386-434` - Intelligent model selection logic
- `src/zen_cli/main.py:213-254` - CLI chat command (direct tool call)

## Testing Evidence

From conversation summary, the MCP path works:

```
**Testing Grok-4 (Messages 24-25):**
- User restarted Claude Desktop
- I tested mcp__zen__chat with model="grok-4"
- SUCCESS: Grok-4 responded with comprehensive microservices vs monolithic comparison
- Confirmed all 137 models now accessible via MCP
```

This proves server.py auto mode resolution works when called via MCP protocol.

## Conclusion

The auto mode intelligent selection **already exists and works** in the MCP path. The bug is that direct CLI calls bypass this logic. Fix by adding auto mode resolution to `_resolve_model_context()` in `base_tool.py` so all execution paths benefit from intelligent model selection.

**Estimated effort**: 30 minutes to implement, 1 hour to test thoroughly.
