#!/usr/bin/env python3
"""
Zen CLI - Typer Implementation
Migrated from Click to resolve hanging issues and improve maintainability.
"""

import json
import logging
import os
import sys

# Set CLI mode to disable background threads that cause hanging
os.environ["ZEN_CLI_MODE"] = "1"
from pathlib import Path
from typing import Optional, List
from enum import Enum

import typer

logger = logging.getLogger(__name__)
from rich.console import Console
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from dotenv import load_dotenv

# Import our standalone components
from .config import load_config, save_config, get_api_key, __version__
from .providers.registry import ModelProviderRegistry
from .utils.file_utils import read_files
from .utils import validators

# Create the Typer app
app = typer.Typer(
    name="zen",
    help="Zen CLI - Standalone AI-powered development assistant.\n\n"
         "Direct access to all Zen tools without requiring an MCP server.\n"
         "Perfect for use with Claude Code, bash scripts, or interactive sessions.",
    add_completion=False,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False
)

# Rich console for output
console = Console()

# Global state management
class State:
    """Global state for CLI application."""
    def __init__(self):
        self.zen = None
        self.config = None
        self.verbose = False
        self.output_format = "auto"
        self.session = None
        self.project = None
        self._initialized = False

state = State()

# Output format enum
class OutputFormat(str, Enum):
    auto = "auto"
    json = "json"
    markdown = "markdown"
    plain = "plain"

def load_env_files():
    """Load .env files from multiple locations in priority order."""
    env_locations = [
        Path.home() / '.zen-cli' / '.env',
        Path.cwd() / '.env',
        Path.home() / '.config' / 'zen-cli' / '.env',
    ]
    
    loaded_from = []
    for env_path in env_locations:
        if env_path.exists():
            load_dotenv(env_path, override=False)
            loaded_from.append(str(env_path))
    
    # Create config directory quietly
    config_dir = Path.home() / '.zen-cli'
    config_file = config_dir / '.env'
    if not config_file.exists():
        config_dir.mkdir(parents=True, exist_ok=True)
    
    return loaded_from

def get_tool_classes():
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
    
    def __init__(self, config: dict):
        """Initialize the CLI with configuration."""
        self.config = config
        self.registry = ModelProviderRegistry()
        
        # Initialize and register providers
        self._initialize_providers()
        
        # Lazy tool loading - don't initialize until needed
        self.tools = {}  # Will be populated on demand
        self._tool_classes = None  # Will be loaded when first needed
    
    def _initialize_providers(self, verbose=False):
        """Initialize and register all available providers based on API keys."""
        from .providers.base import ProviderType
        from .providers.gemini import GeminiModelProvider
        from .providers.openai_provider import OpenAIModelProvider
        
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
        
        if verbose and registered:
            console.print(f"[green]✓ Providers registered:[/green] {', '.join(registered)}")
        elif verbose:
            console.print("[yellow]Warning: No AI providers configured. Set GEMINI_API_KEY or OPENAI_API_KEY[/yellow]")
        
        return registered
    
    def _get_tool_classes(self):
        """Lazy load tool classes only when needed."""
        if self._tool_classes is None:
            self._tool_classes = get_tool_classes()
        return self._tool_classes
    
    def _get_tool(self, tool_name: str):
        """Get or create a tool instance on demand."""
        if tool_name not in self.tools:
            tool_classes = self._get_tool_classes()
            if tool_name not in tool_classes:
                return None
            
            # Lazy loading tool
            self.tools[tool_name] = tool_classes[tool_name]()
        
        return self.tools[tool_name]
    
    def execute_tool(self, tool_name: str, arguments: dict) -> dict:
        """Execute a tool with given arguments."""
        tool = self._get_tool(tool_name)
        if tool is None:
            return {
                'status': 'error',
                'message': f"Unknown tool: {tool_name}"
            }
        try:
            # AUTO-SESSION MANAGEMENT
            # Use UUID for unique session IDs to prevent collisions
            if "continuation_id" not in arguments or not arguments["continuation_id"]:
                utility_tools = {"listmodels", "version"}
                if tool_name not in utility_tools:
                    import uuid
                    arguments["continuation_id"] = f"cli_session_{uuid.uuid4().hex[:8]}"
            
            # AUTO MODEL RESOLUTION
            model_name = arguments.get("model", "auto")
            if model_name.lower() == "auto":
                tool_category = tool.get_model_category()
                resolved_model = self.registry.get_preferred_fallback_model(tool_category)
                if state.verbose:
                    console.print(f"[dim]Auto mode: using {resolved_model} for {tool_name}[/dim]")
                arguments["model"] = resolved_model
            
            # Use synchronous execution for CLI context
            from .tools.sync_wrapper import execute_tool_sync
            result = execute_tool_sync(tool_name, tool, arguments, registry=self.registry)
            
            # Convert result to consistent format
            if isinstance(result, dict):
                # Already in the right format
                return result
            elif hasattr(result, 'text'):
                # TextContent object
                return {
                    'status': 'success',
                    'result': result.text
                }
            elif isinstance(result, list) and result and hasattr(result[0], 'text'):
                # List of TextContent
                return {
                    'status': 'success',
                    'result': result[0].text
                }
            else:
                return {
                    'status': 'success',
                    'result': str(result)
                }
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }

def get_zen_instance() -> ZenCLI:
    """Lazy initialization of ZenCLI instance only when needed."""
    if not state._initialized:
        # Load environment and config only when actually needed
        load_env_files()
        state.config = load_config()
        state.zen = ZenCLI(state.config)
        state._initialized = True
    return state.zen

@app.callback()
def main(
    session: Optional[str] = typer.Option(None, "--session", "-s", 
                                          help="Conversation session ID (auto-creates if not specified)"),
    output_format: OutputFormat = typer.Option(OutputFormat.auto, "--format",
                                               help="Output format (auto adapts to context)"),
    project: Optional[str] = typer.Option(None, "--project", "-p",
                                          help="Project to use (overrides current project)"),
    verbose: bool = typer.Option(False, "--verbose", "-v",
                                 help="Enable verbose output"),
    config_file: Optional[str] = typer.Option(None, "--config-file",
                                              help="Custom config file path"),
    version: bool = typer.Option(None, "--version",
                                 help="Show version and exit")
):
    """
    Initialize global state for all commands.
    This callback runs before any command.
    """
    # Handle version flag specially
    if version:
        typer.echo(f"zen, version {__version__}")
        raise typer.Exit()
    
    # Store global options in state
    state.session = session
    state.output_format = output_format.value
    state.project = project
    state.verbose = verbose
    
    # Set project context if specified
    if project:
        try:
            from .utils.config_manager import get_config_manager
            config_manager = get_config_manager()
            config_manager.set_current_project(project)
        except Exception as e:
            if verbose:
                console.print(f"[yellow]Warning: Could not set project '{project}': {e}[/yellow]")

# === Command Implementations ===

@app.command()
def chat(
    message: str = typer.Argument(..., help="Your question or message"),
    model: str = typer.Option("auto", help="Model to use (auto, gpt-5, gemini-2.5-flash, etc.)"),
    files: List[str] = typer.Option([], "--files", "-f", help="Files to include in the conversation"),
    session: Optional[str] = typer.Option(None, help="Specific session ID to use (overrides auto-session)"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Chat with AI assistant."""
    zen = get_zen_instance()
    
    tool_args = {
        'prompt': message,
        'model': model,
        'files': list(files) if files else []
    }
    
    if session or state.session:
        tool_args['continuation_id'] = session or state.session
    
    # Execute the tool
    result = zen.execute_tool('chat', tool_args)
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            # Parse the JSON result
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except:
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def debug(
    problem: str = typer.Argument(..., help="Problem description"),
    files: List[str] = typer.Option([], "--files", "-f", help="Files to include in debugging"),
    confidence: str = typer.Option("exploring", help="Confidence in problem understanding"),
    model: str = typer.Option("auto", help="Model to use"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Systematic debugging and root cause analysis."""
    zen = get_zen_instance()
    
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
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def listmodels(
    format: str = typer.Option("table", help="Output format")
):
    """List all available AI models."""
    zen = get_zen_instance()
    
    result = zen.execute_tool('listmodels', {})
    
    if format == 'json':
        console.print_json(json.dumps(result))
    elif format == 'simple':
        if result['status'] == 'success':
            console.print(result['result'])
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")
    else:  # table format
        if result['status'] == 'success':
            # Parse the result and create a table
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except:
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def version():
    """Show Zen CLI version and configuration."""
    zen = get_zen_instance()
    result = zen.execute_tool('version', {})
    
    if result['status'] == 'success':
        try:
            result_data = json.loads(result['result'])
            console.print(Markdown(result_data.get('content', result['result'])))
        except:
            console.print(Markdown(result['result']))
    else:
        console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def consensus(
    prompt: str = typer.Argument(..., help="Question or decision to get consensus on"),
    models: List[str] = typer.Option(["gemini-2.5-flash", "gpt-5"], "--models", "-m", 
                                      help="Models to consult for consensus"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Get multi-model consensus on a decision or question."""
    zen = get_zen_instance()
    
    # Format models for the tool
    model_list = [{"model": m} for m in models]
    
    tool_args = {
        'prompt': prompt,
        'models': model_list
    }
    
    result = zen.execute_tool('consensus', tool_args)
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except (json.JSONDecodeError, KeyError, TypeError):
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def analyze(
    files: List[str] = typer.Option(..., "--files", "-f", help="Files to analyze"),
    analysis_type: str = typer.Option("general", help="Type of analysis (general, architecture, complexity)"),
    model: str = typer.Option("auto", help="Model to use"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Analyze code files for architecture, complexity, or general insights."""
    zen = get_zen_instance()
    
    # Read file contents for analysis
    file_contents = read_files(list(files))
    
    tool_args = {
        'files': list(files),
        'file_contents': file_contents,
        'analysis_type': analysis_type,
        'model': model
    }
    
    result = zen.execute_tool('analyze', tool_args)
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except (json.JSONDecodeError, KeyError, TypeError):
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def codereview(
    files: List[str] = typer.Option(..., "--files", "-f", help="Files to review"),
    review_type: str = typer.Option(ReviewType.ALL.value, help="Type of review (all, security, performance, quality)"),
    model: str = typer.Option(MODEL_AUTO, help="Model to use"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Perform code review on specified files."""
    zen = get_zen_instance()
    
    # Validate inputs
    try:
        validated_files = validators.validate_file_paths(list(files))
        review_type = validators.validate_review_type(review_type)
        model = validators.validate_model_name(model, zen.registry)
    except typer.BadParameter as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    
    # Read file contents for the tool
    from .utils.file_utils import read_files
    file_contents = read_files(validated_files)
    
    tool_args = {
        'files': list(files),
        'file_contents': file_contents,  # Pass actual content
        'type': review_type,
        'model': model
    }
    
    result = zen.execute_tool('codereview', tool_args)
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except (json.JSONDecodeError, KeyError, TypeError):
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def planner(
    goal: str = typer.Argument(..., help="Goal or task to plan"),
    context_files: List[str] = typer.Option([], "--files", "-f", help="Context files for planning"),
    model: str = typer.Option("auto", help="Model to use"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Break down complex tasks through step-by-step planning."""
    zen = get_zen_instance()
    
    tool_args = {
        'request': {
            'step': f"Planning for: {goal}",
            'step_number': 1,
            'total_steps': 3,
            'next_step_required': False
        },
        'model': model
    }
    
    if context_files:
        from .utils.file_utils import read_files
        file_contents = read_files(list(context_files))
        if file_contents:
            tool_args['request']['context'] = file_contents
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Planning...", total=None)
        result = zen.execute_tool('planner', tool_args)
        progress.stop()
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except (json.JSONDecodeError, KeyError, TypeError):
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def testgen(
    files: List[str] = typer.Option(..., "--files", "-f", help="Files to generate tests for"),
    test_type: str = typer.Option("unit", help="Type of tests (unit, integration, edge)"),
    model: str = typer.Option("auto", help="Model to use"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Generate comprehensive tests with edge case analysis."""
    zen = get_zen_instance()
    
    # Read file contents for test generation
    file_contents = read_files(list(files))
    
    tool_args = {
        'request': {
            'step': f"Generating {test_type} tests",
            'step_number': 1,
            'total_steps': 2,
            'next_step_required': False,
            'files_checked': list(files),
            'file_contents': file_contents,
            'findings': f"Analyzing code for {test_type} test generation"
        },
        'model': model
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Generating tests...", total=None)
        result = zen.execute_tool('testgen', tool_args)
        progress.stop()
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except (json.JSONDecodeError, KeyError, TypeError):
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def refactor(
    files: List[str] = typer.Option(..., "--files", "-f", help="Files to analyze for refactoring"),
    focus: str = typer.Option("all", help="Focus area (all, codesmells, decompose, modernize, organization)"),
    model: str = typer.Option("auto", help="Model to use"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Analyze code for refactoring opportunities."""
    zen = get_zen_instance()
    
    # Read file contents for refactoring analysis
    file_contents = read_files(list(files))
    
    tool_args = {
        'request': {
            'step': f"Analyzing for {focus} refactoring opportunities",
            'step_number': 1,
            'total_steps': 2,
            'next_step_required': False,
            'files_checked': list(files),
            'file_contents': file_contents,
            'findings': f"Searching for {focus} refactoring opportunities",
            'confidence': 'exploring'
        },
        'model': model
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Analyzing refactoring opportunities...", total=None)
        result = zen.execute_tool('refactor', tool_args)
        progress.stop()
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except (json.JSONDecodeError, KeyError, TypeError):
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def secaudit(
    files: List[str] = typer.Option(..., "--files", "-f", help="Files to audit for security"),
    scope: str = typer.Option("web", help="Security scope (web, mobile, API, enterprise, cloud)"),
    threat_level: str = typer.Option("medium", help="Threat level (low, medium, high, critical)"),
    model: str = typer.Option("auto", help="Model to use"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Comprehensive security audit with vulnerability assessment."""
    zen = get_zen_instance()
    
    # Read file contents for security audit
    file_contents = read_files(list(files))
    
    tool_args = {
        'request': {
            'step': f"Security audit for {scope} application",
            'step_number': 1,
            'total_steps': 3,
            'next_step_required': False,
            'files_checked': list(files),
            'file_contents': file_contents,
            'findings': f"Performing security audit with {threat_level} threat level",
            'confidence': 'exploring',
            'security_scope': scope,
            'threat_level': threat_level
        },
        'model': model
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Performing security audit...", total=None)
        result = zen.execute_tool('secaudit', tool_args)
        progress.stop()
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except (json.JSONDecodeError, KeyError, TypeError):
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def tracer(
    target: str = typer.Argument(..., help="Function or method to trace"),
    files: List[str] = typer.Option([], "--files", "-f", help="Files to analyze"),
    trace_mode: str = typer.Option("ask", help="Trace mode (ask, precision, dependencies)"),
    model: str = typer.Option("auto", help="Model to use"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Trace code execution flow and dependencies."""
    zen = get_zen_instance()
    
    # Read file contents if provided
    file_contents = read_files(list(files)) if files else None
    
    tool_args = {
        'request': {
            'step': f"Tracing {target}",
            'step_number': 1,
            'total_steps': 3,
            'next_step_required': False,
            'files_checked': list(files) if files else [],
            'file_contents': file_contents if file_contents else '',
            'findings': f"Analyzing execution flow for {target}",
            'confidence': 'exploring',
            'trace_mode': trace_mode,
            'target_description': target
        },
        'model': model
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Tracing execution flow...", total=None)
        result = zen.execute_tool('tracer', tool_args)
        progress.stop()
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except (json.JSONDecodeError, KeyError, TypeError):
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def docgen(
    files: List[str] = typer.Option(..., "--files", "-f", help="Files to document"),
    complexity: bool = typer.Option(True, help="Include Big O complexity analysis"),
    flow: bool = typer.Option(True, help="Include call flow documentation"),
    model: str = typer.Option("auto", help="Model to use"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Generate comprehensive documentation with complexity analysis."""
    zen = get_zen_instance()
    
    # Read file contents for documentation generation
    file_contents = read_files(list(files))
    
    tool_args = {
        'request': {
            'step': "Generating documentation",
            'step_number': 1,
            'total_steps': len(files) + 1,
            'next_step_required': False,
            'relevant_files': list(files),
            'file_contents': file_contents,
            'findings': "Analyzing code for documentation",
            'num_files_documented': 0,
            'total_files_to_document': len(files),
            'document_complexity': complexity,
            'document_flow': flow
        },
        'model': model
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Generating documentation...", total=None)
        result = zen.execute_tool('docgen', tool_args)
        progress.stop()
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except (json.JSONDecodeError, KeyError, TypeError):
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def precommit(
    path: str = typer.Option(".", "--path", "-p", help="Path to git repository"),
    compare_to: Optional[str] = typer.Option(None, help="Git ref to compare against"),
    focus: Optional[str] = typer.Option(None, help="Focus area (security, performance, test coverage)"),
    model: str = typer.Option("auto", help="Model to use"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Pre-commit validation with comprehensive checks."""
    zen = get_zen_instance()
    
    import os
    absolute_path = os.path.abspath(path)
    
    tool_args = {
        'request': {
            'step': "Pre-commit validation",
            'step_number': 1,
            'total_steps': 3,
            'next_step_required': False,
            'findings': "Analyzing git changes for pre-commit validation",
            'path': absolute_path,
            'precommit_type': 'external',
            'include_staged': True,
            'include_unstaged': True
        },
        'model': model
    }
    
    if compare_to:
        tool_args['request']['compare_to'] = compare_to
    if focus:
        tool_args['request']['focus_on'] = focus
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Validating changes...", total=None)
        result = zen.execute_tool('precommit', tool_args)
        progress.stop()
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except (json.JSONDecodeError, KeyError, TypeError):
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def thinkdeep(
    problem: str = typer.Argument(..., help="Complex problem to analyze"),
    files: List[str] = typer.Option([], "--files", "-f", help="Relevant files"),
    model: str = typer.Option("auto", help="Model to use"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Extended reasoning for complex problem analysis."""
    zen = get_zen_instance()
    
    # Read file contents if provided
    file_contents = read_files(list(files)) if files else None
    
    tool_args = {
        'request': {
            'step': f"Deep analysis of: {problem}",
            'step_number': 1,
            'total_steps': 3,
            'next_step_required': False,
            'findings': "Beginning deep reasoning analysis",
            'files_checked': list(files) if files else [],
            'file_contents': file_contents if file_contents else '',
            'confidence': 'low'
        },
        'model': model
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Deep thinking...", total=None)
        result = zen.execute_tool('thinkdeep', tool_args)
        progress.stop()
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except (json.JSONDecodeError, KeyError, TypeError):
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

@app.command()
def challenge(
    statement: str = typer.Argument(..., help="Statement to critically analyze"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Challenge ideas with critical thinking."""
    zen = get_zen_instance()
    
    tool_args = {
        'prompt': statement
    }
    
    result = zen.execute_tool('challenge', tool_args)
    
    if output_json or state.output_format == "json":
        console.print_json(json.dumps(result))
    else:
        if result['status'] == 'success':
            try:
                result_data = json.loads(result['result'])
                console.print(Markdown(result_data.get('content', result['result'])))
            except (json.JSONDecodeError, KeyError, TypeError):
                console.print(Markdown(result['result']))
        else:
            console.print(f"[bold red]Error: {result['message']}[/bold red]")

def cli():
    """Entry point for the CLI."""
    app()

if __name__ == "__main__":
    cli()