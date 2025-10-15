# CLAUDE.md Templates for Zen MCP

This directory contains templates for integrating Zen MCP into your CLAUDE.md files. Choose the template that best fits your needs.

## Available Templates

### 1. Quick Start Template (`CLAUDE_MD_QUICKSTART.md`)

**Best for:** Getting started quickly with minimal configuration

**Contents:**
- Essential tools (chat, consensus, debug, codereview, planner)
- Basic auto-trigger patterns
- Quick reference commands
- Minimal setup instructions

**Use when:**
- You're new to Zen MCP
- You want the basics without overwhelming detail
- You need a working setup in under 5 minutes

**How to use:**
```bash
# Copy relevant sections to your project's CLAUDE.md
cat templates/CLAUDE_MD_QUICKSTART.md >> CLAUDE.md
```

---

### 2. Full User Template (`CLAUDE_MD_USER_TEMPLATE.md`)

**Best for:** Comprehensive project-specific integration

**Contents:**
- All available tools with detailed descriptions
- Complete auto-trigger patterns
- Usage examples for each tool
- Workflow protocols and best practices
- Model selection guide
- Troubleshooting section
- Integration patterns

**Use when:**
- You want comprehensive documentation
- You're integrating Zen into a complex project
- You need reference material for all features
- You want examples for every use case

**How to use:**
```bash
# Copy relevant sections to your project's CLAUDE.md
# (Pick and choose sections that apply to your project)
cat templates/CLAUDE_MD_USER_TEMPLATE.md >> CLAUDE.md
```

---

### 3. Global Template (`CLAUDE_MD_GLOBAL_TEMPLATE.md`)

**Best for:** System-wide configuration in `~/.claude/CLAUDE.md`

**Contents:**
- Auto-trigger rules for all projects
- Model selection strategies
- Integration with other MCP tools (Codeindex, Memory Keeper)
- Advanced usage patterns
- Global best practices
- System-wide troubleshooting

**Use when:**
- You want consistent behavior across all projects
- You're setting up global Claude configuration
- You want system-wide auto-trigger patterns
- You use Zen MCP across multiple projects

**How to use:**
```bash
# Add to your global CLAUDE.md
cat templates/CLAUDE_MD_GLOBAL_TEMPLATE.md >> ~/.claude/CLAUDE.md
```

---

## Choosing the Right Template

### Decision Matrix

| Scenario | Recommended Template | Why |
|----------|---------------------|-----|
| First time using Zen MCP | Quick Start | Minimal learning curve |
| Setting up a specific project | Full User Template | Complete reference |
| Configuring Claude globally | Global Template | System-wide patterns |
| Want everything documented | Full User + Global | Maximum coverage |
| Just need the basics | Quick Start | Fast setup |

### Combining Templates

You can use multiple templates together:

**Recommended Setup:**
```bash
# 1. Global configuration (applies to all projects)
cat templates/CLAUDE_MD_GLOBAL_TEMPLATE.md >> ~/.claude/CLAUDE.md

# 2. Project-specific configuration
cd /path/to/your/project
cat templates/CLAUDE_MD_QUICKSTART.md >> CLAUDE.md
# Add project-specific rules and context below
```

**Advanced Setup:**
```bash
# Global: System-wide patterns
cat templates/CLAUDE_MD_GLOBAL_TEMPLATE.md >> ~/.claude/CLAUDE.md

# Project: Comprehensive documentation
cat templates/CLAUDE_MD_USER_TEMPLATE.md >> /path/to/project/CLAUDE.md
# Customize with project-specific tools, workflows, etc.
```

---

## Template Sections Explained

### All Templates Include:

1. **Tool Reference** - List of available tools and their purposes
2. **Auto-Trigger Patterns** - When to automatically use Zen MCP
3. **Usage Examples** - How to call tools correctly
4. **Model Selection** - Which model to use for different tasks
5. **Best Practices** - Guidelines for effective usage

### Additional Sections (Full/Global Templates):

6. **Workflow Protocols** - Multi-step workflow management
7. **File Handling** - Path requirements and best practices
8. **Integration Patterns** - Advanced multi-tool workflows
9. **Troubleshooting** - Common issues and solutions
10. **Quick Reference** - Command cheat sheet

---

## Customization Guide

### Adding Project-Specific Rules

After copying a template, add your project-specific information:

```markdown
## Project-Specific Context

**Project:** MyApp Authentication Module
**Stack:** Python, FastAPI, PostgreSQL
**Critical Files:**
- `/Users/you/myapp/src/auth/`
- `/Users/you/myapp/src/models/user.py`

**Project Rules:**
- Always use `mcp__zen__secaudit` before committing auth changes
- Use `o3` model for security-critical code reviews
- Run `mcp__zen__precommit` on all changes to `/auth/` directory
```

### Customizing Auto-Triggers

Adjust triggers to match your workflow:

```markdown
## Custom Auto-Trigger Patterns

**For this project, always use Zen when:**
- Modifying authentication code → `codereview` with `o3`
- Adding new API endpoints → `precommit` validation
- Refactoring database models → `analyze` + `consensus`
- Security-related changes → `secaudit` required
```

### Adding Tool Configurations

Specify default models and settings:

```markdown
## Project Tool Configuration

**Default Models:**
- Debug: `gemini-2.5-pro` (large context for complex traces)
- Code Review: `o3` (precision for security)
- Planning: `flash` (speed for iteration)
- Consensus: `gemini-pro,o3,gpt-5` (multiple perspectives)

**Disabled Tools:**
- `tracer` - Not needed for web API project
- `docgen` - Using separate documentation tool
```

---

## Integration with Setup Wizard

The setup wizard (`zen setup` or `./run-server.sh`) can reference these templates:

### During MCP Configuration

```bash
./run-server.sh

# After setup completes:
╭──────────────────────────────────────────────────────╮
│ ✓ Zen MCP configured successfully!                   │
│                                                      │
│ Next Steps:                                          │
│ 1. Add integration to CLAUDE.md                     │
│    → See templates/CLAUDE_MD_QUICKSTART.md          │
│ 2. Test with: zen listmodels                        │
╰──────────────────────────────────────────────────────╯
```

### Documentation References

- **README.md** - Links to templates in Quick Start section
- **docs/getting-started.md** - References templates for Claude Code setup
- **docs/setup-wizard.md** - Mentions templates for MCP configuration
- **CLAUDE_CODE_INTEGRATION.md** - Points to full template for advanced users

---

## Template Maintenance

### Version Information

All templates include version information:
```markdown
**Template Version:** 2.0
**Compatible with:** Zen MCP v5.14.0+
**Last Updated:** 2025-01-14
```

### Updating Templates

When Zen MCP adds new features:
1. Update relevant templates with new tools/patterns
2. Increment version number
3. Update "Last Updated" date
4. Document changes in template header

### Template Evolution

| Version | Changes | Date |
|---------|---------|------|
| 2.0 | Added comprehensive templates (User, Global, Quick Start) | 2025-01-14 |
| 1.0 | Initial CLAUDE.md.TEMPLATE | 2025-01-09 |

---

## Additional Resources

**Documentation:**
- [Getting Started Guide](../docs/getting-started.md)
- [Tool Documentation](../docs/tools/)
- [Advanced Usage](../docs/advanced-usage.md)
- [Configuration Guide](../docs/configuration.md)

**Example Integrations:**
- [CLAUDE_CODE_INTEGRATION.md](../CLAUDE_CODE_INTEGRATION.md) - Detailed Claude Code setup
- [CLAUDE.md](../CLAUDE.md) - Example project-specific configuration

**Setup:**
- [Setup Wizard Guide](../docs/setup-wizard.md)
- [README Quick Start](../README.md#quick-start-5-minutes)

---

## Support

**Questions or Issues:**
- GitHub Issues: https://github.com/BeehiveInnovations/zen-mcp-server/issues
- Documentation: https://github.com/BeehiveInnovations/zen-mcp-server/tree/main/docs

**Contributing:**
- See [CONTRIBUTIONS.md](../docs/contributions.md) for guidelines
- Submit template improvements via pull request

---

**Template Directory Version:** 2.0
**Last Updated:** 2025-01-14
