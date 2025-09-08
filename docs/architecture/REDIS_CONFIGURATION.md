# Redis Configuration for Multi-Project Setup

## Current State
The standalone zen-cli currently uses **in-memory storage** for conversation memory, which means:
- Each CLI invocation has isolated memory
- No persistence between runs
- Cannot share conversations across processes

## Future Enhancement: Redis Support

For production use with multiple projects (like your setup), we should add Redis configuration support:

### Proposed Configuration Structure

```yaml
# ~/.zen-cli/config.json
{
  "storage": {
    "type": "redis",  # or "memory"
    "redis": {
      "connections": {
        "project1": {
          "host": "redis1.example.com",
          "port": 6379,
          "db": 0,
          "password": "...",
          "key_prefix": "zen:project1:"
        },
        "project2": {
          "host": "redis2.example.com",
          "port": 6380,
          "db": 1,
          "password": "...",
          "key_prefix": "zen:project2:"
        }
      },
      "default": "project1"
    }
  }
}
```

### Usage Patterns

```bash
# Use default Redis instance
zen chat "How does the auth system work?"

# Specify project/Redis instance
zen --project project2 debug "OAuth tokens not persisting"

# Use local memory (no Redis)
zen --memory chat "Quick question"
```

### Implementation Plan

1. **Add Redis backend option** to storage_backend.py
   - Keep InMemoryStorage as default
   - Add RedisStorage class
   - Auto-detect based on config

2. **Project context management**
   - Add --project flag to CLI
   - Store current project in config
   - Automatic key namespacing per project

3. **Connection pooling**
   - Reuse Redis connections
   - Handle connection failures gracefully
   - Fallback to memory if Redis unavailable

4. **Data isolation**
   - Use key prefixes for project separation
   - Optional Redis database selection
   - Conversation expiry per project

## Benefits of Redis Integration

- **Persistence**: Conversations survive CLI restarts
- **Sharing**: Multiple CLI instances can share context
- **Project isolation**: Each project has separate conversation space
- **Scale**: Handle large conversation histories
- **Analytics**: Track usage patterns across projects

## Current Workaround

Until Redis support is added, you can:
1. Use the MCP server version (which has Redis support)
2. Use environment variables to simulate project switching:
   ```bash
   export ZEN_PROJECT=project1
   zen chat "..."
   ```

## Next Steps

1. Test current in-memory implementation
2. Design Redis configuration schema
3. Implement RedisStorage backend
4. Add project switching support
5. Migration path from in-memory to Redis