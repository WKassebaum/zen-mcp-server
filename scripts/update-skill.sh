#!/bin/bash
# Update Zen CLI Skill with latest version from repo
# This script updates an existing skill installation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_SOURCE="$REPO_ROOT/skills/zen-skill"
SKILL_TARGET="$HOME/.claude/skills/zen-skill"

echo -e "${BLUE}🔄 Zen CLI Skill Update${NC}"
echo ""

# Check if source skill exists
if [ ! -d "$SKILL_SOURCE" ]; then
    echo -e "${RED}❌ Skill source not found: $SKILL_SOURCE${NC}"
    echo "   Please ensure you're running this from the zen-cli repository"
    exit 1
fi

# Check if target skill exists
if [ ! -d "$SKILL_TARGET" ]; then
    echo -e "${YELLOW}⚠️  Skill not currently installed${NC}"
    echo ""
    read -p "   Install skill now? (Y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo -e "${BLUE}ℹ️  Update cancelled${NC}"
        exit 0
    fi
    echo ""
    echo -e "${BLUE}📦 Running installation...${NC}"
    exec "$SCRIPT_DIR/install-skill.sh"
fi

# Create backup
BACKUP_DIR="$HOME/.claude/skills/.backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/zen-skill_$TIMESTAMP"

echo -e "${BLUE}💾 Creating backup...${NC}"
mkdir -p "$BACKUP_DIR"
cp -r "$SKILL_TARGET" "$BACKUP_PATH"
echo -e "${GREEN}✅ Backup created: $BACKUP_PATH${NC}"
echo ""

# Update skill files
echo -e "${BLUE}📋 Updating skill files...${NC}"
cp -r "$SKILL_SOURCE/"* "$SKILL_TARGET/"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Skill updated successfully!${NC}"
else
    echo -e "${RED}❌ Update failed - restoring backup${NC}"
    rm -rf "$SKILL_TARGET"
    cp -r "$BACKUP_PATH" "$SKILL_TARGET"
    echo -e "${YELLOW}⚠️  Backup restored${NC}"
    exit 1
fi

# Verify update
echo ""
echo -e "${BLUE}🔍 Verifying update...${NC}"

if [ "$SCRIPT_DIR/test-skill.sh" ] && [ -x "$SCRIPT_DIR/test-skill.sh" ]; then
    echo -e "${BLUE}Running validation tests...${NC}"
    "$SCRIPT_DIR/test-skill.sh"
else
    # Basic verification if test script not available
    if [ -f "$SKILL_TARGET/SKILL.md" ]; then
        echo -e "${GREEN}✅ SKILL.md verified${NC}"
    else
        echo -e "${RED}❌ SKILL.md missing after update${NC}"
        exit 1
    fi
fi

# Cleanup old backups (keep last 5)
echo ""
echo -e "${BLUE}🧹 Cleaning up old backups...${NC}"
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR" 2>/dev/null | wc -l | tr -d ' ')
if [ "$BACKUP_COUNT" -gt 5 ]; then
    ls -t "$BACKUP_DIR" | tail -n +6 | xargs -I {} rm -rf "$BACKUP_DIR/{}"
    echo -e "${GREEN}✅ Kept 5 most recent backups${NC}"
else
    echo -e "${GREEN}✅ $BACKUP_COUNT backup(s) retained${NC}"
fi

echo ""
echo -e "${GREEN}✨ Update complete!${NC}"
echo ""
echo -e "${BLUE}📊 Update Details:${NC}"
echo "   Source: $SKILL_SOURCE"
echo "   Target: $SKILL_TARGET"
echo "   Backup: $BACKUP_PATH"
echo ""
echo -e "${BLUE}💡 Tip:${NC} Restart Claude Code to use the updated skill"
echo ""
