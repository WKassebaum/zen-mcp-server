#!/usr/bin/env python3
"""Test tool execution directly without CLI framework"""

import sys
sys.path.insert(0, 'src')

import asyncio
import os
from zen_cli.main_typer import load_env_files
from zen_cli.config import load_config

# Load environment
load_env_files()
print("Environment loaded")

# Initialize providers manually
from zen_cli.providers.base import ProviderType
from zen_cli.providers.gemini import GeminiModelProvider
from zen_cli.providers.registry import ModelProviderRegistry

gemini_key = os.getenv("GEMINI_API_KEY")
if gemini_key:
    ModelProviderRegistry.register_provider(ProviderType.GOOGLE, GeminiModelProvider)
    print("Gemini provider registered")

# Create tool directly
from zen_cli.tools.chat import ChatTool
tool = ChatTool()
print("Tool created")

# Test async execution directly
async def test_chat():
    print("Executing chat tool...")
    result = await tool.execute({
        'prompt': 'Say hello in 5 words',
        'model': 'gemini-2.5-flash',
        'files': []
    })
    print(f"Result type: {type(result)}")
    if result and hasattr(result[0], 'text'):
        import json
        data = json.loads(result[0].text)
        print(f"Response: {data.get('content', 'No content')[:100]}")
    return result

# Run the async function
print("Starting asyncio.run()...")
result = asyncio.run(test_chat())
print("Done!")