# Token Optimization Troubleshooting Guide

## Problem: Still Using 43K Tokens Instead of 800

If you've checked out the `token-optimization-two-stage` branch but are still seeing 43,000 tokens being used, follow this troubleshooting guide.

## Solution Steps

### 1. Ensure You Have the Latest Branch
```bash
git checkout token-optimization-two-stage
git pull origin token-optimization-two-stage
```

### 2. Add Token Optimization Settings to Your .env File

**CRITICAL:** The token optimization settings are NOT automatically enabled in your .env file. You must add them manually!

Copy these lines to your `.env` file:
```bash
# Token Optimization Settings (REQUIRED for 95% reduction!)
ZEN_TOKEN_OPTIMIZATION=enabled
ZEN_OPTIMIZATION_MODE=two_stage
ZEN_TOKEN_TELEMETRY=true
ZEN_OPTIMIZATION_VERSION=v5.12.0
```

Or copy from the updated .env.example:
```bash
cp .env.example .env
# Then add your API keys
```

### 3. Verify the Settings Are Working

After restarting the server, check the logs for confirmation:
```bash
# If using Docker
docker-compose logs zen-mcp | grep "Token Optimization"

# If running locally
# Look for these messages in the console:
# "Token Optimization Configuration:"
# "  - Enabled: True"
# "  - Mode: two_stage"
# "  - Using two-stage architecture for 95% token reduction"
# "Using optimized tools - X tools registered for 95% token reduction"
```

### 4. Verify Tools Are Available in Claude

In Claude Desktop, you should see these tools:
- `zen_select_mode` - Stage 1: Mode selection (~200 tokens)
- `zen_execute` - Stage 2: Execution (~600 tokens)

**Note:** The original tool names (chat, debug, codereview, etc.) will redirect to the optimized flow automatically.

### 5. Test the Optimization

Try this in Claude:
```
Use zen_select_mode to debug why OAuth tokens aren't persisting
```

Then use the response to call zen_execute with the recommended parameters.

## Common Issues

### Issue 1: Environment Variables Not Set
**Symptom:** Logs show "Using original tool registration (no optimization)"
**Solution:** Ensure the token optimization variables are in your .env file and restart

### Issue 2: Old Docker Image
**Symptom:** Settings are correct but still using 43k tokens
**Solution:** Rebuild the Docker image
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Issue 3: Wrong Branch
**Symptom:** Files like mode_selector.py are missing
**Solution:** Verify you're on the correct branch
```bash
git branch --show-current  # Should show: token-optimization-two-stage
ls tools/mode_*.py  # Should show: mode_executor.py mode_selector.py
```

### Issue 4: Server Not Restarted
**Symptom:** Changes to .env not taking effect
**Solution:** Restart the server after changing .env
```bash
# Docker
docker-compose restart

# Local
# Stop with Ctrl+C and start again
python server.py
```

## How to Verify It's Working

### Check 1: Log Messages
Look for these key messages when the server starts:
```
Token Optimization Configuration:
  - Enabled: True
  - Mode: two_stage
  - Version: v5.12.0
  - Using two-stage architecture for 95% token reduction
Using optimized tools - 12 tools registered for 95% token reduction
Two-stage token optimization enabled - Stage 1 (zen_select_mode) and Stage 2 (zen_execute) ready
```

### Check 2: Tool List
When Claude lists available tools, you should see:
- `zen_select_mode` with description about mode selection
- `zen_execute` with description about execution

### Check 3: Token Count
Monitor the actual token usage:
- Stage 1 (zen_select_mode): ~200 tokens
- Stage 2 (zen_execute): ~600 tokens
- Total: ~800 tokens (vs 43,000 without optimization)

## Still Not Working?

### Debug Checklist
1. ✅ On branch `token-optimization-two-stage`?
2. ✅ Added all 4 token optimization variables to .env?
3. ✅ Restarted the server after changes?
4. ✅ See optimization messages in logs?
5. ✅ See zen_select_mode and zen_execute in Claude's tool list?

### Get More Debug Info
Set debug logging in your .env:
```bash
LOG_LEVEL=DEBUG
```

Then check logs for:
- "token_config.is_enabled()" status
- "get_optimized_tools()" return value
- Tool registration messages

### Manual Verification
Check if the optimization files exist:
```bash
ls -la tools/mode_*.py tools/zen_execute.py
# Should show:
# tools/mode_executor.py
# tools/mode_selector.py
# tools/zen_execute.py
```

## Expected Behavior When Working

1. **Server Start:** Shows token optimization enabled messages
2. **Claude Lists Tools:** Shows zen_select_mode and zen_execute
3. **Using Tools:** 
   - First call zen_select_mode (200 tokens)
   - Then call zen_execute with mode (600 tokens)
   - Total: ~800 tokens instead of 43,000

## Summary

The most common issue is **missing environment variables**. The token optimization is NOT enabled by default in your .env file - you must add:
```bash
ZEN_TOKEN_OPTIMIZATION=enabled
ZEN_OPTIMIZATION_MODE=two_stage
```

After adding these and restarting, you should see the 95% token reduction working!