#!/usr/bin/env python3
"""Find all imports that don't use zen_cli prefix but should."""

import re
import os

# Local modules that should be imported with zen_cli prefix
LOCAL_MODULES = [
    'config', 'providers', 'utils', 'tools', 'systemprompts', 'types'
]

def check_file(filepath):
    """Check a file for bad imports."""
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    bad_imports = []
    for i, line in enumerate(lines, 1):
        # Check for direct imports
        for module in LOCAL_MODULES:
            # Check "from module import" or "import module"
            if re.match(f'^from {module}\\b', line) or re.match(f'^import {module}\\b', line):
                # Skip if it's already using zen_cli prefix
                if 'zen_cli' not in line:
                    bad_imports.append((i, line.strip()))
    
    return bad_imports

def main():
    src_dir = '/Users/wrk/WorkDev/MCP-Dev/zen-cli/src/zen_cli'
    
    all_bad_imports = []
    
    for root, dirs, files in os.walk(src_dir):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                bad_imports = check_file(filepath)
                if bad_imports:
                    all_bad_imports.append((filepath, bad_imports))
    
    if all_bad_imports:
        print(f"Found {len(all_bad_imports)} files with bad imports:\n")
        for filepath, imports in all_bad_imports:
            print(f"{os.path.relpath(filepath, src_dir)}:")
            for line_num, line in imports:
                print(f"  Line {line_num}: {line}")
            print()
    else:
        print("No bad imports found!")

if __name__ == "__main__":
    main()