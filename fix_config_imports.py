#!/usr/bin/env python3
"""Fix config and systemprompts imports to use zen_cli module path."""

import os
import re
from pathlib import Path

def fix_imports_in_file(filepath):
    """Fix imports in a single Python file."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # Fix config imports
    content = re.sub(r'^from config import', 'from zen_cli.config import', content, flags=re.MULTILINE)
    content = re.sub(r'^import config\b', 'import zen_cli.config as config', content, flags=re.MULTILINE)
    
    # Fix systemprompts imports
    content = re.sub(r'^from systemprompts import', 'from zen_cli.systemprompts import', content, flags=re.MULTILINE)
    content = re.sub(r'^import systemprompts\b', 'import zen_cli.systemprompts as systemprompts', content, flags=re.MULTILINE)
    
    # Fix providers imports
    content = re.sub(r'^from providers import', 'from zen_cli.providers import', content, flags=re.MULTILINE)
    content = re.sub(r'^from providers\.', 'from zen_cli.providers.', content, flags=re.MULTILINE)
    
    # Fix tools imports (but not tools.models which is a special case)
    content = re.sub(r'^from tools\.models import', 'from zen_cli.tools.models import', content, flags=re.MULTILINE)
    
    if content != original_content:
        with open(filepath, 'w') as f:
            f.write(content)
        return True
    return False

def main():
    # Find all Python files in src/zen_cli
    src_dir = Path('/Users/wrk/WorkDev/MCP-Dev/zen-cli/src/zen_cli')
    
    fixed_files = []
    for py_file in src_dir.rglob('*.py'):
        if fix_imports_in_file(py_file):
            fixed_files.append(py_file)
    
    print(f"Fixed {len(fixed_files)} files:")
    for f in fixed_files:
        print(f"  - {f.relative_to(src_dir.parent)}")

if __name__ == "__main__":
    main()