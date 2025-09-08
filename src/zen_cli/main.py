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
from dotenv import load_dotenv

console = Console()

# Load environment variables from multiple locations
def load_env_files():
    """Load .env files from multiple locations in priority order."""
    # Priority order (first found wins for each variable):
    # 1. User config directory .env (primary location)
    # 2. Current directory .env (for project-specific overrides)
    # 3. XDG config directory .env (alternative standard location)
    
    env_locations = [
        Path.home() / '.zen-cli' / '.env',  # Primary config location
        Path.cwd() / '.env',  # Current directory (project-specific)
        Path.home() / '.config' / 'zen-cli' / '.env',  # XDG config standard
    ]
    
    loaded_from = []
    for env_path in env_locations:
        if env_path.exists():
            load_dotenv(env_path, override=False)  # Don't override existing env vars
            loaded_from.append(str(env_path))
    
    # Create config directory quietly (remove console output that might block)
    config_dir = Path.home() / '.zen-cli'
    config_file = config_dir / '.env'
    if not config_file.exists():
        config_dir.mkdir(parents=True, exist_ok=True)
        # Silently skip setup instructions to avoid potential console blocking
    
    return loaded_from

# Remove module-level environment loading entirely - let individual components handle it
# def load_env_files() is still available for explicit calls

# Import our standalone components
from .config import load_config, save_config, get_api_key, __version__
from .providers.registry import ModelProviderRegistry
from .utils.file_utils import read_files

# Lazy import tools to avoid blocking operations during module import
def _get_tool_classes():
    """Lazy import tool classes to avoid blocking during module import."""
    from .tools.chat import ChatTool
    from .tools.debug import DebugIssueTool
    from .tools.codereview import CodeReviewTool
    from .tools.consensus import ConsensusTool
    from .tools.analyze import AnalyzeTool
    from .tools.planner import PlannerTool
    from .tools.thinkdeep import ThinkDeepTool
    from .tools.challenge import ChallengeTool
    from .tools.precommit import PrecommitTool
    from .tools.refactor import RefactorTool
    from .tools.secaudit import SecauditTool
    from .tools.testgen import TestGenTool
    from .tools.docgen import DocgenTool
    from .tools.tracer import TracerTool
    from .tools.listmodels import ListModelsTool
    from .tools.version import VersionTool
    
    return {
        'chat': ChatTool,
        'debug': DebugIssueTool,
        'codereview': CodeReviewTool,
        'consensus': ConsensusTool,
        'analyze': AnalyzeTool,
        'planner': PlannerTool,
        'thinkdeep': ThinkDeepTool,
        'challenge': ChallengeTool,
        'precommit': PrecommitTool,
        'refactor': RefactorTool,
        'secaudit': SecauditTool,
        'testgen': TestGenTool,
        'docgen': DocgenTool,
        'tracer': TracerTool,
        'listmodels': ListModelsTool,
        'version': VersionTool,
    }


class ZenCLI:
    """Main CLI orchestrator for standalone Zen tools."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the CLI with configuration."""
        print("[DEBUG] ZenCLI.__init__ starting")
        self.config = config
        print("[DEBUG] Config set")
        self.registry = ModelProviderRegistry()
        print("[DEBUG] Registry created")
        
        # Initialize and register providers
        print("[DEBUG] Calling _initialize_providers...")
        self._initialize_providers()
        print("[DEBUG] Providers initialized")
        
        # Initialize all tools using lazy loading (tools don't take parameters in constructor)  
        print("[DEBUG] Creating tools dictionary...")
        tool_classes = _get_tool_classes()
        self.tools = {name: tool_class() for name, tool_class in tool_classes.items()}
        print("[DEBUG] All tools created successfully!")
        print("[DEBUG] ZenCLI.__init__ completed")
    
    def _initialize_providers(self, verbose=False):
        """Initialize and register all available providers based on API keys."""
        from zen_cli.providers.base import ProviderType
        
        # Import provider classes
        from zen_cli.providers.gemini import GeminiModelProvider
        from zen_cli.providers.openai_provider import OpenAIModelProvider
        from zen_cli.providers.xai import XAIModelProvider
        from zen_cli.providers.openrouter import OpenRouterProvider
        from zen_cli.providers.anthropic import AnthropicProvider
        
        registered = []
        
        # Register Gemini provider if API key is available
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key and gemini_key != "your_gemini_api_key_here":
            ModelProviderRegistry.register_provider(ProviderType.GOOGLE, GeminiModelProvider)
            registered.append("Gemini")
        
        # Register OpenAI provider if API key is available
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key and openai_key != "your_openai_api_key_here":
            ModelProviderRegistry.register_provider(ProviderType.OPENAI, OpenAIModelProvider)
            registered.append("OpenAI")
        
        # Register XAI provider if API key is available
        xai_key = os.getenv("XAI_API_KEY")
        if xai_key and xai_key != "your_xai_api_key_here":
            ModelProviderRegistry.register_provider(ProviderType.XAI, XAIModelProvider)
            registered.append("X.AI")
        
        # Register OpenRouter provider if API key is available
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key and openrouter_key != "your_openrouter_api_key_here":
            ModelProviderRegistry.register_provider(ProviderType.OPENROUTER, OpenRouterProvider)
            registered.append("OpenRouter")
        
        # Register Anthropic provider if API key is available
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key and anthropic_key != "your_anthropic_api_key_here":
            ModelProviderRegistry.register_provider(ProviderType.ANTHROPIC, AnthropicProvider)
            registered.append("Anthropic")
        
        # Only show messages if verbose or if no providers registered
        if verbose or not registered:
            if registered:
                console.print(f"[green]✓ Providers registered:[/green] {', '.join(registered)}")
            else:
                console.print("[yellow]Warning: No AI providers configured. Set API keys for Gemini, OpenAI, X.AI, OpenRouter, or Anthropic[/yellow]")
        
        return registered
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool with given arguments."""
        print(f"[DEBUG] execute_tool called with tool_name={tool_name}, arguments={arguments}")
        
        if tool_name not in self.tools:
            return {
                'status': 'error',
                'message': f"Unknown tool: {tool_name}"
            }
        
        tool = self.tools[tool_name]
        try:
            # AUTO-SESSION MANAGEMENT
            # Inject auto-session continuation_id unless manually specified
            if "continuation_id" not in arguments or not arguments["continuation_id"]:
                # Skip auto-sessions for utility tools that don't benefit from persistence
                utility_tools = {"listmodels", "version"}
                if tool_name not in utility_tools:
                    try:
                        from zen_cli.utils.file_storage import get_session_manager
                        session_manager = get_session_manager()
                        auto_session_id = session_manager.get_or_create_auto_session()
                        arguments["continuation_id"] = auto_session_id
                        print(f"[DEBUG] Auto-session: {auto_session_id}")
                    except Exception as e:
                        print(f"[DEBUG] Auto-session creation failed, continuing without: {e}")
            
            # AUTO MODEL RESOLUTION (copied from server.py logic)
            # Handle auto model resolution before tool execution
            model_name = arguments.get("model", "auto")
            print(f"[DEBUG] Initial model_name: {model_name}")
            
            if model_name.lower() == "auto":
                print("[DEBUG] Auto model detected, resolving...")
                # Get tool category to determine appropriate model
                tool_category = tool.get_model_category()
                print(f"[DEBUG] Tool category: {tool_category}")
                
                resolved_model = self.registry.get_preferred_fallback_model(tool_category)
                print(f"[DEBUG] Resolved model: {resolved_model}")
                
                console.print(f"[dim]Auto mode: using {resolved_model} for {tool_name}[/dim]")
                arguments["model"] = resolved_model
                print(f"[DEBUG] Updated arguments: {arguments}")
            
            print("[DEBUG] About to call tool.execute()")
            # Tools have async execute method, we need to run it synchronously
            import asyncio
            result = asyncio.run(tool.execute(arguments))
            print(f"[DEBUG] Tool execute completed with result type: {type(result)}")
            
            # Convert TextContent to string for display
            if result and hasattr(result[0], 'text'):
                return {
                    'status': 'success',
                    'result': result[0].text
                }
            return {
                'status': 'success',
                'result': str(result)
            }
        except Exception as e:
            print(f"[DEBUG] Exception in execute_tool: {e}")
            import traceback
            print(f"[DEBUG] Traceback: {traceback.format_exc()}")
            return {
                'status': 'error',
                'message': str(e)
            }


@click.group()
@click.version_option(version=__version__, prog_name="zen")
@click.option('--session', '-s', help='Conversation session ID (auto-creates if not specified)')
@click.option('--format', 'output_format', type=click.Choice(['auto', 'json', 'markdown', 'plain']), 
              default='auto', help='Output format (auto adapts to context)')
@click.option('--project', '-p', help='Project to use (overrides current project)')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.option('--config-file', help='Custom config file path')
@click.pass_context
def cli(ctx, session, output_format, project, verbose, config_file):
    """Zen CLI - Standalone AI-powered development assistant."""
    # Do absolutely nothing in the group function to avoid hanging
    pass

def _get_zen_instance(ctx):
    """Lazy initialization of ZenCLI instance only when needed."""
    # Initialize context object if it doesn't exist
    if ctx.obj is None:
        ctx.obj = {}
    
    if not ctx.obj.get('_zen_initialized', False):
        # Load environment and config only when actually needed
        try:
            load_env_files()
        except Exception:
            pass  # Silently continue if env loading fails
        
        config = load_config()
        ctx.obj['config'] = config  
        ctx.obj['zen'] = ZenCLI(config)
        ctx.obj['_zen_initialized'] = True
    
    return ctx.obj['zen']



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
@click.argument('message')
@click.option('--model', default='auto', help='Model to use (auto, gpt-5, gemini-2.5-flash, etc.)')
@click.option('--files', '-f', multiple=True, help='Files to include in the conversation')
@click.option('--session', help='Specific session ID to use (overrides auto-session)')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def chat(ctx, message, model, files, session, output_json):
    """Chat with AI assistant."""
    zen = _get_zen_instance(ctx)
    
    tool_args = {
        'prompt': message,  # ChatTool expects 'prompt' not 'query'
        'model': model,
        'files': list(files) if files else []
    }
    
    if session:
        tool_args['continuation_id'] = session
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Thinking...", total=None)
        result = zen.execute_tool('chat', tool_args)
        progress.stop()
    
    if output_json:
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")


@cli.command()
@click.pass_context  
def sessions(ctx):
    """List active conversation sessions."""
    try:
        from zen_cli.utils.file_storage import get_storage_backend, get_session_manager
        from datetime import datetime
        
        storage = get_storage_backend()
        session_manager = get_session_manager()
        
        # Get current auto-session identity
        current_auto_session = session_manager.get_session_identity()
        
        # List active conversations
        active_conversations = storage.list_active_conversations()
        
        if not active_conversations:
            console.print("[dim]No active conversation sessions found.[/dim]")
            return
            
        console.print("[bold]Active Conversation Sessions:[/bold]\n")
        
        for session_id, metadata in active_conversations:
            created_time = datetime.fromtimestamp(metadata['created_at']).strftime('%Y-%m-%d %H:%M:%S')
            expires_time = datetime.fromtimestamp(metadata['expires_at']).strftime('%Y-%m-%d %H:%M:%S')
            
            # Mark current auto-session
            is_current = "✓ " if session_id == current_auto_session else "  "
            
            console.print(f"{is_current}[cyan]{session_id}[/cyan]")
            console.print(f"   Created:  {created_time}")
            console.print(f"   Expires:  {expires_time}")
            console.print()
            
        console.print(f"[dim]Current auto-session: {current_auto_session}[/dim]")
        console.print("[dim]Use --session <id> to use a specific session[/dim]")
            
    except Exception as e:
        console.print(f"[red]Error listing sessions: {e}[/red]")


@cli.group()
def config():
    """Manage configuration, projects, and API keys."""
    pass


@config.command(name='show')
@click.option('--format', 'output_format', type=click.Choice(['table', 'json']), default='table')
def config_show(output_format):
    """Show current configuration."""
    try:
        from zen_cli.utils.config_manager import get_config_manager
        
        config_manager = get_config_manager()
        config = config_manager.get_config()
        
        if output_format == 'json':
            import json
            console.print_json(json.dumps(config_manager.export_config(), indent=2))
            return
        
        # Display as table
        table = Table(title="Zen CLI Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Config File", str(config_manager.config_file))
        table.add_row("Current Project", config.current_project or "[dim]None[/dim]")
        table.add_row("Storage Type", config.storage.type)
        table.add_row("Default Model", config.models.default_provider)
        
        # API Keys
        providers = ['gemini', 'openai', 'xai', 'openrouter', 'anthropic']
        for provider in providers:
            api_key = config_manager.get_api_key(provider)
            status = "✅ Set" if api_key else "❌ Not set"
            table.add_row(f"{provider.title()} API Key", status)
        
        # Projects
        projects = config_manager.list_projects()
        table.add_row("Total Projects", str(len(projects)))
        
        console.print(table)
        
        # Show projects if any exist
        if projects:
            console.print("\n[bold]Projects:[/bold]")
            for project in projects[:5]:  # Show first 5
                status = "🟢" if project['is_current'] else "⚪"
                console.print(f"  {status} {project['name']} - {project['description'] or '[dim]No description[/dim]'}")
            
            if len(projects) > 5:
                console.print(f"  ... and {len(projects) - 5} more projects")
    
    except Exception as e:
        console.print(f"[red]Error showing configuration: {e}[/red]")


@config.command(name='set')
@click.argument('key')
@click.argument('value')
@click.option('--project', help='Set for specific project')
def config_set(key, value, project):
    """Set configuration value."""
    try:
        from zen_cli.utils.config_manager import get_config_manager
        
        config_manager = get_config_manager()
        
        if project:
            config_manager.set_current_project(project)
        
        # Handle API keys
        if key.endswith('_api_key') or key.endswith('-api-key'):
            provider = key.replace('_api_key', '').replace('-api-key', '').lower()
            config_manager.set_api_key(provider, value, project_specific=bool(project))
            console.print(f"✅ Set {provider} API key")
        else:
            console.print(f"[yellow]Setting '{key}' not yet supported. Use 'zen config show' to see available settings.[/yellow]")
    
    except Exception as e:
        console.print(f"[red]Error setting configuration: {e}[/red]")


@config.command(name='health')
def config_health():
    """Check configuration health."""
    try:
        from zen_cli.utils.config_manager import get_config_manager
        from zen_cli.utils.storage_backend import get_storage_backend
        
        config_manager = get_config_manager()
        
        # Check config health
        config_health = config_manager.health_check()
        
        table = Table(title="Configuration Health Check")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details", style="dim")
        
        # Config system
        status = "✅ Healthy" if config_health['healthy'] else "❌ Unhealthy"
        details = f"Projects: {config_health.get('projects_count', 0)}"
        table.add_row("Configuration", status, details)
        
        # Storage backend
        try:
            storage = get_storage_backend()
            if hasattr(storage, 'health_check'):
                storage_health = storage.health_check()
                if storage_health['healthy']:
                    status = "✅ Healthy"
                    details = f"Backend: {storage_health['backend']}"
                else:
                    status = "❌ Unhealthy"
                    details = storage_health.get('error', 'Unknown error')
            else:
                status = "✅ Healthy"
                details = f"Backend: {type(storage).__name__}"
            table.add_row("Storage", status, details)
        except Exception as e:
            table.add_row("Storage", "❌ Error", str(e))
        
        # API Keys
        providers = ['gemini', 'openai', 'xai']
        configured_keys = 0
        for provider in providers:
            if config_manager.get_api_key(provider):
                configured_keys += 1
        
        status = "✅ Ready" if configured_keys > 0 else "⚠️ No keys"
        details = f"{configured_keys}/{len(providers)} providers configured"
        table.add_row("API Keys", status, details)
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error checking configuration health: {e}[/red]")


@cli.group()
def project():
    """Manage projects and project switching."""
    pass


@project.command(name='list')
@click.option('--format', 'output_format', type=click.Choice(['table', 'json']), default='table')
def project_list(output_format):
    """List all projects."""
    try:
        from zen_cli.utils.config_manager import get_config_manager
        
        config_manager = get_config_manager()
        projects = config_manager.list_projects()
        
        if output_format == 'json':
            import json
            console.print_json(json.dumps(projects, indent=2))
            return
        
        if not projects:
            console.print("[dim]No projects configured. Use 'zen project create' to create one.[/dim]")
            return
        
        table = Table(title="Projects")
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="white") 
        table.add_column("Storage", style="green")
        table.add_column("API Keys", style="yellow")
        table.add_column("Last Used", style="dim")
        table.add_column("Current", style="bold")
        
        for project in projects:
            current = "🟢" if project['is_current'] else ""
            last_used = project['last_used'][:10] if project['last_used'] else "Never"
            
            table.add_row(
                project['name'],
                project['description'] or "[dim]No description[/dim]",
                project['storage_type'],
                str(project['api_keys_configured']),
                last_used,
                current
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error listing projects: {e}[/red]")


@project.command(name='create')
@click.argument('name')
@click.option('--description', '-d', help='Project description')
@click.option('--storage', type=click.Choice(['file', 'redis', 'memory']), default='file')
@click.option('--set-current', is_flag=True, help='Set as current project')
def project_create(name, description, storage, set_current):
    """Create a new project."""
    try:
        from zen_cli.utils.config_manager import get_config_manager, StorageConfig
        
        config_manager = get_config_manager()
        
        # Create project with custom storage
        storage_config = StorageConfig(type=storage)
        
        project = config_manager.create_project(
            name=name,
            description=description or f"Project {name}",
            storage=storage_config
        )
        
        if set_current:
            config_manager.set_current_project(name)
            console.print(f"✅ Created and set '{name}' as current project")
        else:
            console.print(f"✅ Created project '{name}'")
            
    except Exception as e:
        console.print(f"[red]Error creating project: {e}[/red]")


@project.command(name='switch')
@click.argument('name')
def project_switch(name):
    """Switch to a different project."""
    try:
        from zen_cli.utils.config_manager import get_config_manager
        
        config_manager = get_config_manager()
        config_manager.set_current_project(name)
        
        console.print(f"✅ Switched to project '{name}'")
        
    except Exception as e:
        console.print(f"[red]Error switching project: {e}[/red]")


@project.command(name='delete')
@click.argument('name')
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
def project_delete(name, confirm):
    """Delete a project."""
    try:
        from zen_cli.utils.config_manager import get_config_manager
        
        if not confirm:
            import click
            if not click.confirm(f"Delete project '{name}'? This cannot be undone."):
                console.print("Cancelled.")
                return
        
        config_manager = get_config_manager()
        config_manager.delete_project(name)
        
        console.print(f"✅ Deleted project '{name}'")
        
    except Exception as e:
        console.print(f"[red]Error deleting project: {e}[/red]")


@cli.command()
@click.option('--model', default='auto', help='Default model for interactive session')
@click.option('--session', help='Conversation session to continue (overrides global --session)')
@click.pass_context
def interactive(ctx, model, session):
    """Start interactive chat session with conversation continuity."""
    try:
        console.print("[bold blue]🧘 Zen CLI Interactive Mode[/bold blue]")
        console.print("Type your messages and press Enter. Use '/help' for commands, '/quit' to exit.")
        console.print(f"[dim]Model: {model} | Session: {session or 'auto-generated'}[/dim]\n")
        
        # Get global session override
        global_session = ctx.obj.get('global_session')
        active_session = session or global_session
        
        zen = ctx.obj['zen']
        conversation_count = 0
        
        while True:
            try:
                # Get user input
                user_input = console.input("[bold cyan]You:[/bold cyan] ").strip()
                
                if not user_input:
                    continue
                
                # Handle special commands
                if user_input.startswith('/'):
                    if user_input in ['/quit', '/exit', '/q']:
                        console.print("[dim]Goodbye! 👋[/dim]")
                        break
                    elif user_input == '/help':
                        console.print("""
[bold]Interactive Commands:[/bold]
/help    - Show this help
/quit    - Exit interactive mode  
/clear   - Start new conversation
/model   - Show current model
/session - Show current session ID
/switch <model> - Switch to different model

Just type your message and press Enter to chat!
""")
                        continue
                    elif user_input == '/clear':
                        # Start fresh conversation
                        active_session = None
                        conversation_count = 0
                        console.print("[dim]Started new conversation[/dim]")
                        continue
                    elif user_input == '/model':
                        console.print(f"[dim]Current model: {model}[/dim]")
                        continue
                    elif user_input == '/session':
                        console.print(f"[dim]Current session: {active_session or 'auto-generated'}[/dim]")
                        continue
                    elif user_input.startswith('/switch '):
                        new_model = user_input[8:].strip()
                        if new_model:
                            model = new_model
                            console.print(f"[dim]Switched to model: {model}[/dim]")
                        else:
                            console.print("[yellow]Usage: /switch <model_name>[/yellow]")
                        continue
                    else:
                        console.print(f"[yellow]Unknown command: {user_input}. Type '/help' for help.[/yellow]")
                        continue
                
                # Execute chat
                arguments = {
                    'prompt': user_input,
                    'model': model
                }
                
                if active_session:
                    arguments['continuation_id'] = active_session
                
                # Show thinking indicator
                with console.status("[dim]Thinking...[/dim]", spinner="dots"):
                    result = zen.execute_tool('chat', arguments)
                
                # Display response
                if result.get('status') == 'success':
                    console.print(f"[bold green]Zen:[/bold green] {result['result']}")
                    
                    # Extract session ID for continuation
                    if not active_session and 'continuation_offer' in result:
                        active_session = result['continuation_offer'].get('continuation_id')
                    
                    conversation_count += 1
                else:
                    console.print(f"[red]Error: {result.get('message', 'Unknown error')}[/red]")
                
                console.print("")  # Add spacing
                
            except KeyboardInterrupt:
                console.print("\n[dim]Use '/quit' to exit or continue chatting...[/dim]")
                continue
            except EOFError:
                console.print("\n[dim]Goodbye! 👋[/dim]")
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                continue
    
    except Exception as e:
        console.print(f"[red]Failed to start interactive mode: {e}[/red]")


@cli.command()
@click.option('--last', is_flag=True, help='Continue the most recent conversation')
@click.option('--session', help='Specific session to continue')
@click.pass_context
def continue_chat(ctx, last, session):
    """Continue a previous conversation."""
    try:
        if not last and not session:
            console.print("[yellow]Please specify --last or --session <id>[/yellow]")
            return
        
        if last:
            # Find the most recent session
            from zen_cli.utils.file_storage import get_storage_backend
            storage = get_storage_backend()
            conversations = storage.list_active_conversations()
            
            if not conversations:
                console.print("[dim]No recent conversations found[/dim]")
                return
            
            # Use the most recently used session
            session = conversations[0][0]
            console.print(f"[dim]Continuing conversation: {session}[/dim]")
        
        # Start interactive mode with the specified session
        ctx.invoke(interactive, session=session)
        
    except Exception as e:
        console.print(f"[red]Error continuing conversation: {e}[/red]")


if __name__ == '__main__':
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        sys.exit(1)