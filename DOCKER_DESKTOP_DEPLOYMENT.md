# Docker Desktop Deployment Guide for Zen MCP Server v5.12.0

## Quick Start (2 minutes)

### Prerequisites
- Docker Desktop installed and running
- API keys for at least one provider (Gemini, OpenAI, etc.)

### 1. Clone and Checkout v5.12.0
```bash
# Clone the repository
git clone https://github.com/WKassebaum/zen-mcp-server.git
cd zen-mcp-server

# Checkout the token-optimization release
git checkout v5.12.0
# or for the branch:
git checkout token-optimization-two-stage
```

### 2. Configure Environment
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your API keys
nano .env  # or use your preferred editor
```

**Required in .env:**
```bash
# At least one API key is required:
GEMINI_API_KEY=your-gemini-key-here
# and/or
OPENAI_API_KEY=your-openai-key-here
# and/or
OPENROUTER_API_KEY=your-openrouter-key-here

# Token optimization is enabled by default
ZEN_TOKEN_OPTIMIZATION=enabled
ZEN_OPTIMIZATION_MODE=two_stage
```

### 3. Build and Start with Docker Compose
```bash
# Build the Docker image
docker-compose build

# Start the services (Redis + Zen MCP Server)
docker-compose up -d

# Verify it's running
docker-compose ps
```

You should see:
```
NAME                IMAGE                    STATUS    PORTS
zen-mcp-server      zen-mcp-server:latest   Up        0.0.0.0:3001->3001/tcp
```

### 4. Configure Claude Desktop

Add to your Claude Desktop configuration:

**Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "zen": {
      "command": "docker",
      "args": ["exec", "-i", "zen-mcp-server", "python", "server.py", "--stdio"],
      "env": {}
    }
  }
}
```

**Alternative: Use TCP connection:**
```json
{
  "mcpServers": {
    "zen": {
      "command": "nc",
      "args": ["localhost", "3001"],
      "env": {}
    }
  }
}
```

### 5. Restart Claude Desktop
- Quit Claude Desktop completely (Cmd+Q on Mac, Alt+F4 on Windows)
- Start Claude Desktop again
- Look for the 🔌 icon in the bottom right
- Click it to verify "zen" server is connected

### 6. Test the Connection
Ask Claude: "What Zen tools are available?"

You should see tools including:
- `zen_select_mode` - Stage 1 of token optimization (~200 tokens)
- `zen_execute` - Stage 2 of token optimization (~600 tokens)
- Plus: chat, debug, codereview, consensus, etc.

## Docker Desktop Specific Settings

### Resource Allocation
In Docker Desktop settings:
1. Go to Settings → Resources
2. Recommended settings:
   - **Memory:** 4 GB minimum (8 GB recommended)
   - **CPU:** 2 cores minimum (4 cores recommended)
   - **Swap:** 1 GB
   - **Disk:** 10 GB free space

### Volume Mounts (Optional)
To persist logs and configuration:

Edit `docker-compose.yml`:
```yaml
services:
  zen-mcp:
    volumes:
      - ./logs:/app/logs
      - ./config:/app/config
      - ~/.zen_mcp:/root/.zen_mcp  # For telemetry data
```

## Common Docker Commands

### View Logs
```bash
# Follow logs in real-time
docker-compose logs -f zen-mcp

# Last 100 lines
docker-compose logs --tail 100 zen-mcp

# Save logs to file
docker-compose logs > zen-logs.txt
```

### Restart Services
```bash
# Restart just the Zen MCP server
docker-compose restart zen-mcp

# Stop everything
docker-compose down

# Start everything
docker-compose up -d

# Rebuild after code changes
docker-compose up --build -d
```

### Debug Connection Issues
```bash
# Check if container is running
docker ps | grep zen-mcp

# Test TCP connection
nc -zv localhost 3001

# Check container health
docker-compose ps

# Enter container for debugging
docker exec -it zen-mcp-server bash

# Check logs for errors
docker-compose logs zen-mcp | grep ERROR
```

## Updating to Latest Version

```bash
# Stop services
docker-compose down

# Pull latest code
git pull origin token-optimization-two-stage

# Rebuild and start
docker-compose up --build -d
```

## Environment Variables

### Token Optimization Settings
```bash
# In .env file
ZEN_TOKEN_OPTIMIZATION=enabled  # Enable 95% token reduction
ZEN_OPTIMIZATION_MODE=two_stage # Use two-stage architecture
ZEN_TOKEN_TELEMETRY=true       # Track token usage
```

### Model Configuration
```bash
DEFAULT_MODEL=auto              # Let Claude choose the best model
# or specify:
DEFAULT_MODEL=gemini-2.0-flash-exp
DEFAULT_MODEL=o3-mini
```

### Performance Tuning
```bash
# Increase timeouts for slow connections
MCP_TIMEOUT=120                # Default: 60 seconds
MAX_RESPONSE_TOKENS=8000       # Default: 4000

# Redis settings
REDIS_URL=redis://localhost:6379/0
REDIS_TIMEOUT=10
```

## Troubleshooting

### Container Won't Start
```bash
# Check Docker Desktop is running
docker version

# Check port 3001 is free
lsof -i :3001

# Remove old containers
docker-compose down -v
docker-compose up --build -d
```

### API Key Issues
```bash
# Verify environment variables are set
docker exec zen-mcp-server env | grep API_KEY

# Check logs for API errors
docker-compose logs zen-mcp | grep "API"
```

### Connection Refused
1. Ensure Docker Desktop is running
2. Check container status: `docker-compose ps`
3. Verify port mapping: `docker port zen-mcp-server`
4. Check firewall settings

### High Memory Usage
```bash
# Check resource usage
docker stats zen-mcp-server

# Restart to clear memory
docker-compose restart zen-mcp

# Adjust memory limits in docker-compose.yml
```

## Advanced Configuration

### Using External Redis
Edit `docker-compose.yml`:
```yaml
services:
  zen-mcp:
    environment:
      - REDIS_URL=redis://your-redis-host:6379/0
    # Remove or comment out the redis service
```

### Custom Port
Edit `docker-compose.yml`:
```yaml
services:
  zen-mcp:
    ports:
      - "8080:3001"  # Use port 8080 instead
```

Update Claude config:
```json
{
  "mcpServers": {
    "zen": {
      "command": "nc",
      "args": ["localhost", "8080"]
    }
  }
}
```

### Production Deployment
For production, add:
```yaml
services:
  zen-mcp:
    restart: always
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; socket.create_connection(('localhost', 3001), timeout=1)"]
      interval: 30s
      timeout: 10s
      retries: 3
```

## Token Optimization Benefits

With v5.12.0's two-stage architecture:
- **Before:** 43,000 tokens per request
- **After:** 200-800 tokens per request
- **Savings:** 95% reduction

This means:
- Longer conversations without context resets
- Faster response times
- Lower API costs
- More complex workflows possible

## Quick Health Check

Run this to verify everything is working:
```bash
#!/bin/bash
echo "Checking Docker Desktop..."
docker version > /dev/null 2>&1 && echo "✓ Docker running" || echo "✗ Docker not running"

echo "Checking Zen MCP container..."
docker ps | grep zen-mcp > /dev/null && echo "✓ Container running" || echo "✗ Container not running"

echo "Checking TCP port..."
nc -zv localhost 3001 2>&1 | grep succeeded > /dev/null && echo "✓ Port 3001 accessible" || echo "✗ Port 3001 not accessible"

echo "Checking logs for errors..."
docker-compose logs --tail 20 zen-mcp 2>/dev/null | grep ERROR > /dev/null && echo "⚠ Errors found in logs" || echo "✓ No recent errors"
```

## Support

- **Issues:** https://github.com/WKassebaum/zen-mcp-server/issues
- **Version:** v5.12.0 with 95% token optimization
- **Branch:** token-optimization-two-stage

---

Last updated for v5.12.0 - Token Optimization Release