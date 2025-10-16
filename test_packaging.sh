#!/bin/bash
# Test script to verify zen-mcp-server packaging issues
# Usage: ./test_packaging.sh

set -e

COLOR_RED='\033[0;31m'
COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_BLUE='\033[0;34m'
COLOR_RESET='\033[0m'

echo -e "${COLOR_BLUE}=== Zen MCP Server Packaging Verification ===${COLOR_RESET}\n"

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${COLOR_YELLOW}Step 1: Checking source directory...${COLOR_RESET}"
if [ ! -f "server.py" ]; then
    echo -e "${COLOR_RED}ERROR: Not in zen-mcp-server directory${COLOR_RESET}"
    exit 1
fi

echo "✓ Found server.py"

# Count expected conf files
EXPECTED_CONF_FILES=$(find conf -name "*.json" | wc -l | tr -d ' ')
echo "✓ Found $EXPECTED_CONF_FILES JSON files in conf/ directory"
echo ""

echo -e "${COLOR_YELLOW}Step 2: Building package...${COLOR_RESET}"
python -m build --wheel 2>&1 | grep -E "Successfully|ERROR" || true
WHEEL_FILE=$(ls -t dist/*.whl 2>/dev/null | head -1)

if [ -z "$WHEEL_FILE" ]; then
    echo -e "${COLOR_RED}ERROR: Failed to build wheel${COLOR_RESET}"
    exit 1
fi

echo "✓ Built: $WHEEL_FILE"
echo ""

echo -e "${COLOR_YELLOW}Step 3: Checking wheel contents...${COLOR_RESET}"
WHEEL_CONF_COUNT=$(unzip -l "$WHEEL_FILE" | grep -c "conf/.*\.json" || echo "0")
echo "Found $WHEEL_CONF_COUNT JSON files in wheel (expected: $EXPECTED_CONF_FILES)"

if [ "$WHEEL_CONF_COUNT" -eq "0" ]; then
    echo -e "${COLOR_RED}✗ FAIL: No JSON files found in wheel${COLOR_RESET}"
    echo ""
    echo "Wheel contents (conf directory):"
    unzip -l "$WHEEL_FILE" | grep "conf/" || echo "No conf files at all!"
    echo ""
    BUG_STATUS="CONFIRMED"
elif [ "$WHEEL_CONF_COUNT" -lt "$EXPECTED_CONF_FILES" ]; then
    echo -e "${COLOR_YELLOW}⚠ PARTIAL: Only $WHEEL_CONF_COUNT/$EXPECTED_CONF_FILES files included${COLOR_RESET}"
    BUG_STATUS="PARTIAL"
else
    echo -e "${COLOR_GREEN}✓ PASS: All JSON files included in wheel${COLOR_RESET}"
    BUG_STATUS="FIXED"
fi
echo ""

echo -e "${COLOR_YELLOW}Step 4: Testing installation in clean venv...${COLOR_RESET}"
TEST_VENV="/tmp/zen-test-venv-$$"
python -m venv "$TEST_VENV"
source "$TEST_VENV/bin/activate"

echo "Installing wheel..."
pip install "$WHEEL_FILE" --quiet

echo "Checking installed conf directory..."
INSTALLED_CONF=$(python -c "import conf, os; print(os.path.dirname(conf.__file__))")
INSTALLED_COUNT=$(ls "$INSTALLED_CONF"/*.json 2>/dev/null | wc -l | tr -d ' ')

echo "Found $INSTALLED_COUNT JSON files in installed package (expected: $EXPECTED_CONF_FILES)"

if [ "$INSTALLED_COUNT" -eq "0" ]; then
    echo -e "${COLOR_RED}✗ FAIL: No JSON files in installed package${COLOR_RESET}"
    echo ""
    echo "Installed conf directory contents:"
    ls -la "$INSTALLED_CONF"
    INSTALL_STATUS="FAILED"
elif [ "$INSTALLED_COUNT" -lt "$EXPECTED_CONF_FILES" ]; then
    echo -e "${COLOR_YELLOW}⚠ PARTIAL: Only $INSTALLED_COUNT/$EXPECTED_CONF_FILES files installed${COLOR_RESET}"
    INSTALL_STATUS="PARTIAL"
else
    echo -e "${COLOR_GREEN}✓ PASS: All JSON files correctly installed${COLOR_RESET}"
    INSTALL_STATUS="PASSED"
fi

deactivate
rm -rf "$TEST_VENV"
echo ""

echo -e "${COLOR_YELLOW}Step 5: Testing server startup (if installed)...${COLOR_RESET}"
if [ "$INSTALL_STATUS" = "PASSED" ]; then
    # Create temp venv with actual install
    TEST_VENV2="/tmp/zen-server-test-$$"
    python -m venv "$TEST_VENV2"
    source "$TEST_VENV2/bin/activate"
    pip install "$WHEEL_FILE" --quiet

    # Set minimal required env vars
    export GEMINI_API_KEY="test-key"
    export DEFAULT_MODEL="gemini-flash"

    # Try to start server (will timeout quickly)
    echo "Attempting server startup (5 second timeout)..."
    if timeout 5 python -m server 2>&1 | grep -q "ERROR.*No models available"; then
        echo -e "${COLOR_RED}✗ FAIL: Server startup failed with model error${COLOR_RESET}"
        SERVER_STATUS="FAILED"
    elif timeout 5 python -m server 2>&1 | grep -q "ERROR"; then
        echo -e "${COLOR_RED}✗ FAIL: Server startup failed with error${COLOR_RESET}"
        SERVER_STATUS="FAILED"
    else
        echo -e "${COLOR_GREEN}✓ PASS: Server started without fatal errors${COLOR_RESET}"
        SERVER_STATUS="PASSED"
    fi

    deactivate
    rm -rf "$TEST_VENV2"
else
    echo "Skipping (installation failed)"
    SERVER_STATUS="SKIPPED"
fi
echo ""

echo -e "${COLOR_BLUE}=== Test Results Summary ===${COLOR_RESET}\n"

echo -e "Packaging: ${BUG_STATUS}"
echo -e "Installation: ${INSTALL_STATUS}"
echo -e "Server Startup: ${SERVER_STATUS}"
echo ""

if [ "$BUG_STATUS" = "CONFIRMED" ] || [ "$INSTALL_STATUS" = "FAILED" ]; then
    echo -e "${COLOR_RED}❌ BUG CONFIRMED: Packaging issue detected${COLOR_RESET}"
    echo ""
    echo "Details:"
    echo "- Expected: $EXPECTED_CONF_FILES JSON files in conf/"
    echo "- In wheel: $WHEEL_CONF_COUNT files"
    echo "- Installed: $INSTALLED_COUNT files"
    echo ""
    echo "See BUG_REPORT_PACKAGING.md for full details and suggested fixes."
    exit 1
elif [ "$BUG_STATUS" = "PARTIAL" ] || [ "$INSTALL_STATUS" = "PARTIAL" ]; then
    echo -e "${COLOR_YELLOW}⚠️  PARTIAL: Some files missing${COLOR_RESET}"
    exit 1
else
    echo -e "${COLOR_GREEN}✅ ALL TESTS PASSED: Packaging is working correctly${COLOR_RESET}"
    exit 0
fi
