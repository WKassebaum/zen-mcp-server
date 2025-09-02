#!/usr/bin/env python3
"""
Zen CLI - Standalone AI-powered development assistant

A command-line interface providing direct access to all Zen tools without
requiring an MCP server. Can be called from Claude Code, bash scripts, or
used interactively.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Import our standalone components
from .config import load_config, save_config, get_api_key
from .providers.registry import ModelRegistry
from .utils.conversation_memory import ConversationMemory
from .utils.file_utils import read_files_with_budget

# Import tools
from .tools.chat import ChatTool
from .tools.debug import DebugTool
from .tools.codereview import CodeReviewTool
from .tools.consensus import ConsensusTool
from .tools.analyze import AnalyzeTool
from .tools.planner import PlannerTool
from .tools.thinkdeep import ThinkDeepTool
from .tools.challenge import ChallengeTool
from .tools.precommit import PrecommitTool
from .tools.refactor import RefactorTool
from .tools.secaudit import SecurityAuditTool
from .tools.testgen import TestGeneratorTool
from .tools.docgen import DocGeneratorTool
from .tools.tracer import TracerTool
from .tools.listmodels import ListModelsTool
from .tools.version import VersionTool

console = Console()


class ZenCLI:
    """Main CLI orchestrator for standalone Zen tools."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the CLI with configuration."""
        self.config = config
        self.registry = ModelRegistry()
        self.conversation_memory = ConversationMemory()
        
        # Initialize all tools
        self.tools = {
            'chat': ChatTool(self.registry, self.conversation_memory),
            'debug': DebugTool(self.registry, self.conversation_memory),
            'codereview': CodeReviewTool(self.registry, self.conversation_memory),
            'consensus': ConsensusTool(self.registry, self.conversation_memory),
            'analyze': AnalyzeTool(self.registry, self.conversation_memory),
            'planner': PlannerTool(self.registry, self.conversation_memory),
            'thinkdeep': ThinkDeepTool(self.registry, self.conversation_memory),
            'challenge': ChallengeTool(self.registry, self.conversation_memory),
            'precommit': PrecommitTool(self.registry, self.conversation_memory),
            'refactor': RefactorTool(self.registry, self.conversation_memory),
            'secaudit': SecurityAuditTool(self.registry, self.conversation_memory),
            'testgen': TestGeneratorTool(self.registry, self.conversation_memory),
            'docgen': DocGeneratorTool(self.registry, self.conversation_memory),
            'tracer': TracerTool(self.registry, self.conversation_memory),
            'listmodels': ListModelsTool(self.registry, self.conversation_memory),
            'version': VersionTool(self.registry, self.conversation_memory),
        }
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool with given arguments."""
        if tool_name not in self.tools:
            return {
                'status': 'error',
                'message': f"Unknown tool: {tool_name}"
            }
        
        tool = self.tools[tool_name]
        try:
            result = tool.process_request(arguments)
            return {
                'status': 'success',
                'result': result
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }


@click.group()
@click.version_option(version="1.0.0", prog_name="zen")
@click.pass_context
def cli(ctx):
    """
    Zen CLI - Standalone AI-powered development assistant.
    
    Direct access to all Zen tools without requiring an MCP server.
    Perfect for use with Claude Code, bash scripts, or interactive sessions.
    
    Examples:
      zen chat "Explain REST APIs"
      zen debug "OAuth not working" --files auth.py
      zen codereview --files src/*.py --model gemini-pro
      zen consensus "Should we use microservices?" --models gemini,o3
    """
    ctx.ensure_object(dict)
    config = load_config()
    ctx.obj['config'] = config
    ctx.obj['zen'] = ZenCLI(config)


@cli.command()
@click.argument('prompt')
@click.option('--model', default='auto', help='Model to use (auto for automatic selection)')
@click.option('--temperature', type=float, help='Temperature for response generation')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def chat(ctx, prompt, model, temperature, output_json):
    """General AI consultation and brainstorming."""
    zen = ctx.obj['zen']
    
    arguments = {
        'request': prompt,
        'model': model
    }
    if temperature is not None:
        arguments['temperature'] = temperature
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Thinking...", total=None)
        result = zen.execute_tool('chat', arguments)
        progress.stop()
    
    if output_json:
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")


@cli.command()
@click.argument('problem')
@click.option('--files', '-f', multiple=True, help='Files to include in debugging')
@click.option('--confidence', type=click.Choice(['exploring', 'low', 'medium', 'high', 'certain']),
              default='exploring', help='Confidence in problem understanding')
@click.option('--model', default='auto', help='Model to use')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def debug(ctx, problem, files, confidence, model, output_json):
    """Systematic debugging and root cause analysis."""
    zen = ctx.obj['zen']
    
    arguments = {
        'request': problem,
        'files': list(files) if files else [],
        'confidence': confidence,
        'model': model
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Investigating...", total=None)
        result = zen.execute_tool('debug', arguments)
        progress.stop()
    
    if output_json:
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")


@cli.command()
@click.option('--files', '-f', multiple=True, help='Files to review')
@click.option('--type', 'review_type', type=click.Choice(['quality', 'security', 'performance', 'all']),
              default='quality', help='Type of review')
@click.option('--model', default='auto', help='Model to use')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def codereview(ctx, files, review_type, model, output_json):
    """Professional code review with actionable feedback."""
    zen = ctx.obj['zen']
    
    arguments = {
        'files': list(files) if files else [],
        'review_type': review_type,
        'model': model
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Reviewing code...", total=None)
        result = zen.execute_tool('codereview', arguments)
        progress.stop()
    
    if output_json:
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")


@cli.command()
@click.argument('question')
@click.option('--models', '-m', multiple=True, help='Models to consult')
@click.option('--context-files', '-f', multiple=True, help='Context files')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def consensus(ctx, question, models, context_files, output_json):
    """Build consensus from multiple AI models."""
    zen = ctx.obj['zen']
    
    arguments = {
        'request': question,
        'models': list(models) if models else None,
        'context_files': list(context_files) if context_files else None
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Building consensus...", total=None)
        result = zen.execute_tool('consensus', arguments)
        progress.stop()
    
    if output_json:
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")


@cli.command()
@click.option('--files', '-f', multiple=True, help='Files to analyze')
@click.option('--analysis-type', type=click.Choice(['architecture', 'dependencies', 'patterns', 'all']),
              default='all', help='Type of analysis')
@click.option('--model', default='auto', help='Model to use')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def analyze(ctx, files, analysis_type, model, output_json):
    """Comprehensive code and architecture analysis."""
    zen = ctx.obj['zen']
    
    arguments = {
        'files': list(files) if files else [],
        'analysis_type': analysis_type,
        'model': model
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Analyzing...", total=None)
        result = zen.execute_tool('analyze', arguments)
        progress.stop()
    
    if output_json:
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")


@cli.command()
@click.argument('goal')
@click.option('--context-files', '-f', multiple=True, help='Context files')
@click.option('--model', default='auto', help='Model to use')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def planner(ctx, goal, context_files, model, output_json):
    """Break down complex projects into actionable plans."""
    zen = ctx.obj['zen']
    
    arguments = {
        'request': goal,
        'context_files': list(context_files) if context_files else None,
        'model': model
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Planning...", total=None)
        result = zen.execute_tool('planner', arguments)
        progress.stop()
    
    if output_json:
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")


@cli.command()
@click.argument('topic')
@click.option('--thinking-mode', type=click.Choice(['low', 'medium', 'high', 'max']),
              default='medium', help='Depth of reasoning')
@click.option('--model', default='auto', help='Model to use')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def thinkdeep(ctx, topic, thinking_mode, model, output_json):
    """Extended reasoning and deep analysis."""
    zen = ctx.obj['zen']
    
    arguments = {
        'request': topic,
        'thinking_mode': thinking_mode,
        'model': model
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Deep thinking...", total=None)
        result = zen.execute_tool('thinkdeep', arguments)
        progress.stop()
    
    if output_json:
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")


@cli.command()
@click.option('--format', 'output_format', type=click.Choice(['table', 'json', 'simple']),
              default='table', help='Output format')
@click.pass_context
def listmodels(ctx, output_format):
    """List all available AI models."""
    zen = ctx.obj['zen']
    
    result = zen.execute_tool('listmodels', {})
    
    if output_format == 'json':
        console.print_json(json.dumps(result))
    elif output_format == 'simple':
        if result['status'] == 'success':
            console.print(result['result'])
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")
    else:  # table format
        if result['status'] == 'success':
            # Parse the result and create a table
            console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")


@cli.command()
@click.pass_context
def version(ctx):
    """Show Zen CLI version and configuration."""
    zen = ctx.obj['zen']
    result = zen.execute_tool('version', {})
    
    if result['status'] == 'success':
        console.print(Markdown(result['result']))
    else:
        console.print(f"[bold red]Error: {result['message']}[/bold red]")


@cli.command()
@click.pass_context
def config(ctx):
    """Manage configuration and API keys."""
    config = ctx.obj['config']
    
    table = Table(title="Zen CLI Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Config File", str(Path.home() / '.zen' / 'config.yaml'))
    table.add_row("Active Profile", config.get('active_profile', 'default'))
    
    # Check API keys
    for key in ['GEMINI_API_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'XAI_API_KEY']:
        value = get_api_key(key, config)
        display_value = f"{'✅ Set' if value else '❌ Not set'}"
        table.add_row(key, display_value)
    
    # Check Redis
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    table.add_row("Redis URL", redis_url)
    
    console.print(table)


if __name__ == '__main__':
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        sys.exit(1)