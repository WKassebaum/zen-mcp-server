#!/usr/bin/env python3
"""Fix all remaining tools.models imports."""

import re
import os

def fix_file(filepath):
    """Fix imports in a single file."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    original = content
    
    # Fix tools.models imports
    content = re.sub(r'from tools\.models import', 'from zen_cli.tools.models import', content)
    
    # Fix TYPE_CHECKING imports that are still wrong
    content = re.sub(r'if TYPE_CHECKING:\s*\n\s*from tools\.models import', 
                     'if TYPE_CHECKING:\n    from zen_cli.tools.models import', content)
    
    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        return True
    return False

def main():
    src_dir = '/Users/wrk/WorkDev/MCP-Dev/zen-cli/src/zen_cli'
    fixed = []
    
    for root, dirs, files in os.walk(src_dir):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                if fix_file(filepath):
                    fixed.append(filepath)
    
    print(f"Fixed {len(fixed)} files:")
    for f in fixed:
        print(f"  - {os.path.relpath(f, src_dir)}")

if __name__ == "__main__":
    main()