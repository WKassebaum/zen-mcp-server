#!/usr/bin/env python3
"""Minimal CLI test to isolate hanging issue"""

import click

@click.group()
@click.pass_context
def minimal_cli(ctx):
    """Minimal CLI test"""
    print("CLI group function called")
    ctx.ensure_object(dict)
    ctx.obj['test'] = 'value'
    print("CLI group function completed")

@minimal_cli.command()
@click.argument('message')
@click.pass_context
def chat(ctx, message):
    """Test chat command"""
    print(f"Chat command called with: {message}")
    print(f"Context: {ctx.obj}")

if __name__ == '__main__':
    minimal_cli()