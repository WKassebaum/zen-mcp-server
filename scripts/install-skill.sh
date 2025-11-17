#!/bin/bash
# Install Zen CLI Skill for Claude Code
# This script copies the zen-skill from the repo to Claude's skills directory

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

echo -e "${BLUE}📦 Zen CLI Skill Installation${NC}"
echo ""

# Check if source skill exists
if [ ! -d "$SKILL_SOURCE" ]; then
    echo -e "${RED}❌ Skill source not found: $SKILL_SOURCE${NC}"
    echo "   Please ensure you're running this from the zen-cli repository"
    exit 1
fi

# Check required files
if [ ! -f "$SKILL_SOURCE/SKILL.md" ]; then
    echo -e "${RED}❌ SKILL.md not found in source directory${NC}"
    exit 1
fi

# Create target directory if it doesn't exist
if [ ! -d "$HOME/.claude/skills" ]; then
    echo -e "${YELLOW}📁 Creating Claude skills directory...${NC}"
    mkdir -p "$HOME/.claude/skills"
fi

# Check if skill already exists
if [ -d "$SKILL_TARGET" ]; then
    echo -e "${YELLOW}⚠️  Zen skill already installed at: $SKILL_TARGET${NC}"
    echo ""
    read -p "   Overwrite existing installation? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}ℹ️  Installation cancelled${NC}"
        exit 0
    fi
    echo ""
fi

# Copy skill files
echo -e "${BLUE}📋 Copying skill files...${NC}"
mkdir -p "$SKILL_TARGET"
cp -r "$SKILL_SOURCE/"* "$SKILL_TARGET/"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Zen skill installed successfully!${NC}"
else
    echo -e "${RED}❌ Failed to copy skill files${NC}"
    exit 1
fi

# Verify installation
echo ""
echo -e "${BLUE}🔍 Verifying installation...${NC}"

if [ -f "$SKILL_TARGET/SKILL.md" ]; then
    echo -e "${GREEN}✅ SKILL.md found${NC}"
else
    echo -e "${RED}❌ SKILL.md missing${NC}"
    exit 1
fi

if [ -f "$SKILL_TARGET/examples.md" ]; then
    echo -e "${GREEN}✅ examples.md found${NC}"
else
    echo -e "${YELLOW}⚠️  examples.md not found (optional)${NC}"
fi

# Show installation details
echo ""
echo -e "${BLUE}📊 Installation Details:${NC}"
echo "   Source: $SKILL_SOURCE"
echo "   Target: $SKILL_TARGET"
echo "   Files installed:"
for file in "$SKILL_TARGET"/*; do
    filename=$(basename "$file")
    filesize=$(du -h "$file" | cut -f1)
    echo "   - $filename ($filesize)"
done

echo ""
echo -e "${GREEN}✨ Installation complete!${NC}"
echo ""
echo -e "${BLUE}📖 Usage in Claude Code:${NC}"
echo "   • Use Skill tool: ${YELLOW}Skill(skill=\"zen-skill\")${NC}"
echo ""
echo -e "${BLUE}💡 Tip:${NC} The skill provides comprehensive documentation for all 15 Zen MCP tools"
echo ""
