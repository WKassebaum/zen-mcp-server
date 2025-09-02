#!/usr/bin/env python3
"""
Diagnostic script for token optimization issues.
Run this to check if token optimization is properly configured and working.
"""

import os
import sys
import json
from pathlib import Path

print("=" * 60)
print("Token Optimization Diagnostic Tool")
print("=" * 60)

# 1. Check environment variables
print("\n1. ENVIRONMENT VARIABLES:")
print("-" * 40)
token_opt = os.getenv("ZEN_TOKEN_OPTIMIZATION", "enabled")
opt_mode = os.getenv("ZEN_OPTIMIZATION_MODE", "two_stage")
telemetry = os.getenv("ZEN_TOKEN_TELEMETRY", "true")
version = os.getenv("ZEN_OPTIMIZATION_VERSION", "v5.12.0")

print(f"ZEN_TOKEN_OPTIMIZATION = {token_opt} (default: enabled)")
print(f"ZEN_OPTIMIZATION_MODE = {opt_mode} (default: two_stage)")
print(f"ZEN_TOKEN_TELEMETRY = {telemetry} (default: true)")
print(f"ZEN_OPTIMIZATION_VERSION = {version} (default: v5.12.0)")

if token_opt == "disabled":
    print("❌ WARNING: Token optimization is explicitly DISABLED!")
elif token_opt in ["enabled", "auto"]:
    print("✅ Token optimization is ENABLED")
else:
    print(f"⚠️  WARNING: Unknown value '{token_opt}' - optimization will be DISABLED")
    print("   Valid values: enabled, disabled, auto")

# 2. Check if .env file exists and contains settings
print("\n2. .ENV FILE CHECK:")
print("-" * 40)
env_file = Path(".env")
if env_file.exists():
    print("✅ .env file exists")
    with open(env_file) as f:
        env_content = f.read()
        if "ZEN_TOKEN_OPTIMIZATION" in env_content:
            print("✅ ZEN_TOKEN_OPTIMIZATION found in .env")
        else:
            print("⚠️  ZEN_TOKEN_OPTIMIZATION NOT in .env (using default: enabled)")
        
        if "ZEN_OPTIMIZATION_MODE" in env_content:
            print("✅ ZEN_OPTIMIZATION_MODE found in .env")
        else:
            print("⚠️  ZEN_OPTIMIZATION_MODE NOT in .env (using default: two_stage)")
else:
    print("⚠️  No .env file found - using all defaults")

# 3. Check if required files exist
print("\n3. REQUIRED FILES:")
print("-" * 40)
required_files = [
    "server_token_optimized.py",
    "token_optimization_config.py",
    "tools/mode_selector.py",
    "tools/mode_executor.py",
    "tools/zen_execute.py"
]

all_files_exist = True
for file in required_files:
    if Path(file).exists():
        print(f"✅ {file}")
    else:
        print(f"❌ {file} - MISSING!")
        all_files_exist = False

if not all_files_exist:
    print("\n❌ CRITICAL: Required files missing! Are you on the right branch?")
    print("   Run: git checkout token-optimization-two-stage")

# 4. Test imports
print("\n4. IMPORT TEST:")
print("-" * 40)
try:
    from token_optimization_config import token_config
    print("✅ token_optimization_config imports successfully")
    print(f"   - Enabled: {token_config.is_enabled()}")
    print(f"   - Mode: {token_config.mode}")
    print(f"   - Two-stage: {token_config.is_two_stage()}")
except Exception as e:
    print(f"❌ Failed to import token_optimization_config: {e}")

try:
    from server_token_optimized import get_optimized_tools
    print("✅ server_token_optimized imports successfully")
    
    # Test get_optimized_tools
    tools = get_optimized_tools()
    if tools is None:
        print("❌ get_optimized_tools() returned None - optimization DISABLED")
    else:
        print(f"✅ get_optimized_tools() returned {len(tools)} tools")
        if "zen_select_mode" in tools:
            print("   ✅ zen_select_mode found")
        else:
            print("   ❌ zen_select_mode NOT found")
        
        if "zen_execute" in tools:
            print("   ✅ zen_execute found")
        else:
            print("   ❌ zen_execute NOT found")
except Exception as e:
    print(f"❌ Failed to import server_token_optimized: {e}")

try:
    from tools.mode_selector import ModeSelectorTool
    print("✅ ModeSelectorTool imports successfully")
except Exception as e:
    print(f"❌ Failed to import ModeSelectorTool: {e}")

try:
    from tools.zen_execute import ZenExecuteTool
    print("✅ ZenExecuteTool imports successfully")
except Exception as e:
    print(f"❌ Failed to import ZenExecuteTool: {e}")

# 5. Summary and recommendations
print("\n" + "=" * 60)
print("DIAGNOSIS SUMMARY:")
print("=" * 60)

if token_opt in ["enabled", "auto"] and all_files_exist:
    try:
        from server_token_optimized import get_optimized_tools
        tools = get_optimized_tools()
        if tools and "zen_select_mode" in tools and "zen_execute" in tools:
            print("✅ Token optimization should be WORKING!")
            print("\nIf you're still seeing 43k tokens:")
            print("1. Restart the server after running this diagnostic")
            print("2. Check server logs for 'Token Optimization Configuration'")
            print("3. Verify Claude Desktop sees zen_select_mode and zen_execute tools")
        else:
            print("❌ Token optimization is NOT working properly")
            print("\nProblem: get_optimized_tools() not returning expected tools")
            print("This usually means token_config.is_enabled() is False")
    except:
        print("❌ Token optimization is NOT working due to import errors")
else:
    print("❌ Token optimization is NOT configured properly")
    print("\nTo fix:")
    print("1. Add to your .env file:")
    print("   ZEN_TOKEN_OPTIMIZATION=enabled")
    print("   ZEN_OPTIMIZATION_MODE=two_stage")
    print("2. Ensure you're on branch: token-optimization-two-stage")
    print("3. Restart the server")

print("\n" + "=" * 60)