#!/usr/bin/env python3
"""Test import issue with file_storage"""

import sys
import os
sys.path.insert(0, 'src')
os.environ['ZEN_CLI_MODE'] = '1'

print("1. Starting test...")

# Test importing the module
print("2. Importing file_storage module...")
import zen_cli.utils.file_storage
print("3. Module imported")

# Test getting the function
print("4. Getting function from module...")
get_session_manager = zen_cli.utils.file_storage.get_session_manager
print(f"5. Function obtained: {get_session_manager}")

# Test calling the function
print("6. Calling get_session_manager...")
result = get_session_manager()
print(f"7. Result: {result}")

print("Test complete!")