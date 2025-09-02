#!/usr/bin/env python3
"""
Zen CLI - Main entry point

Command-line interface for Zen MCP Server with 95% token optimization.
Provides two-stage token optimization and direct access to all Zen tools.
"""

import json
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .config import load_config, save_config, get_api_key
from .token_optimizer import TokenOptimizer
from .api_client import ZenAPIClient

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="zen")
@click.pass_context
def cli(ctx):
    """
    Zen CLI - AI-powered development assistant with 95% token optimization.
    
    Two-stage optimization commands:
      zen select <task>  - Analyze task and recommend mode (~200 tokens)
      zen execute <mode> - Execute with minimal schema (~600 tokens)
    
    Direct commands (auto-optimized):
      zen chat    - General AI consultation
      zen debug   - Debug issues systematically  
      zen review  - Code review and quality assessment
      zen analyze - Architecture and code analysis
      zen consensus - Multi-model consensus building
    """
    ctx.ensure_object(dict)
    config = load_config()
    ctx.obj['config'] = config
    ctx.obj['client'] = ZenAPIClient(config)
    ctx.obj['optimizer'] = TokenOptimizer()


@cli.command()
@click.argument('task_description')
@click.option('--confidence', type=click.Choice(['exploring', 'medium', 'high']), 
              default='medium', help='Your confidence level in understanding the task')
@click.option('--context-size', type=click.Choice(['minimal', 'standard', 'comprehensive']),
              default='standard', help='Amount of context available')
@click.pass_context
def select(ctx, task_description, confidence, context_size):
    """
    Stage 1: Analyze task and recommend optimal mode (~200 tokens).
    
    This is the first stage of the two-stage token optimization.
    It analyzes your task and recommends the best mode and parameters
    for Stage 2 execution.
    """
    console.print(f"[bold cyan]🔍 Analyzing task...[/bold cyan]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Selecting optimal mode...", total=None)
        
        optimizer = ctx.obj['optimizer']
        result = optimizer.select_mode(
            task_description=task_description,
            confidence_level=confidence,
            context_size=context_size
        )
        
        progress.stop()
    
    if result['status'] == 'mode_selected':
        console.print(f"[bold green]✅ Mode selected: {result['selected_mode']}[/bold green]")
        console.print(f"Complexity: {result['complexity']}")
        console.print(f"Description: {result['description']}")
        console.print(f"[bold yellow]Token savings: {result.get('token_savings', 'N/A')}[/bold yellow]")
        
        # Show next step
        console.print("\n[bold]Next step:[/bold]")
        console.print(f"Run: [cyan]zen execute {result['selected_mode']} --complexity {result['complexity']}[/cyan]")
        
        # Save selection for next command
        cache_file = Path.home() / '.zen' / 'last_selection.json'
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(result, indent=2))
    else:
        console.print(f"[bold red]❌ Error: {result.get('message', 'Unknown error')}[/bold red]")


@cli.command()
@click.argument('mode', type=click.Choice(
    ['debug', 'review', 'analyze', 'chat', 'consensus', 'security', 'refactor', 'testgen', 'planner', 'tracer']
))
@click.option('--complexity', type=click.Choice(['simple', 'workflow', 'expert']),
              default='simple', help='Task complexity level')
@click.option('--request', '-r', help='JSON request parameters')
@click.option('--from-file', '-f', type=click.Path(exists=True), 
              help='Load request from JSON file')
@click.pass_context
def execute(ctx, mode, complexity, request, from_file):
    """
    Stage 2: Execute with optimized mode and minimal schema (~600 tokens).
    
    This is the second stage of the two-stage token optimization.
    Uses the mode selected in Stage 1 with minimal schema overhead.
    """
    console.print(f"[bold cyan]⚡ Executing {mode} mode...[/bold cyan]")
    
    # Load request parameters
    if from_file:
        with open(from_file, 'r') as f:
            request_params = json.load(f)
    elif request:
        request_params = json.loads(request)
    else:
        # Try to load from last selection
        cache_file = Path.home() / '.zen' / 'last_selection.json'
        if cache_file.exists():
            last_selection = json.loads(cache_file.read_text())
            console.print("[dim]Using parameters from last selection[/dim]")
            request_params = last_selection.get('next_step', {}).get('required_fields', {})
        else:
            console.print("[bold red]❌ No request parameters provided[/bold red]")
            console.print("Use --request or --from-file, or run 'zen select' first")
            return
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task(f"Executing {mode}...", total=None)
        
        optimizer = ctx.obj['optimizer']
        result = optimizer.execute_mode(
            mode=mode,
            complexity=complexity,
            request=request_params
        )
        
        progress.stop()
    
    # Display results
    if result.get('status') == 'success':
        console.print("[bold green]✅ Execution successful[/bold green]")
        if result.get('content'):
            console.print(Markdown(result['content']))
    else:
        console.print(f"[bold red]❌ Error: {result.get('message', 'Unknown error')}[/bold red]")
    
    # Show token optimization stats
    if '_meta' in result:
        meta = result['_meta']
        console.print(f"\n[dim]Token optimization: {meta.get('optimization_level', 'N/A')}[/dim]")
        console.print(f"[dim]Schema size: {meta.get('schema_size', 'N/A')} bytes[/dim]")


@cli.command()
@click.argument('prompt')
@click.option('--model', default='auto', help='Model to use (auto for automatic selection)')
@click.option('--temperature', type=float, help='Temperature for response generation')
@click.pass_context
def chat(ctx, prompt, model, temperature):
    """Quick AI consultation and brainstorming."""
    console.print("[bold cyan]💬 Starting chat...[/bold cyan]")
    
    client = ctx.obj['client']
    response = client.chat(prompt, model=model, temperature=temperature)
    
    if response.get('status') == 'success':
        console.print(Markdown(response['content']))
    else:
        console.print(f"[bold red]❌ Error: {response.get('message', 'Unknown error')}[/bold red]")


@cli.command()
@click.argument('problem')
@click.option('--files', '-f', multiple=True, help='Files to include in debugging')
@click.option('--confidence', type=click.Choice(['exploring', 'medium', 'high']),
              default='exploring', help='Confidence in problem understanding')
@click.pass_context
def debug(ctx, problem, files, confidence):
    """Systematic debugging and root cause analysis."""
    console.print("[bold cyan]🐛 Starting debug session...[/bold cyan]")
    
    # Use two-stage optimization behind the scenes
    optimizer = ctx.obj['optimizer']
    
    # Stage 1: Select mode
    selection = optimizer.select_mode(
        task_description=f"Debug: {problem}",
        confidence_level=confidence
    )
    
    if selection['status'] != 'mode_selected':
        console.print(f"[bold red]❌ Error selecting mode: {selection.get('message')}[/bold red]")
        return
    
    # Stage 2: Execute
    request_params = {
        'problem': problem,
        'files': list(files) if files else [],
        'confidence': confidence
    }
    
    result = optimizer.execute_mode(
        mode='debug',
        complexity=selection['complexity'],
        request=request_params
    )
    
    if result.get('status') == 'success' or result.get('status') == 'pause_for_investigation':
        console.print("[bold green]✅ Debug analysis complete[/bold green]")
        console.print(Markdown(json.dumps(result, indent=2)))
    else:
        console.print(f"[bold red]❌ Error: {result.get('message', 'Unknown error')}[/bold red]")


@cli.command()
@click.option('--profile', help='Configuration profile to use')
@click.pass_context
def config(ctx, profile):
    """Manage configuration and API keys."""
    config = ctx.obj['config']
    
    table = Table(title="Zen CLI Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Config File", str(Path.home() / '.zen' / 'config.yaml'))
    table.add_row("Active Profile", config.get('active_profile', 'default'))
    table.add_row("API Endpoint", config.get('api_endpoint', 'http://localhost:3001'))
    table.add_row("Token Optimization", "Enabled (95% reduction)")
    
    # Check API keys
    for key in ['GEMINI_API_KEY', 'OPENAI_API_KEY']:
        value = get_api_key(key, config)
        display_value = f"{'✅ Set' if value else '❌ Not set'}"
        table.add_row(key, display_value)
    
    console.print(table)


@cli.command()
@click.pass_context
def interactive(ctx):
    """Launch interactive mode with rich terminal UI."""
    console.print("[bold cyan]🚀 Launching interactive mode...[/bold cyan]")
    console.print("[dim]Interactive mode coming soon![/dim]")
    # TODO: Implement interactive mode with textual or prompt_toolkit


@cli.group()
def plugin():
    """Manage Zen CLI plugins."""
    pass


@plugin.command('list')
def plugin_list():
    """List installed plugins."""
    console.print("[bold]Installed Plugins:[/bold]")
    console.print("[dim]Plugin system coming soon![/dim]")


@plugin.command('install')
@click.argument('plugin_name')
def plugin_install(plugin_name):
    """Install a new plugin."""
    console.print(f"[bold cyan]Installing plugin: {plugin_name}[/bold cyan]")
    console.print("[dim]Plugin system coming soon![/dim]")


if __name__ == '__main__':
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        sys.exit(1)