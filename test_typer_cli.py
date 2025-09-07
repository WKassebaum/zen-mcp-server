#!/usr/bin/env python3
"""Test script for Typer CLI implementation"""

import sys
sys.path.insert(0, 'src')

from zen_cli.main_typer import cli

if __name__ == '__main__':
    cli()