# Zen CLI - Claude Code Integration Analysis

## Executive Summary

**Problem:** CLAUDE.md contains outdated, incomplete Zen CLI documentation that wastes tokens and provides incorrect usage examples.

**Solution:** A comprehensive zen-skill already exists (~6,500 tokens) with accurate documentation for all 15 tools, but it's not integrated into the installation process. We should adopt **progressive disclosure** via skills instead of loading everything in CLAUDE.md.

**Token Savings:** 80-90% reduction by moving from always-loaded CLAUDE.md to on-demand skill invocation.

## Current State Analysis

### 1. CLAUDE.md Issues (Lines 781-924)

**Critical Problems:**
```bash
# ❌ WRONG - These CLI flags don't exist
zen debug "problem" --step 1 --total-steps 3 --next-step-required true --findings "test"

# ❌ WRONG - Model name outdated
zen consensus "question" --models gemini-pro,o3

# ❌ WRONG - Tool doesn't exist
mcp__zen__security  # Should be mcp__zen__secaudit

# ✅ CORRECT
zen debug "OAuth tokens not persisting" -f auth.py --confidence exploring
zen consensus "question" --models gemini-2.5-pro,o3
mcp__zen__secaudit
```

**Missing Tools:** CLAUDE.md only documents 5 tools but we have 15:
- ❌ Missing: `docgen`, `precommit`, `secaudit`, `refactor`, `testgen`, `thinkdeep`, `tracer`, `apilookup`, `challenge`, `clink`
- ✅ Documented: `chat`, `debug`, `consensus`, `analyze`, `planner`

**Outdated Information:**
- Shows CLI flags that were removed during workflow tool redesign
- Uses old model names (`gemini-pro` → `gemini-2.5-pro`, `flash` → `gemini-2.5-flash`)
- References nonexistent `zen continue-chat` command
- Shows `zen project` commands that don't exist in current CLI

### 2. Zen Skill - Comprehensive & Accurate

**Location:** `~/.claude/skills/zen-skill/SKILL.md`

**Quality Metrics:**
- ✅ 553 lines of comprehensive documentation
- ✅ All 15 tools documented with correct parameters
- ✅ Accurate usage examples
- ✅ Troubleshooting guide
- ✅ Best practices and patterns
- ✅ Progressive workflows (Pattern 1-5)
- ✅ Auto-trigger scenarios
- ✅ Integration with development workflow

**Example of Superior Documentation:**

```markdown
### 8. `mcp__zen__refactor`
**Purpose:** Refactoring analysis for code smells, decomposition, and modernization

**Parameters:**
- `step` (required): Refactoring plan
- `step_number` (required): Current step
- `total_steps` (required): Estimated steps
- `next_step_required` (required): Continue flag
- `findings` (required): Refactoring opportunities found
- `model` (required): AI model
- `refactor_type` (optional): "codesmells/decompose/modernize/organization"
- `confidence` (required): "exploring/incomplete/partial/complete"

**When to Use:**
- Code smell detection
- Breaking down large functions/classes
- Modernizing legacy code
- Improving code organization
```

This level of detail doesn't exist in CLAUDE.md.

## Token Economics Analysis

### Current Approach (CLAUDE.md Always Loaded)

**Token Cost Per Session:**
- CLAUDE.md Zen section: ~2,800 tokens (outdated, incomplete)
- Loaded: Every Claude Code session
- **Annual waste:** ~2,800 tokens × sessions × inaccuracy factor

**Problems:**
- User pays token cost even when not using Zen
- Outdated docs lead to failed commands → wasted user time
- Missing tools → users don't know capabilities exist

### Proposed Approach (Progressive Disclosure via Skill)

**Token Cost Per Session:**
- Skill listed in available skills: ~50 tokens
- **Full skill loaded only when invoked:** ~6,500 tokens (but accurate & complete)
- Typical sessions without Zen: 0 additional tokens
- **Token savings:** 80-90% for non-Zen sessions

**Benefits:**
- ✅ Load only when needed (Skill tool invocation)
- ✅ Always up-to-date (skill can be updated independently)
- ✅ Complete documentation (all 15 tools)
- ✅ Better user experience (accurate examples)
- ✅ Discoverable (`/skills` command shows it's available)

### Real-World Scenarios

**Scenario 1: General Development (No Zen)**
- CLAUDE.md approach: 2,800 tokens wasted
- Skill approach: 0 tokens
- **Savings:** 2,800 tokens (100%)

**Scenario 2: Using Zen Occasionally**
- CLAUDE.md approach: 2,800 tokens always + incomplete docs
- Skill approach: 50 tokens (listing) + 6,500 tokens when invoked
- **Net cost:** +3,750 tokens BUT user gets:
  - Accurate documentation
  - All 15 tools documented
  - Troubleshooting guide
  - Best practices

**Scenario 3: Heavy Zen Usage**
- Skill stays loaded in context
- One-time 6,500 token cost vs continuous 2,800 token cost
- **ROI:** Better docs + more complete coverage

## Available Tools - Complete List

### Currently Documented in zen-skill

All 15 tools are properly documented:

1. **mcp__zen__chat** - General AI consultation ✅
2. **mcp__zen__consensus** - Multi-model consensus ✅
3. **mcp__zen__debug** - Systematic debugging ✅
4. **mcp__zen__codereview** - Code review (quality, security, performance) ✅
5. **mcp__zen__analyze** - Comprehensive code analysis ✅
6. **mcp__zen__planner** - Sequential task planning ✅
7. **mcp__zen__thinkdeep** - Multi-stage investigation ✅
8. **mcp__zen__refactor** - Refactoring analysis ✅
9. **mcp__zen__testgen** - Test generation ✅
10. **mcp__zen__precommit** - Pre-commit validation ✅
11. **mcp__zen__secaudit** - Security audit (OWASP, compliance) ✅
12. **mcp__zen__tracer** - Code tracing (execution flow, dependencies) ✅
13. **mcp__zen__clink** - CLI-to-CLI bridge ✅
14. **mcp__zen__listmodels** - List available models ✅
15. **mcp__zen__challenge** - Critical thinking validation ✅

### Utility Tools (Non-workflow)

16. **mcp__zen__version** - Server version and configuration
17. **mcp__zen__apilookup** - API documentation lookup

## Recommendations

### Immediate Actions

**1. Update CLAUDE.md Zen Section** (High Priority)

Replace outdated CLI examples with minimal, accurate guidance:

```markdown
## 🧠 Zen MCP Integration

Zen MCP provides AI orchestration and multi-model collaboration for complex tasks.

### Quick Access

For comprehensive documentation, use the zen-skill:
- **Command:** `/skill zen-skill` or use Skill tool
- **Lists:** Use `/skills` to see all available skills

### Essential Commands

**MCP Tools (via Claude Desktop):**
- All zen tools available as `mcp__zen__*`
- Use `mcp__zen__listmodels` to see available models
- Full docs: invoke zen-skill

**CLI Commands (via Terminal):**
```bash
# Quick consultation
zen chat "question" --model gemini-2.5-pro

# Debug with context
zen debug "problem description" -f file.py --confidence exploring

# Code review
zen codereview -f src/*.py --type security

# Multi-model consensus
zen consensus "decision question?" --models gemini-2.5-pro,o3

# List available models
zen listmodels
```

### Auto-Trigger Patterns

Use Zen MCP automatically when:
- Confidence < 80% on technical decisions
- Stuck debugging for >5 minutes
- Security-critical code review needed
- Architectural decisions affecting >2 components
- User explicitly requests validation or second opinion

**For complete documentation:** Use the zen-skill (`/skill zen-skill`)
```

**Token Impact:** Reduces from 2,800 tokens to ~400 tokens (86% reduction)

**2. Automate Skill Installation** (High Priority)

Update `run-server.sh` to install the skill:

```bash
# Add to run-server.sh after MCP configuration

echo "📦 Installing Zen CLI Skill..."
SKILL_DIR="$HOME/.claude/skills/zen-skill"

if [ ! -d "$SKILL_DIR" ]; then
    mkdir -p "$SKILL_DIR"

    # Copy skill files from zen-cli repo
    cp -r "$(pwd)/skills/zen-skill/"* "$SKILL_DIR/"

    echo "✅ Zen skill installed to $SKILL_DIR"
else
    echo "✅ Zen skill already installed"

    # Optional: Update existing skill
    read -p "Update existing skill? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cp -r "$(pwd)/skills/zen-skill/"* "$SKILL_DIR/"
        echo "✅ Zen skill updated"
    fi
fi
```

**3. Create skills/ Directory in Repo** (Medium Priority)

```bash
zen-cli/
├── skills/
│   └── zen-skill/
│       ├── SKILL.md          # Main skill documentation
│       └── examples.md       # Usage examples (optional)
├── scripts/
│   ├── test-skill.sh         # Existing test script ✅
│   └── install-skill.sh      # New: Standalone installer
└── README.md                 # Update with skill info
```

**4. Update README.md** (Medium Priority)

Add skill documentation section:

```markdown
## Claude Code Integration

### Zen Skill

The Zen CLI includes a comprehensive Claude Code skill with documentation for all tools.

**Installation:** Automatically installed by `./run-server.sh`

**Manual Installation:**
```bash
./scripts/install-skill.sh
```

**Usage in Claude Code:**
- List skills: `/skills`
- Load Zen skill: `/skill zen-skill`
- Use Skill tool: Skill(skill="zen-skill")

**Benefits:**
- Progressive disclosure (loaded only when needed)
- Token-efficient (~6,500 tokens vs always-loaded)
- Complete documentation for all 15 tools
- Troubleshooting guides and best practices
```

### Long-Term Improvements

**1. Skill Auto-Update Mechanism**

Create `scripts/update-skill.sh`:

```bash
#!/bin/bash
# Update installed skill with latest from repo

SKILL_SOURCE="$(pwd)/skills/zen-skill"
SKILL_TARGET="$HOME/.claude/skills/zen-skill"

if [ ! -d "$SKILL_SOURCE" ]; then
    echo "❌ Skill source not found: $SKILL_SOURCE"
    exit 1
fi

echo "📦 Updating zen-skill..."
cp -r "$SKILL_SOURCE/"* "$SKILL_TARGET/"
echo "✅ Skill updated successfully"

# Verify with test script
./scripts/test-skill.sh
```

**2. Skill Versioning**

Add version to SKILL.md frontmatter:

```yaml
---
name: zen-skill
version: 2.0.0
description: AI orchestration and multi-model collaboration
updated: 2025-11-07
---
```

**3. Examples.md Expansion**

Create rich examples.md with:
- Real-world scenarios
- Multi-step workflows
- Common debugging patterns
- Architecture decision examples
- Integration with other tools

## Implementation Checklist

### Phase 1: Critical Fixes (This Week)

- [x] Analyze CLAUDE.md vs zen-skill discrepancies
- [ ] Create skills/zen-skill/ directory in repo
- [ ] Copy current ~/.claude/skills/zen-skill/ to repo
- [ ] Create scripts/install-skill.sh
- [ ] Update run-server.sh with skill installation
- [ ] Test skill installation workflow
- [ ] Update CLAUDE.md with minimal, accurate Zen section
- [ ] Document skill approach in README.md

### Phase 2: Enhancement (Next Week)

- [ ] Create comprehensive examples.md
- [ ] Add skill versioning
- [ ] Create update-skill.sh script
- [ ] Add skill testing to code quality checks
- [ ] Document skill development workflow
- [ ] Create CONTRIBUTING.md with skill update guidelines

### Phase 3: Maintenance (Ongoing)

- [ ] Keep skill in sync with tool changes
- [ ] Collect user feedback on skill usefulness
- [ ] Expand examples based on common use cases
- [ ] Consider separate skills for different workflows
  - zen-debug-skill (focused on debugging)
  - zen-review-skill (focused on code review)
  - zen-plan-skill (focused on planning)

## Testing Strategy

### Skill Installation Testing

```bash
# Test 1: Fresh installation
rm -rf ~/.claude/skills/zen-skill
./scripts/install-skill.sh
./scripts/test-skill.sh

# Test 2: Update existing
./scripts/update-skill.sh
./scripts/test-skill.sh

# Test 3: Integration with run-server.sh
./run-server.sh  # Should install skill automatically
```

### Skill Usage Testing

In Claude Code:

1. List skills: `/skills` → Should show zen-skill
2. Load skill: `/skill zen-skill` → Should load full docs
3. Use tool: Try `mcp__zen__chat` → Should work as documented
4. Verify examples: Test code examples from skill docs

## Migration Path for Users

### For Existing Users

Users with current CLAUDE.md will:

1. **No breaking changes** - Everything continues to work
2. **Get better docs** - Skill provides accurate, complete info
3. **Token savings** - Option to use skill instead of always-loaded docs
4. **Easy transition** - Skill auto-installed on next `run-server.sh`

### Communication

Update docs to explain:

```markdown
## 📢 Important: Zen Documentation Now Available as Skill

To reduce token usage and provide better documentation, Zen CLI
now includes a comprehensive skill instead of loading everything
in CLAUDE.md.

**Migration:**
- Old: Zen docs always loaded in CLAUDE.md (~2,800 tokens)
- New: Zen docs loaded on-demand via skill (~6,500 tokens when needed)
- **Savings:** 80-90% token reduction for non-Zen sessions

**How to use:**
- Type `/skill zen-skill` in Claude Code
- Or use Skill tool: `Skill(skill="zen-skill")`
- Skill is auto-installed by setup script

**Benefits:**
- ✅ Complete docs for all 15 tools
- ✅ Accurate usage examples
- ✅ Troubleshooting guides
- ✅ Only loaded when you need it
```

## Conclusion

### Summary

1. **CLAUDE.md is outdated** - Wrong commands, old models, missing 10 tools
2. **Zen-skill is excellent** - Comprehensive, accurate, well-structured
3. **Skill approach is superior** - Progressive disclosure saves 80-90% tokens
4. **Easy to implement** - Skill exists, just need installation automation

### Recommendation

**Adopt progressive disclosure via skills:**

1. ✅ Move comprehensive docs to zen-skill (already done)
2. ✅ Reduce CLAUDE.md to minimal, accurate guidance (to do)
3. ✅ Automate skill installation in run-server.sh (to do)
4. ✅ Document skill approach in README (to do)

### Expected Outcomes

- **Token efficiency:** 80-90% reduction for non-Zen sessions
- **Better UX:** Accurate, complete documentation when needed
- **Maintainability:** Single source of truth for tool docs
- **Discoverability:** Skills are discoverable via `/skills` command
- **Flexibility:** Can update skill independently of CLAUDE.md

---

**Next Steps:** Implement Phase 1 checklist items this week.

**Date:** 2025-11-07
**Status:** Analysis Complete - Ready for Implementation
