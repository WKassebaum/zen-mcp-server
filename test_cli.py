#!/usr/bin/env python3
"""Test the CLI directly to debug issues."""

import sys
import os

# Add src to path
sys.path.insert(0, '/Users/wrk/WorkDev/MCP-Dev/zen-cli/src')

# Set environment variable for testing
os.environ['GEMINI_API_KEY'] = os.environ.get('GEMINI_API_KEY', 'test-key')

print("Testing Zen CLI...")
print("=" * 50)

# Test imports
try:
    print("1. Testing imports...")
    from zen_cli.main import ZenCLI
    from zen_cli.config import load_config
    print("   ✓ Main imports successful")
except Exception as e:
    print(f"   ✗ Import error: {e}")
    sys.exit(1)

# Test tool creation
try:
    print("2. Creating ZenCLI instance...")
    config = load_config()
    zen = ZenCLI(config)
    print("   ✓ ZenCLI created successfully")
except Exception as e:
    print(f"   ✗ Creation error: {e}")
    sys.exit(1)

# Test chat tool
try:
    print("3. Testing chat tool...")
    result = zen.execute_tool('chat', {'prompt': 'Say hello', 'model': 'auto'})
    print(f"   Result status: {result.get('status')}")
    if result['status'] == 'error':
        print(f"   Error message: {result.get('message')}")
    else:
        print(f"   Success! Response: {result.get('result', '')[:100]}...")
except Exception as e:
    print(f"   ✗ Execution error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("=" * 50)
print("Test complete!")