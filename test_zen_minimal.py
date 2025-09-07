#!/usr/bin/env python3
"""Test zen CLI with gradual complexity to identify hang point"""

import sys
sys.path.insert(0, 'src')

import click
import os
from pathlib import Path

# Test 3: Add environment loading
print("Loading environment...")
from zen_cli.main import load_env_files
load_env_files()

print("Importing zen config...")
from zen_cli.config import load_config

print("Importing zen registry...")  
from zen_cli.providers.registry import ModelProviderRegistry

print("Importing ZenCLI...")
from zen_cli.main import ZenCLI

print("Importing cli function...")
from zen_cli.main import cli

print("All zen imports successful")

# Test Click structure with zen initialization
@click.group()
@click.pass_context  
def test_cli(ctx):
    """Test CLI"""
    print("CLI group called")
    ctx.ensure_object(dict)
    
    print("Loading config...")
    config = load_config()
    
    print("Creating registry...")
    registry = ModelProviderRegistry()
    
    print("Creating ZenCLI instance...")
    zen = ZenCLI(config)
    
    print("ZenCLI created successfully")
    print("CLI group completed")

@test_cli.command()
@click.argument('message')
@click.pass_context
def chat(ctx, message):
    """Test chat"""
    print(f"Chat called with: {message}")

if __name__ == '__main__':
    print("Starting actual zen CLI...")
    cli()