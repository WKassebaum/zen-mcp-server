#!/usr/bin/env python3
"""Fix remaining imports in base_tool.py and other files."""

import re

# Fix base_tool.py specifically
filepath = '/Users/wrk/WorkDev/MCP-Dev/zen-cli/src/zen_cli/tools/shared/base_tool.py'

with open(filepath, 'r') as f:
    content = f.read()

# Fix the remaining imports
replacements = [
    (r'from config import DEFAULT_MODEL', 'from zen_cli.config import DEFAULT_MODEL'),
    (r'from config import OPENROUTER_MODELS', 'from zen_cli.config import OPENROUTER_MODELS'),
    (r'from providers\.registry import ModelProviderRegistry', 'from zen_cli.providers.registry import ModelProviderRegistry'),
    (r'from providers\.base import ProviderType', 'from zen_cli.providers.base import ProviderType'),
    (r'from providers\.openrouter_registry import OpenRouterModelRegistry', 'from zen_cli.providers.openrouter_registry import OpenRouterModelRegistry'),
    (r'from utils\.model_context import ModelContext', 'from zen_cli.utils.model_context import ModelContext'),
    (r'from tools\.models import', 'from zen_cli.tools.models import'),
]

for old, new in replacements:
    content = re.sub(old, new, content)

with open(filepath, 'w') as f:
    f.write(content)

print(f"Fixed imports in {filepath}")

# Also fix workflow_mixin.py
filepath = '/Users/wrk/WorkDev/MCP-Dev/zen-cli/src/zen_cli/tools/workflow/workflow_mixin.py'
try:
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Fix imports
    content = re.sub(r'from providers import', 'from zen_cli.providers import', content)
    content = re.sub(r'from utils import', 'from zen_cli.utils import', content)
    
    with open(filepath, 'w') as f:
        f.write(content)
    print(f"Fixed imports in {filepath}")
except FileNotFoundError:
    print(f"File not found: {filepath}")