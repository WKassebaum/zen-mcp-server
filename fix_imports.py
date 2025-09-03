#!/usr/bin/env python3
"""Fix import paths in zen-cli to use correct module paths"""

import os
import re
from pathlib import Path

def fix_imports_in_file(filepath):
    """Fix imports in a single file"""
    with open(filepath, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # Fix utils imports
    content = re.sub(r'^from utils\.', 'from zen_cli.utils.', content, flags=re.MULTILINE)
    content = re.sub(r'^import utils\.', 'import zen_cli.utils.', content, flags=re.MULTILINE)
    
    # Fix providers imports
    content = re.sub(r'^from providers\.', 'from zen_cli.providers.', content, flags=re.MULTILINE)
    content = re.sub(r'^import providers\.', 'import zen_cli.providers.', content, flags=re.MULTILINE)
    
    # Fix tools imports
    content = re.sub(r'^from tools\.', 'from zen_cli.tools.', content, flags=re.MULTILINE)
    content = re.sub(r'^import tools\.', 'import zen_cli.tools.', content, flags=re.MULTILINE)
    
    # Fix base_tool import
    content = re.sub(r'^from base_tool ', 'from zen_cli.base_tool ', content, flags=re.MULTILINE)
    
    if content != original_content:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Fixed: {filepath}")
        return True
    return False

def main():
    """Fix all imports in the zen-cli source"""
    src_dir = Path('src/zen_cli')
    
    fixed_count = 0
    for filepath in src_dir.rglob('*.py'):
        if fix_imports_in_file(filepath):
            fixed_count += 1
    
    print(f"\nFixed imports in {fixed_count} files")

if __name__ == '__main__':
    main()