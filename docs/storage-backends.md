# Storage Backends for Zen CLI

## Overview

Zen CLI supports three storage backends for conversation persistence:

1. **File-based Storage** (Default, Recommended) - Zero dependencies
2. **Redis Storage** (Optional) - For distributed/team environments
3. **In-Memory Storage** - For testing/development only

## 📁 File-Based Storage (Default)

### Why File Storage is the Default

- ✅ **Zero external dependencies** - Works out of the box
- ✅ **No Docker/services required** - Just filesystem access
- ✅ **Portable** - Works on any platform (Linux, macOS, Windows)
- ✅ **Simple backup** - Just copy `~/.zen/` directory
- ✅ **No network overhead** - Direct file I/O
- ✅ **Thread-safe** - Proper locking mechanisms
- ✅ **Auto-cleanup** - Expires old conversations automatically

### Storage Location

```bash
~/.zen/
├── .env                           # API keys and configuration
└── conversations/
    ├── session_abc123.json        # Active conversation
    ├── session_def456.json        # Another conversation
    └── ...                        # Automatically expires after 3 hours
```

### File Format (JSON)

Each conversation file contains:

```json
{
  "value": {
    "messages": [
      {"role": "user", "content": "Hello"},
      {"role": "assistant", "content": "Hi there!"}
    ],
    "metadata": {
      "model": "gemini-flash",
      "created": "2025-10-09T18:00:00Z"
    }
  },
  "expires_at": 1728504000.0,
  "created_at": 1728493200.0
}
```

### Configuration

File storage is enabled by default. No configuration needed!

```bash
# Optional: Override storage directory
export ZEN_STORAGE_DIR="~/my-custom-location/.zen-cli"

# Optional: Change TTL (Time To Live)
export CONVERSATION_TIMEOUT_HOURS=6  # Default: 3 hours
```

### Usage

```bash
# Just use zen commands - file storage is automatic
zen chat "Hello world"
zen debug "OAuth not working" --files auth.py

# Conversations persist across sessions
zen chat "Continue our previous discussion" --session-id abc123
```

### Maintenance

File storage includes automatic cleanup:

- **Auto-expiration**: Old conversations removed after TTL (default 3 hours)
- **Background cleanup**: Runs every ~30 minutes (disabled in CLI mode to prevent hanging)
- **Manual cleanup**: Delete `~/.zen/conversations/*.json` files

### Thread Safety

File storage uses proper locking to prevent corruption:

```python
# Automatic file locking during read/write operations
with self._lock:
    # Read/write operations are atomic and thread-safe
    file_path.write_text(json.dumps(data))
```

---

## 🔴 Redis Storage (Optional)

### When to Use Redis

Redis is **optional** and only needed for:

- 🏢 **Team environments** - Shared conversation storage
- 🌐 **Distributed deployments** - Multiple servers accessing same conversations
- 📊 **Advanced features** - Pub/sub, distributed locks, etc.

**For single-user CLI usage, file storage is recommended.**

### Installation

Redis is not installed by default. To enable Redis support:

```bash
# Option 1: Install Redis support only
pip install zen-mcp-server[redis]

# Option 2: Install full CLI with all storage backends
pip install zen-mcp-server[cli]
```

### Redis Server Options

#### Option A: Native Redis (No Docker)

**macOS (Homebrew):**
```bash
brew install redis
brew services start redis

# Test connection
redis-cli ping  # Should return "PONG"
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install redis-server
sudo systemctl start redis
sudo systemctl enable redis

# Test connection
redis-cli ping
```

**Windows:**
```bash
# Use WSL2 and follow Linux instructions
# Or download from: https://redis.io/download
```

#### Option B: Docker (Not Recommended per Maintainer)

```bash
# Only if you absolutely need Docker
docker run -d -p 6379:6379 redis:7-alpine
```

#### Option C: Cloud Redis Services

- **Redis Labs Cloud** (Free tier available)
- **AWS ElastiCache**
- **Azure Cache for Redis**
- **Google Cloud Memorystore**

### Configuration

Enable Redis storage via environment variables:

```bash
# ~/.zen/.env
ZEN_STORAGE_TYPE=redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_password_if_needed
REDIS_KEY_PREFIX=zen:
```

### Usage

```bash
# Enable Redis storage
export ZEN_STORAGE_TYPE=redis

# Use zen commands normally
zen chat "Hello world"

# Conversations now stored in Redis
redis-cli KEYS "zen:*"
```

### Graceful Fallback

If Redis is unavailable, Zen automatically falls back to file storage:

```
[WARNING] Redis connection failed, falling back to file storage
[INFO] Initialized file-based conversation storage (Redis fallback)
```

---

## 💾 In-Memory Storage (Testing Only)

### When to Use

- Unit testing
- Development/debugging
- Ephemeral sessions (no persistence needed)

### Configuration

```bash
export ZEN_STORAGE_TYPE=memory
```

### Limitations

- ⚠️ **No persistence** - All data lost when process exits
- ⚠️ **Not suitable for production**
- ⚠️ **Single process only** - No shared state

---

## 🔄 Migration Between Backends

### File → Redis

```bash
# 1. Start with file storage (default)
zen chat "Important conversation" --session-id my-session

# 2. Export conversation
cat ~/.zen/conversations/my-session.json > backup.json

# 3. Switch to Redis
export ZEN_STORAGE_TYPE=redis

# 4. Import to Redis (manual migration needed)
# Use redis-cli or Python script to import backup.json
```

### Redis → File

```bash
# 1. Export from Redis
redis-cli GET "zen:session:my-session" > backup.json

# 2. Switch to file storage
export ZEN_STORAGE_TYPE=file

# 3. Import to file storage
# Place backup.json in ~/.zen/conversations/
```

---

## 📊 Comparison Matrix

| Feature | File Storage | Redis Storage | In-Memory |
|---------|--------------|---------------|-----------|
| **External Dependencies** | None ✅ | Redis server | None |
| **Persistence** | Yes ✅ | Yes ✅ | No ❌ |
| **Multi-process** | Limited ⚠️ | Yes ✅ | No ❌ |
| **Team Sharing** | No ❌ | Yes ✅ | No ❌ |
| **Network Required** | No ✅ | Yes ⚠️ | No ✅ |
| **Setup Complexity** | Zero ✅ | Medium ⚠️ | Zero ✅ |
| **Performance** | Fast ✅ | Fast ✅ | Fastest ✅ |
| **Backup/Restore** | Easy ✅ | Medium ⚠️ | N/A ❌ |
| **Production Ready** | Yes ✅ | Yes ✅ | No ❌ |
| **Recommended For** | Single user CLI | Teams, distributed | Testing only |

---

## 🎯 Recommendations

### For Most Users
**Use file storage (default)** - It just works, no setup required.

### For Team Environments
**Use Redis** - Shared conversation state, distributed access.

### For Testing/CI
**Use in-memory** - Fast, isolated, no cleanup needed.

---

## 🔧 Troubleshooting

### File Storage Issues

**Problem:** Permission denied writing to `~/.zen/`
```bash
# Solution: Check directory permissions
ls -ld ~/.zen
chmod 755 ~/.zen
```

**Problem:** Disk full errors
```bash
# Solution: Clean up old conversations
rm -f ~/.zen/conversations/*.json
```

### Redis Issues

**Problem:** Connection refused
```bash
# Solution 1: Check if Redis is running
redis-cli ping

# Solution 2: Check Redis configuration
cat /opt/homebrew/etc/redis.conf | grep bind

# Solution 3: Verify port
netstat -an | grep 6379
```

**Problem:** Authentication required
```bash
# Solution: Add password to environment
export REDIS_PASSWORD=your_redis_password
```

---

## 📝 Summary

**Default (File Storage) - Just Works™**
```bash
# No configuration needed!
zen chat "Hello world"
```

**Optional (Redis) - For Teams**
```bash
# Install Redis support
pip install zen-mcp-server[redis]

# Configure Redis
export ZEN_STORAGE_TYPE=redis
export REDIS_HOST=localhost

# Use normally
zen chat "Team conversation"
```

**The maintainer is moving away from Docker** - Our file-based storage aligns perfectly with this direction by eliminating external service dependencies while maintaining full conversation persistence.
