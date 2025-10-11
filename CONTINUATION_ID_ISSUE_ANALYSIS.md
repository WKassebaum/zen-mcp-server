# Continuation ID Expiration Issue - Analysis & Solution

## Issue Report

User experiencing continuation ID expiration errors during multi-step consensus workflows:

**Error Message:**
```
Conversation thread '<id>' was not found or has expired.
This may happen if the conversation was created more than 3 hours ago
or if the server was restarted.
```

**Context:**
- Occurs during consensus tool execution when trying to continue after first model response
- Happens within normal workflow timeframe (not 3 hours later)
- Affects multi-step workflows that require continuation

## Root Cause Analysis

### 1. Default TTL Configuration

**Location:** `utils/conversation_memory.py:133-148`

```python
# Get conversation timeout from environment (in hours), default to 3 hours
CONVERSATION_TIMEOUT_HOURS = 3  # Default
CONVERSATION_TIMEOUT_SECONDS = CONVERSATION_TIMEOUT_HOURS * 3600  # 10,800 seconds
```

### 2. TTL Refresh Mechanism

**Location:** `utils/conversation_memory.py:257`

```python
# Save back to storage and refresh TTL
storage.set(key, context.model_dump(), ttl=CONVERSATION_TIMEOUT_SECONDS)  # Refresh TTL on add_turn
```

**How it works:**
- Every time `add_turn()` is called, the TTL is refreshed to 3 hours from that moment
- This should keep active conversations alive indefinitely
- Only inactive conversations (no turn additions for 3 hours) should expire

### 3. Storage Backend Implementation

All storage backends support TTL:
- **File Storage** (`utils/file_storage.py`): Stores `expires_at` timestamp with each thread
- **Redis Storage** (`utils/redis_storage.py`): Uses Redis native TTL (SETEX)
- **In-Memory Storage** (`utils/storage_base.py`): Stores `expires_at` with cleanup thread

## Possible Causes

### A. Storage Backend Not Persisting (Most Likely)

**Symptom:** MCP server running with in-memory storage that doesn't persist across requests

**Check:**
```bash
# View current storage configuration
cat ~/.zen/.env | grep STORAGE_TYPE
```

**Solution:**
```bash
# Switch to file-based storage (default, persistent)
export STORAGE_TYPE=file

# Or set in ~/.zen/.env
echo "STORAGE_TYPE=file" >> ~/.zen/.env
```

### B. MCP Server Restarting Between Requests

**Symptom:** If the MCP server process restarts, all in-memory storage is lost

**Check:**
```bash
# Monitor MCP server process
ps aux | grep "python.*mcp_server"

# Check MCP server logs for restart events
tail -f logs/mcp_server.log | grep -i "starting\|initialized"
```

### C. Continuation ID Not Being Created

**Symptom:** Tool doesn't create continuation_id on first step

**Location:** `tools/workflow/workflow_mixin.py:695-697`

```python
# Create thread for first step
if not continuation_id and request.step_number == 1:
    continuation_id = create_thread(self.get_name(), clean_args)
```

**Check:** Verify the first tool response includes a `continuation_id` field

### D. TTL Not Being Refreshed on Tool Calls

**Symptom:** TTL expires because `add_turn()` is never called during workflow

**Location:** `tools/workflow/workflow_mixin.py:736-737`

```python
# Store in conversation memory
if continuation_id:
    self.store_conversation_turn(continuation_id, response_data, request)
```

This calls `add_turn()` which should refresh the TTL.

## Debugging Steps

### 1. Check Storage Configuration

```bash
# View environment configuration
cat ~/.zen/.env

# Expected: STORAGE_TYPE=file (or redis)
# If missing or "memory", that's the problem
```

### 2. Check Conversation Files

```bash
# List active conversations (file storage)
ls -lh ~/.zen/conversations/

# View a specific conversation
cat ~/.zen/conversations/thread_<uuid>.json | jq .
```

### 3. Enable Debug Logging

```bash
# Set debug log level
export LOG_LEVEL=DEBUG

# Monitor conversation memory operations
tail -f logs/mcp_server.log | grep -E "\[THREAD\]|\[FLOW\]|expires_at"
```

### 4. Test Continuation ID Manually

```python
from utils.conversation_memory import create_thread, add_turn, get_thread
import time

# Create thread
thread_id = create_thread("test", {"test": "data"})
print(f"Created: {thread_id}")

# Add turn (refreshes TTL)
add_turn(thread_id, "user", "test content")

# Verify it exists
thread = get_thread(thread_id)
print(f"Retrieved: {thread is not None}")

# Wait 5 seconds and verify TTL was refreshed
time.sleep(5)
thread = get_thread(thread_id)
print(f"Still exists after 5s: {thread is not None}")
```

## Solutions

### Solution 1: Use File-Based Storage (Recommended)

**File:** `~/.zen/.env`

```bash
# Add or update storage configuration
STORAGE_TYPE=file
```

**Why this works:**
- File storage persists across MCP server restarts
- TTL is tracked in file metadata
- Automatic cleanup of expired conversations

### Solution 2: Increase TTL Timeout

**File:** `~/.zen/.env`

```bash
# Increase conversation timeout to 12 hours
CONVERSATION_TIMEOUT_HOURS=12
```

**Why this helps:**
- Gives more time for long-running workflows
- Prevents expiration during normal usage
- Still cleans up old conversations

### Solution 3: Use Redis Storage (Production)

**File:** `~/.zen/.env`

```bash
# Configure Redis storage
STORAGE_TYPE=redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

**Why this is best for production:**
- Persistent across server restarts
- Native TTL support
- Scalable for multiple server instances

### Solution 4: Check Model Availability First

**Issue:** User also reported model availability errors

**Fix:** Ensure models are configured correctly in `~/.zen/.env`

```bash
# Check which API keys are configured
cat ~/.zen/.env | grep -i api_key

# Verify models are available
zen listmodels
```

**Models mentioned by user:**
- ❌ `gemini-2.0-flash-exp` - Not available (use `gemini-2.5-pro` instead)
- ❌ `claude-sonnet-4` - Not available (use `claude-sonnet-4-20250514` instead)
- ✅ `gemini-2.5-pro` - Available
- ✅ `gpt-5-pro` - Available
- ✅ `o3` - Available

## Recommended Actions

### For User

1. **Check storage configuration:**
   ```bash
   cat ~/.zen/.env | grep STORAGE_TYPE
   ```

2. **If not set or "memory", add file storage:**
   ```bash
   echo "STORAGE_TYPE=file" >> ~/.zen/.env
   ```

3. **Restart MCP server:**
   ```bash
   # Find and kill existing server
   pkill -f "python.*mcp_server"

   # Claude Code will auto-restart it
   ```

4. **Use correct model names:**
   - Instead of: `gemini-2.0-flash-exp`
   - Use: `gemini-2.5-pro` or `gemini-flash`

   - Instead of: `claude-sonnet-4`
   - Use: `claude-sonnet-4-20250514` or just `sonnet-4`

5. **Verify models are available:**
   ```bash
   zen listmodels | grep -i "gemini\|claude\|gpt-5\|o3"
   ```

### For Development

1. **Add better error messages:**
   - When continuation_id expires, suggest checking storage config
   - Include TTL remaining time in debug logs
   - Warn when using in-memory storage

2. **Add continuation_id validation:**
   - Check if thread exists before processing workflow steps
   - Return clear error with storage configuration hint
   - Log thread expiration events

3. **Add storage health check:**
   - Verify storage backend is working on server startup
   - Log storage type being used
   - Warn if using in-memory storage in production

## Testing Verification

After applying fixes, verify with:

```python
# Test conversation persistence
from utils.conversation_memory import create_thread, add_turn, get_thread
from utils.storage_backend import get_storage_backend
import time

# Check storage type
storage = get_storage_backend()
print(f"Storage type: {type(storage).__name__}")

# Create thread
thread_id = create_thread("consensus", {"test": "multi-model"})

# Add multiple turns (simulating consensus workflow)
for i in range(3):
    add_turn(thread_id, "user", f"Step {i+1}")
    time.sleep(1)  # Simulate time between steps

    # Verify thread still exists and TTL was refreshed
    thread = get_thread(thread_id)
    if thread:
        print(f"✓ Step {i+1}: Thread active, {len(thread.turns)} turns")
    else:
        print(f"✗ Step {i+1}: Thread expired!")
        break
```

## Status

**Issue:** Continuation IDs expiring during multi-step workflows
**Severity:** HIGH - Blocks multi-model consensus workflows
**Root Cause:** Type mismatch in `get_thread()` - using `model_validate_json()` instead of `model_validate()`
**Fix Applied:** ✅ YES - Fixed utils/conversation_memory.py:303
**Testing Required:** Yes - verify with consensus workflow

## ACTUAL ROOT CAUSE (FIXED)

### Bug in utils/conversation_memory.py

**Location:** `utils/conversation_memory.py:303`

**Problem:**
```python
# WRONG - expects JSON string
return ThreadContext.model_validate_json(data)
```

File storage backend returns a **dict** from `storage.get(key)`, but `model_validate_json()` expects a **JSON string**. This caused the thread lookup to fail silently (caught by Exception handler), making threads appear expired when they actually existed.

**Fix:**
```python
# CORRECT - expects dict
return ThreadContext.model_validate(data)
```

**Why this caused the symptoms:**
1. User creates consensus workflow → thread created successfully
2. First model responds → thread lookup fails due to type mismatch
3. Exception silently caught → thread appears "not found or expired"
4. Error message misleads about TTL timeout (actually a bug, not expiration)

**Evidence from logs:**
```
2025-10-11 03:34:28,786 - __main__ - WARNING - Thread not found: a1a591a2-20f3-404e-bc56-180d28f6f0c2
2025-10-11 03:34:28,786 - __main__ - DEBUG - [CONVERSATION_DEBUG] Thread a1a591a2-20f3-404e-bc56-180d28f6f0c2 not found in storage or expired
```

But the file existed: `/Users/wrk/.zen/conversations/thread:a1a591a2-20f3-404e-bc56-180d28f6f0c2.json`

## Next Steps

1. User should check storage configuration
2. Set `STORAGE_TYPE=file` in `~/.zen/.env`
3. Restart MCP server
4. Re-test consensus workflow with correct model names
5. Monitor logs for any TTL-related warnings
