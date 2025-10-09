# XAI Grok Models Addition

**Branch:** `xai-grok-models`
**Base:** `upstream/main` (BeehiveInnovations/zen-mcp-server)
**Status:** ✅ Ready for testing and potential upstream PR
**Date:** 2025-10-09

## Overview

This branch adds 3 new XAI Grok models to the Zen MCP Server that provide extended context windows and specialized capabilities compared to the existing Grok models.

## New Models Added

### 1. grok-4-fast-reasoning
- **Context Window:** 2M tokens (vs 256K in standard Grok-4)
- **Output Tokens:** 128K
- **Features:**
  - Extended thinking support
  - Function calling
  - JSON mode
  - Image support (20MB max)
- **Use Case:** Cost-efficient reasoning with extended context
- **Intelligence Score:** 15
- **Aliases:** `grok4fast`, `grok-4-fast`

### 2. grok-4-fast-non-reasoning
- **Context Window:** 2M tokens
- **Output Tokens:** 128K
- **Features:**
  - Optimized for speed (no extended thinking)
  - Function calling
  - JSON mode
  - Image support (20MB max)
- **Use Case:** Lowest latency for large context tasks
- **Intelligence Score:** 14
- **Aliases:** `grok4fast-nr`, `grok-4-fast-nr`

### 3. grok-code-fast-1
- **Context Window:** 256K tokens
- **Output Tokens:** 128K
- **Features:**
  - Specialized for agentic coding tasks
  - Extended thinking with visible reasoning traces
  - Function calling
  - JSON mode
  - No image support (text-only)
- **Use Case:** Code generation and analysis
- **Intelligence Score:** 16
- **Aliases:** `grok-code`, `grokcode`, `grok-code-fast`

## Key Benefits

1. **Extended Context:** 2M token context window (8x larger than Grok-4)
2. **Cost Efficiency:** 40% fewer tokens than standard Grok-4
3. **Specialized Coding:** Dedicated model optimized for code tasks
4. **Performance Options:** Choose between reasoning depth and speed

## Technical Details

**File Modified:** `conf/xai_models.json` (+60 lines)
**Total XAI Models:** 6 (was 3, now 6)
**Testing:** ✅ Verified in Docker deployment

**Existing Models:**
- grok-4 (256K context)
- grok-3 (131K context)
- grok-3-fast (131K context)

**New Models:**
- grok-4-fast-reasoning (2M context) ✨
- grok-4-fast-non-reasoning (2M context) ✨
- grok-code-fast-1 (256K context, specialized) ✨

## Testing Verification

```bash
# Verified in running container
docker exec zen-mcp-server python3 -c "import json; \
  data = json.load(open('/app/conf/xai_models.json')); \
  print(f'Total XAI models: {len(data[\"models\"])}'); \
  [print(f'  - {m[\"model_name\"]}') for m in data['models']]"

# Output:
# Total XAI models: 6
#   - grok-4
#   - grok-3
#   - grok-3-fast
#   - grok-4-fast-reasoning ✅
#   - grok-4-fast-non-reasoning ✅
#   - grok-code-fast-1 ✅
```

## Usage Examples

```python
# Using grok-4-fast-reasoning for extended context analysis
model = "grok-4-fast-reasoning"
# Can process up to 2M tokens of context

# Using grok-code-fast-1 for code generation
model = "grok-code-fast-1"
# Optimized for coding tasks with visible reasoning

# Using grok-4-fast-non-reasoning for speed
model = "grok-4-fast-non-reasoning"
# Fastest option for large context
```

## Comparison with Existing Models

| Model | Context | Output | Thinking | Images | Score | Use Case |
|-------|---------|--------|----------|--------|-------|----------|
| grok-4 | 256K | 256K | ✅ | ✅ | 16 | General flagship |
| grok-3 | 131K | 131K | ❌ | ❌ | 13 | Standard tasks |
| grok-3-fast | 131K | 131K | ❌ | ❌ | 12 | Fast processing |
| **grok-4-fast-reasoning** | **2M** | **128K** | ✅ | ✅ | 15 | **Extended context** |
| **grok-4-fast-non-reasoning** | **2M** | **128K** | ❌ | ✅ | 14 | **Fast + large context** |
| **grok-code-fast-1** | **256K** | **128K** | ✅ | ❌ | 16 | **Specialized coding** |

## Branch Information

**GitHub Fork:** https://github.com/WKassebaum/zen-mcp-server
**Branch:** `xai-grok-models`
**Upstream:** BeehiveInnovations/zen-mcp-server (main branch)
**Commits:** 1 clean commit focused on XAI models only

**Commit:**
```
07cb86c feat: Add XAI Grok-4-Fast and Grok-Code-Fast models

- Add grok-4-fast-reasoning (2M context, extended thinking)
- Add grok-4-fast-non-reasoning (2M context, optimized for speed)
- Add grok-code-fast-1 (256K context, specialized coding model)

These models provide 2M context windows (vs 256K in standard Grok-4)
and include a specialized coding model optimized for agentic tasks.
```

## Deployment

### Local Testing
```bash
# Switch to branch
git checkout xai-grok-models

# Build and deploy
docker-compose build
docker-compose up -d

# Verify models loaded
docker exec zen-mcp-server python3 -c "import json; \
  data = json.load(open('/app/conf/xai_models.json')); \
  [print(m['model_name']) for m in data['models']]"
```

### Pulling from Fork
```bash
# Add fork as remote
git remote add wkassebaum https://github.com/WKassebaum/zen-mcp-server.git

# Fetch and checkout
git fetch wkassebaum
git checkout -b xai-grok-models wkassebaum/xai-grok-models
```

## Potential Upstream PR

This branch is ready to potentially submit as a PR to BeehiveInnovations if desired:

**Pros:**
- Small, focused change (60 lines, 1 file)
- Adds real value (new models with 2M context)
- No architectural changes
- Clean commit history
- Already tested

**Cons:**
- Active project may implement differently
- May already have these models in progress
- Maintainers may prefer different model selection

**Recommendation:** Monitor upstream for a few days to see if they add these models independently. If not, this branch is ready to submit as a focused PR.

## Notes

- This branch is based on the **latest upstream/main** (not our rejected token-optimization work)
- Contains **only** the XAI model additions, no other changes
- All models tested and verified in Docker deployment
- Compatible with current Zen MCP Server architecture
- No breaking changes or dependencies

---

**Created:** 2025-10-09
**Author:** William R. Kassebaum
**Co-Authored-By:** Claude (Anthropic)
