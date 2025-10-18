#!/bin/bash
# Test script for Zen MCP Skill structure validation

set -e

SKILL_DIR="$HOME/.claude/skills/zen-skill"

echo "🔍 Testing Zen MCP Skill Structure..."
echo

# Check directory exists
if [ ! -d "$SKILL_DIR" ]; then
    echo "❌ Skill directory not found: $SKILL_DIR"
    exit 1
fi
echo "✅ Skill directory exists"

# Check SKILL.md exists and has frontmatter
if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
    echo "❌ SKILL.md not found"
    exit 1
fi
echo "✅ SKILL.md found"

if ! head -1 "$SKILL_DIR/SKILL.md" | grep -q "^---$"; then
    echo "❌ SKILL.md missing YAML frontmatter opening (---)"
    exit 1
fi
echo "✅ YAML frontmatter found"

if ! grep -q "^name:" "$SKILL_DIR/SKILL.md"; then
    echo "❌ Missing 'name:' field"
    exit 1
fi
echo "✅ 'name' field found"

if ! grep -q "^description:" "$SKILL_DIR/SKILL.md"; then
    echo "❌ Missing 'description:' field"
    exit 1
fi
echo "✅ 'description' field found"

# Check examples.md exists
if [ ! -f "$SKILL_DIR/examples.md" ]; then
    echo "⚠️  examples.md not found (optional but recommended)"
else
    echo "✅ examples.md found"
fi

# Validate content sections exist
echo
echo "🔍 Validating SKILL.md content sections..."

sections=(
    "When to Use Zen MCP"
    "Auto-Trigger Scenarios"
    "Available MCP Tools"
    "Best Practices"
    "Common Patterns"
    "Troubleshooting"
)

for section in "${sections[@]}"; do
    if ! grep -q "$section" "$SKILL_DIR/SKILL.md"; then
        echo "⚠️  Section '$section' not found"
    else
        echo "✅ Section '$section' present"
    fi
done

echo
echo "✅ All skill structure checks passed!"
echo
echo "📏 Skill Size:"
echo "  SKILL.md: $(wc -l < "$SKILL_DIR/SKILL.md") lines"
[ -f "$SKILL_DIR/examples.md" ] && echo "  examples.md: $(wc -l < "$SKILL_DIR/examples.md") lines"

echo
echo "📝 YAML Frontmatter:"
head -5 "$SKILL_DIR/SKILL.md"

echo
echo "✨ Zen MCP Skill is ready for use!"
