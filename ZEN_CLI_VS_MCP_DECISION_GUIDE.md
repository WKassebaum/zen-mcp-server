# Zen CLI vs MCP Server Decision Guide

When both the `zen` CLI command and zen MCP server are available, this guide helps determine which tool to use first for optimal development assistance.

## 💡 **Key Insight: Token Economics**

The **95% token optimization** in MCP server refers to the "price of entry" - the schema context loading cost when Claude Code loads the MCP server (~43K tokens → ~4K tokens), not ongoing AI model usage costs.

**Context Burden Comparison:**
- **MCP Server**: ~4K tokens (optimized schema loaded into Claude Code context)
- **Zen CLI**: ~1-2K tokens (lightweight CLAUDE.md template)
- **AI Model Costs**: Identical for both (same Gemini/OpenAI API calls)

## 🎯 **Zen CLI (Stronger Default Choice)**

**Advantages:**
- **📉 Lower Claude Code context burden** - Only ~1-2K tokens vs ~4K for MCP
- **⚡ Direct execution** - No server dependency or protocol overhead
- **🚀 Immediate availability** - Works instantly if installed  
- **🔧 Simpler troubleshooting** - Fewer moving parts, clearer error messages
- **📦 Self-contained** - All dependencies bundled, no server state to manage
- **🛡️ More reliable** - No network calls, server connectivity, or MCP protocol issues
- **💰 Same AI costs** - Identical underlying model usage and pricing

**When to use zen CLI:**
```bash
# Quick consultation
zen chat "Best approach for caching strategy?"

# Debugging with files
zen debug "API timeout issues" --files api_handler.py --confidence medium

# Code review
zen codereview --files src/*.py --type security
```

## 🌐 **Zen MCP Server (Specialized Tool)**

**Advantages:**
- **💾 Persistent conversations** - Advanced session management across Claude Code sessions
- **🏢 Enterprise features** - Redis clustering, shared team infrastructure
- **🔄 Two-stage architecture** - Workflow continuity features
- **📊 Advanced analytics** - Usage tracking and team metrics

**When to prefer MCP server:**
- **Enterprise teams** with shared Redis infrastructure needs
- **Long-running projects** requiring conversation persistence across multiple Claude Code sessions
- **Team environments** with centralized session management requirements
- **Specific workflow continuity** needs that require server-side state

## 🤔 **Decision Matrix**

| Scenario | First Choice | Reason |
|----------|-------------|---------|
| Quick question | **zen CLI** | Lower context burden, instant response |
| Single file debug | **zen CLI** | Direct execution, same AI costs |
| Small to medium tasks | **zen CLI** | Lower context burden, simpler |
| Large codebase analysis | **zen CLI** | Same AI costs, lower context burden |
| Individual development | **zen CLI** | No server setup needed |
| Troubleshooting tools | **zen CLI** | Simpler error diagnosis |
| Enterprise team with Redis | **MCP server** | Shared infrastructure benefits |
| Cross-session persistence | **MCP server** | Advanced session management |
| Centralized team management | **MCP server** | Team coordination features |

## 💡 **Recommended Approach**

### **Default Strategy (90% of cases):**
**Use zen CLI** - It has lower context burden, same AI performance, and higher reliability.

### **MCP Server Only When:**
You have specific enterprise needs:
- **Team coordination** requiring shared Redis infrastructure
- **Cross-session persistence** where conversations must survive Claude Code restarts  
- **Centralized management** for team environments

### **No Longer Valid Reasons for MCP:**
- ❌ ~~"Large codebase analysis"~~ - Same AI costs, zen CLI has lower context burden
- ❌ ~~"Token optimization"~~ - Only affected schema loading, not AI usage
- ❌ ~~"Complex tasks"~~ - Same underlying AI models and capabilities

## 🎯 **Quick Reference**

### **Use zen CLI for (90% of cases):**
- ✅ All individual development tasks
- ✅ Any size codebase analysis (same AI costs, lower context burden)
- ✅ Quick consultations and debugging
- ✅ Code reviews and security audits
- ✅ When reliability is important
- ✅ When you want immediate results
- ✅ When you want lower Claude Code context usage

### **Use MCP server only for (10% of cases):**
- ✅ Enterprise teams with existing Redis infrastructure
- ✅ Cross-session conversation persistence requirements
- ✅ Centralized team management and coordination
- ✅ When you specifically need server-side session state

## 📊 **Performance Comparison**

| Aspect | Zen CLI | MCP Server |
|--------|---------|------------|
| **Claude Code Context** | ~1-2K tokens | ~4K tokens |
| **AI Model Costs** | Same | Same |
| **Startup Time** | Instant | ~2-3 seconds |
| **Reliability** | Higher | Good (network dependent) |
| **Session Memory** | Basic (per-session) | Advanced (persistent) |
| **Error Handling** | Simple, direct | More complex |
| **Troubleshooting** | Easier | More involved |
| **Infrastructure Needs** | None | Redis (optional but beneficial) |

## 🎖️ **Best Practice Summary**

**Use zen CLI for 90% of development tasks** - It has lower Claude Code context burden (~1-2K vs ~4K tokens), same AI model performance and costs, higher reliability, and simpler troubleshooting. 

**The MCP server is now a specialized tool** primarily for enterprise teams with specific infrastructure needs (shared Redis, cross-session persistence, team coordination).

**Key Insight:** The "95% token optimization" was about schema loading cost, not AI usage. Since zen CLI has even lower context burden and identical AI costs, it's superior for individual development work.

**Remember:** Both tools provide identical core functionality and AI capabilities - zen CLI is simply more efficient for most use cases.

---

*Last updated: v5.12.2 - Token economics clarified: zen CLI has lower context burden with same AI performance.*