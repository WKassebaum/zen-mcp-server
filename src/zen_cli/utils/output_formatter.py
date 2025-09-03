"""
Output formatting utilities for consistent CLI responses

This module provides utilities for formatting command output consistently
across all zen CLI commands, supporting multiple output formats and 
context-aware formatting.
"""

import json
import sys
from typing import Any, Dict, Optional
from rich.console import Console
from rich.markdown import Markdown
from rich.json import JSON
from rich.table import Table

console = Console()


def format_output(data: Any, format_type: str = 'auto', context: str = 'general') -> None:
    """
    Format and display output based on the specified format type.
    
    Args:
        data: Data to format and display
        format_type: Output format ('auto', 'json', 'markdown', 'plain')
        context: Context hint for auto-formatting ('chat', 'list', 'status', etc.)
    """
    if format_type == 'json':
        _format_json(data)
    elif format_type == 'markdown':
        _format_markdown(data)
    elif format_type == 'plain':
        _format_plain(data)
    else:  # auto
        _format_auto(data, context)


def _format_json(data: Any) -> None:
    """Format output as JSON"""
    try:
        if isinstance(data, dict):
            console.print_json(json.dumps(data, indent=2))
        elif hasattr(data, '__dict__'):
            console.print_json(json.dumps(data.__dict__, indent=2, default=str))
        else:
            console.print_json(json.dumps({'result': str(data)}, indent=2))
    except Exception:
        # Fallback for non-serializable data
        console.print_json(json.dumps({'result': str(data)}, indent=2))


def _format_markdown(data: Any) -> None:
    """Format output as Markdown"""
    if isinstance(data, dict) and 'result' in data:
        content = str(data['result'])
        # If content already looks like markdown, render it
        if any(marker in content for marker in ['#', '*', '-', '```', '>']):
            console.print(Markdown(content))
        else:
            console.print(content)
    else:
        console.print(str(data))


def _format_plain(data: Any) -> None:
    """Format output as plain text"""
    if isinstance(data, dict) and 'result' in data:
        print(data['result'])
    else:
        print(str(data))


def _format_auto(data: Any, context: str) -> None:
    """Auto-detect best format based on data and context"""
    if isinstance(data, dict):
        if 'status' in data:
            # Tool response format
            if data.get('status') == 'success':
                result = data.get('result', '')
                if context == 'chat' and isinstance(result, str):
                    # Chat responses often contain markdown
                    if any(marker in result for marker in ['#', '*', '-', '```', '>']):
                        console.print(Markdown(result))
                    else:
                        console.print(result)
                else:
                    console.print(result)
            else:
                # Error case
                error_msg = data.get('message', 'Unknown error')
                console.print(f"[red]Error: {error_msg}[/red]")
        elif 'content' in data:
            # Alternative content format
            console.print(data['content'])
        else:
            # Generic dictionary - check context
            if context in ['list', 'status']:
                # For list/status commands, pretty print as table if possible
                console.print(data)
            else:
                # Default to JSON for structured data
                _format_json(data)
    else:
        # Simple string/other data
        console.print(str(data))


def format_error(error: str, format_type: str = 'auto') -> None:
    """Format and display error messages consistently"""
    if format_type == 'json':
        error_data = {'status': 'error', 'message': error}
        console.print_json(json.dumps(error_data, indent=2))
    else:
        console.print(f"[red]Error: {error}[/red]")


def format_success(message: str, format_type: str = 'auto') -> None:
    """Format and display success messages consistently"""
    if format_type == 'json':
        success_data = {'status': 'success', 'message': message}
        console.print_json(json.dumps(success_data, indent=2))
    else:
        console.print(f"[green]✅ {message}[/green]")


def format_warning(message: str, format_type: str = 'auto') -> None:
    """Format and display warning messages consistently"""
    if format_type == 'json':
        warning_data = {'status': 'warning', 'message': message}
        console.print_json(json.dumps(warning_data, indent=2))
    else:
        console.print(f"[yellow]⚠️  {message}[/yellow]")


def format_tool_response(result: Dict[str, Any], format_type: str = 'auto', 
                        context: str = 'general', show_metadata: bool = False) -> None:
    """
    Format tool response with optional metadata display.
    
    Args:
        result: Tool response dictionary
        format_type: Output format preference
        context: Context for auto-formatting
        show_metadata: Whether to show tool metadata (model used, etc.)
    """
    format_output(result, format_type, context)
    
    if show_metadata and isinstance(result, dict) and 'metadata' in result:
        metadata = result['metadata']
        if format_type != 'json':  # Don't double-print for JSON format
            console.print(f"\n[dim]Model: {metadata.get('model_used', 'unknown')} | "
                         f"Provider: {metadata.get('provider_used', 'unknown')}[/dim]")


def create_status_table(title: str, data: Dict[str, str]) -> Table:
    """Create a consistent status table"""
    table = Table(title=title)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    for key, value in data.items():
        table.add_row(key, str(value))
    
    return table