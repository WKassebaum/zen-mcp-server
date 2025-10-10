#!/usr/bin/env python3
"""
Zen CLI - Standalone command-line interface for Zen MCP Server

Provides direct access to all Zen AI tools without requiring an MCP server.
Compatible with Claude Code, CI/CD pipelines, and interactive terminal use.

Architecture:
- Uses root providers/ (catalog-based, from main v8.0.0)
- Uses root tools/ (MCP tools, adapted for CLI)
- Adds CLI-specific features in src/zen_cli/utils/
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

# Load environment variables from ~/.zen/.env
zen_config_dir = Path.home() / ".zen"
env_file = zen_config_dir / ".env"

# CRITICAL: Load CLI env vars BEFORE any imports that use get_env()
# Must update both os.environ (for os.getenv) and utils.env's _DOTENV_VALUES (for override mode)
if env_file.exists():
    from dotenv import dotenv_values
    cli_env_values = dotenv_values(env_file)

    # 1. Set in os.environ so os.getenv() finds them
    for key, value in cli_env_values.items():
        if value is not None:
            os.environ[key] = value

    # 2. Update utils.env's _DOTENV_VALUES for override mode
    from utils.env import reload_env
    reload_env(cli_env_values)

# NOW safe to import modules that use get_env() - they'll see CLI's .env values
from config import __version__
from providers.registry import ModelProviderRegistry
from providers.shared import ProviderType

# Import providers from root
from providers.gemini import GeminiModelProvider
from providers.openai import OpenAIModelProvider
from providers.anthropic import AnthropicProvider
from providers.azure_openai import AzureOpenAIProvider
from providers.xai import XAIModelProvider
from providers.dial import DIALModelProvider
from providers.openrouter import OpenRouterProvider
from providers.custom import CustomProvider

# Import tools from root (import individually in commands to avoid name conflicts)
# from tools import chat, debug, codereview, consensus, analyze, planner, thinkdeep
# from tools import challenge, precommit, refactor, secaudit, testgen, docgen

# Import utilities (get_env imported via reload_env above)
from utils.env import get_env

console = Console()
logger = logging.getLogger(__name__)


class ZenCLI:
    """Main CLI orchestrator that bridges CLI commands to MCP tools."""

    def __init__(self, verbose: bool = False):
        """Initialize CLI with provider registry."""
        self.verbose = verbose
        self.registry = ModelProviderRegistry()
        self._initialize_providers()

    def _initialize_providers(self):
        """Register all available providers based on API keys (from server.py pattern)."""
        registered = []

        # Gemini provider
        if get_env("GEMINI_API_KEY"):
            ModelProviderRegistry.register_provider(ProviderType.GOOGLE, GeminiModelProvider)
            registered.append("Gemini")

        # OpenAI provider
        if get_env("OPENAI_API_KEY"):
            ModelProviderRegistry.register_provider(ProviderType.OPENAI, OpenAIModelProvider)
            registered.append("OpenAI")

        # Anthropic provider
        if get_env("ANTHROPIC_API_KEY"):
            ModelProviderRegistry.register_provider(ProviderType.ANTHROPIC, AnthropicProvider)
            registered.append("Anthropic")

        # Azure OpenAI provider
        if get_env("AZURE_OPENAI_KEY") and get_env("AZURE_OPENAI_ENDPOINT"):
            ModelProviderRegistry.register_provider(ProviderType.AZURE, AzureOpenAIProvider)
            registered.append("Azure")

        # X.AI provider
        if get_env("XAI_API_KEY"):
            ModelProviderRegistry.register_provider(ProviderType.XAI, XAIModelProvider)
            registered.append("X.AI")

        # DIAL provider
        if get_env("DIAL_API_KEY") and get_env("DIAL_API_URL"):
            ModelProviderRegistry.register_provider(ProviderType.DIAL, DIALModelProvider)
            registered.append("DIAL")

        # Custom provider (Ollama, etc.)
        custom_url = get_env("CUSTOM_API_URL")
        if custom_url:
            # Use factory pattern for custom provider
            def custom_provider_factory(api_key: str):
                return CustomProvider(api_key=api_key or "", base_url=custom_url)

            ModelProviderRegistry.register_provider(ProviderType.CUSTOM, custom_provider_factory)
            registered.append("Custom")

        # OpenRouter provider (always enabled as fallback)
        if get_env("OPENROUTER_API_KEY"):
            ModelProviderRegistry.register_provider(ProviderType.OPENROUTER, OpenRouterProvider)
            registered.append("OpenRouter")

        if self.verbose:
            if registered:
                console.print(f"[green]✓ Providers registered:[/green] {', '.join(registered)}")
            else:
                console.print("[yellow]⚠ No providers configured. Set API keys for at least one provider.[/yellow]")

        return registered


def _present_workflow_step(result: dict, session_id: str, tool_name: str):
    """
    Present workflow step results with clear continuation guidance.

    Args:
        result: Enhanced workflow result with continuation instructions
        session_id: Session identifier
        tool_name: Name of the workflow tool
    """
    # Header with session info
    console.print(f"\n[bold cyan]{'='*70}[/bold cyan]")
    console.print(f"[bold]Workflow Session:[/bold] [yellow]{session_id}[/yellow]")
    console.print(f"[bold]Tool:[/bold] {tool_name}")
    console.print(f"[bold]Step:[/bold] {result.get('step_number', '?')}/{result.get('total_steps', '?')}")
    console.print(f"[bold cyan]{'='*70}[/bold cyan]\n")

    # Main content
    if "content" in result and result["content"]:
        console.print(Markdown(result["content"]))
    elif "step" in result:
        console.print(Markdown(result["step"]))

    # Workflow status and continuation
    if result.get("workflow_status") == "in_progress":
        console.print(f"\n[bold yellow]⚠️  Workflow Continuation Required[/bold yellow]\n")

        # Show continuation command
        if "continuation_command" in result:
            console.print("[dim]To continue this workflow, run:[/dim]")
            console.print(f"[green]{result['continuation_command']}[/green]\n")

        # Show manual user instructions
        if "workflow_instructions" in result and "for_manual_users" in result["workflow_instructions"]:
            console.print("[dim]" + result["workflow_instructions"]["for_manual_users"] + "[/dim]")

    elif result.get("workflow_status") == "complete":
        console.print(f"\n[bold green]✓ Workflow Complete![/bold green]")
        console.print("[dim]Session has been automatically cleaned up.[/dim]")


# Global context object for Click
@click.group()
@click.version_option(version=__version__, prog_name="zen")
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.pass_context
def cli(ctx, verbose):
    """Zen CLI - AI-powered development assistant

    Provides direct access to multi-model AI orchestration for code analysis,
    debugging, reviews, and more. Compatible with Claude Code and terminal use.

    Examples:
        zen chat "Explain REST APIs"
        zen debug "OAuth not working" --files auth.py
        zen codereview --files src/*.py --type security
        zen consensus "Microservices vs monolith?" --models gemini-pro,o3
    """
    # Create ZenCLI instance and store in context
    ctx.ensure_object(dict)
    ctx.obj['zen'] = ZenCLI(verbose=verbose)


def _get_zen_instance(ctx: click.Context) -> ZenCLI:
    """Helper to get ZenCLI instance from context."""
    if ctx.obj is None:
        ctx.obj = {}
    if 'zen' not in ctx.obj:
        ctx.obj['zen'] = ZenCLI(verbose=False)
    return ctx.obj['zen']


@cli.command()
@click.argument('message')
@click.option('--model', default='auto', help='Model to use (default: auto)')
@click.option('--files', '-f', multiple=True, help='Context files to include')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def chat(ctx, message, model, files, output_json):
    """Chat with AI for brainstorming and quick consultations

    Examples:
        zen chat "Explain REST APIs"
        zen chat "Best practices for error handling" --model gemini-pro
        zen chat "Analyze this code" --files app.py
    """
    zen = _get_zen_instance(ctx)

    # Prepare arguments for chat tool
    arguments = {
        "prompt": message,
        "model": model,
        "working_directory": os.getcwd(),
    }

    # Add files if provided
    if files:
        arguments["files"] = list(files)

    # Execute chat tool asynchronously
    try:
        from tools.chat import ChatTool
        result = asyncio.run(ChatTool().execute(arguments))

        if output_json:
            console.print_json(data=result)
        else:
            # Pretty print the response
            if isinstance(result, dict) and 'content' in result:
                console.print(Markdown(result['content']))
            else:
                console.print(result)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        sys.exit(1)


@cli.command()
@click.argument('problem')
@click.option('--files', '-f', multiple=True, help='Files to analyze')
@click.option('--confidence', type=click.Choice(['exploring', 'low', 'medium', 'high', 'certain']),
              default='exploring', help='Initial confidence level')
@click.option('--model', default='auto', help='Model to use')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def debug(ctx, problem, files, confidence, model, output_json):
    """Debug issues with systematic investigation

    Examples:
        zen debug "OAuth tokens not persisting" --files auth.py session.py
        zen debug "Memory leak after 1000 requests" --confidence medium
    """
    zen = _get_zen_instance(ctx)

    arguments = {
        "problem_description": problem,
        "confidence": confidence,
        "model": model,
        "working_directory": os.getcwd(),
    }

    if files:
        arguments["files"] = list(files)

    try:
        from tools.debug import DebugIssueTool
        result = asyncio.run(DebugIssueTool().execute(arguments))

        if output_json:
            console.print_json(data=result)
        else:
            if isinstance(result, dict) and 'content' in result:
                console.print(Markdown(result['content']))
            else:
                console.print(result)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        sys.exit(1)


@cli.command()
@click.option('--files', '-f', multiple=True, help='Files to review')
@click.option('--type', 'review_type', type=click.Choice(['quality', 'security', 'performance', 'all']),
              default='all', help='Type of review')
@click.option('--model', default='auto', help='Model to use')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def codereview(ctx, files, review_type, model, output_json):
    """Professional code review with severity levels

    Examples:
        zen codereview --files src/*.py --type security
        zen codereview --files auth/ payment/ --type all
    """
    zen = _get_zen_instance(ctx)

    if not files:
        console.print("[yellow]Warning:[/yellow] No files specified. Use --files to specify files to review.")
        return

    arguments = {
        "files": list(files),
        "review_type": review_type,
        "model": model,
        "working_directory": os.getcwd(),
    }

    try:
        from tools.codereview import CodeReviewTool
        result = asyncio.run(CodeReviewTool().execute(arguments))

        if output_json:
            console.print_json(data=result)
        else:
            if isinstance(result, dict) and 'content' in result:
                console.print(Markdown(result['content']))
            else:
                console.print(result)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        sys.exit(1)


@cli.command()
@click.argument('question')
@click.option('--models', '-m', multiple=True, help='Models to consult (e.g., gemini-pro,o3)')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def consensus(ctx, question, models, output_json):
    """Get consensus from multiple AI models

    Examples:
        zen consensus "Should we use microservices or monolith?"
        zen consensus "PostgreSQL vs MongoDB?" --models gemini-pro,o3,gpt-4
    """
    zen = _get_zen_instance(ctx)

    arguments = {
        "prompt": question,
    }

    # Parse models if provided
    if models:
        model_list = []
        for model_str in models:
            # Handle comma-separated models in single argument
            model_list.extend(m.strip() for m in model_str.split(',') if m.strip())

        arguments["models"] = [{"model": m} for m in model_list]

    try:
        from tools.consensus import ConsensusTool
        result = asyncio.run(ConsensusTool().execute(arguments))

        if output_json:
            console.print_json(data=result)
        else:
            if isinstance(result, dict) and 'content' in result:
                console.print(Markdown(result['content']))
            else:
                console.print(result)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        sys.exit(1)


@cli.command('listmodels')
@click.option('--format', 'output_format', type=click.Choice(['table', 'json', 'simple']),
              default='table', help='Output format')
@click.pass_context
def listmodels_cmd(ctx, output_format):
    """List all available AI models

    Examples:
        zen listmodels              # Table format (default)
        zen listmodels --format json  # JSON format for scripts
        zen listmodels --format simple # Simple text list
    """
    zen = _get_zen_instance(ctx)

    try:
        if output_format == 'json':
            # For JSON, return structured data from registry
            providers_data = []
            for provider_type in zen.registry.get_available_providers():
                provider = zen.registry.get_provider(provider_type)
                if provider:
                    models = zen.registry.get_available_model_names(provider_type)
                    providers_data.append({
                        "provider": provider_type.value if hasattr(provider_type, 'value') else str(provider_type),
                        "models": sorted(models),
                        "count": len(models)
                    })
            console.print_json(data={"providers": providers_data})
        elif output_format == 'simple':
            # Simple text-only format - exhaustive list for easy selection
            console.print("\n[bold]Available AI Models[/bold]\n")

            total_models = 0
            for provider_type in zen.registry.get_available_providers():
                provider = zen.registry.get_provider(provider_type)
                if not provider:
                    continue

                models = zen.registry.get_available_model_names(provider_type)
                if models:
                    provider_name = provider_type.value if hasattr(provider_type, 'value') else str(provider_type)
                    console.print(f"[cyan]{provider_name}[/cyan]: {len(models)} models")
                    # Show ALL models for easy selection
                    for model in sorted(models):
                        console.print(f"  • {model}")
                    console.print()
                    total_models += len(models)

            console.print(f"[bold]Total: {total_models} models[/bold]\n")
        else:  # table format
            # Table format - use Rich table
            table = Table(title="Available AI Models", show_header=True, header_style="bold magenta")
            table.add_column("Provider", style="cyan", no_wrap=True)
            table.add_column("Status", style="green", no_wrap=True)
            table.add_column("Models", style="yellow")
            table.add_column("Count", justify="right", style="blue")

            total_models = 0
            for provider_type in zen.registry.get_available_providers():
                provider = zen.registry.get_provider(provider_type)
                provider_name = provider_type.value if hasattr(provider_type, 'value') else str(provider_type)

                if provider:
                    models = zen.registry.get_available_model_names(provider_type)
                    model_count = len(models)
                    total_models += model_count

                    if model_count > 0:
                        status = "✅ Configured"
                        sample_models = sorted(models)[:3]
                        model_display = ", ".join(sample_models)
                        if len(models) > 3:
                            model_display += f", +{len(models) - 3} more"
                    else:
                        status = "❌ No models"
                        model_display = "-"

                    table.add_row(provider_name, status, model_display, str(model_count))

            table.add_section()
            table.add_row("[bold]Total[/bold]", "", "", f"[bold]{total_models}[/bold]")

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        sys.exit(1)


@cli.command()
@click.pass_context
def version(ctx):
    """Show version information"""
    console.print(f"Zen CLI v{__version__}")
    console.print(f"Based on Zen MCP Server v9.0.0")


# ============================================================================
# CRITICAL TOOLS
# ============================================================================

@cli.command()
@click.argument('goal', required=False)
@click.option('--session', '-s', help='Session ID for multi-step workflows (auto-generated if not provided)')
@click.option('--continue', 'continue_findings', help='Continue existing session with your findings/work results')
@click.option('--context-files', '-f', multiple=True, help='Context files to include')
@click.option('--model', '-m', help='AI model to use (default: auto)')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def planner(ctx, goal, session, continue_findings, context_files, model, output_json):
    """Generate sequential task plan for complex goals

    Multi-step workflow with automatic session management for workflow continuity.
    Sessions allow pausing and resuming workflows across multiple CLI invocations.

    \b
    WORKFLOW MODES:
      • Start new workflow: zen planner "goal"
      • Continue workflow:  zen planner --session <id> --continue "findings"

    \b
    HOW IT WORKS:
      1. Tool analyzes your goal and provides investigation steps
      2. You (or Claude Code) perform the requested investigation
      3. Continue the workflow with your findings
      4. Repeat until workflow is complete
      5. Sessions auto-expire after 3 hours

    \b
    FOR CLAUDE CODE USERS:
      The tool returns 'continuation_command' with embedded instructions.
      Claude Code will automatically continue the workflow by calling the
      command with investigation results until workflow completes.

    \b
    EXAMPLES:

      # Start a new planning workflow (session ID auto-generated)
      zen planner "Implement OAuth2 authentication"

      # Start with context files
      zen planner "Refactor auth module" -f auth.py -f config.py

      # Continue an existing workflow session
      zen planner --session planner_1234_abcd --continue "Found UserAuth class using JWT tokens..."

      # Use specific model
      zen planner "Add dark mode" --model gemini-pro

      # Get JSON output for programmatic use
      zen planner "Build API" --json

    \b
    SESSION MANAGEMENT:
      • Sessions automatically generated with format: planner_<timestamp>_<random>
      • Session state persists in ~/.zen/conversations/
      • Sessions expire after 3 hours of inactivity
      • Completed workflows automatically clean up their sessions
    """
    from utils.workflow_session import (
        generate_session_id,
        load_session_state,
        save_session_state,
        enhance_with_continuation_instructions,
        build_continuation_arguments
    )

    try:
        from tools.planner import PlannerTool

        tool_name = "planner"

        # Determine if this is continuation or new workflow
        is_continuation = bool(continue_findings and session)

        if is_continuation:
            # CONTINUATION: Load existing session
            session_id = session
            session_state = load_session_state(session_id)

            if not session_state:
                console.print(f"[red]Error:[/red] Session '{session_id}' not found or expired")
                console.print("[yellow]Tip:[/yellow] Sessions expire after 3 hours. Start a new workflow:")
                console.print(f"  zen planner \"{goal or 'your goal'}\"")
                sys.exit(1)

            # Build continuation arguments from session state
            arguments = build_continuation_arguments(session_state, continue_findings, model)

            console.print(f"[dim]Continuing session {session_id} (step {arguments['step_number']})...[/dim]\n")

        else:
            # NEW WORKFLOW: Initialize with auto-generated or provided session ID
            if not goal:
                console.print("[red]Error:[/red] Goal is required for new workflows")
                console.print("[yellow]Usage:[/yellow] zen planner \"your goal here\"")
                sys.exit(1)

            session_id = session or generate_session_id(tool_name)

            arguments = {
                "step": goal,
                "step_number": 1,
                "total_steps": 5,  # Initial estimate
                "next_step_required": True,
                "findings": "",
                "files_checked": [],
                "relevant_files": list(context_files) if context_files else [],
                "relevant_context": [],
                "confidence": "exploring",
                "working_directory": os.getcwd(),
            }

            if model:
                arguments["model"] = model

            console.print(f"[dim]Starting new workflow session: {session_id}[/dim]\n")

        # Execute workflow step
        result = asyncio.run(PlannerTool().execute(arguments))
        result_data = json.loads(result[0].text)

        # Save session state for next step (if needed)
        if result_data.get("next_step_required", False):
            save_session_state(session_id, tool_name, result_data, arguments)

        # Enhance response with continuation instructions
        enhanced_result = enhance_with_continuation_instructions(
            result_data,
            session_id,
            tool_name
        )

        # Present results
        if output_json:
            console.print_json(data=enhanced_result)
        else:
            _present_workflow_step(enhanced_result, session_id, tool_name)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        logger.error(f"Planner workflow failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument('goal', required=False)
@click.option('--session', '-s', help='Session ID (auto-generated if not provided)')
@click.option('--continue', 'continue_findings', help='Continue with findings/work results')
@click.option('--files', '-f', multiple=True, help='Files to analyze')
@click.option('--analysis-type', type=click.Choice(['architecture', 'patterns', 'complexity', 'all']),
              default='all', help='Type of analysis to perform')
@click.option('--model', '-m', help='AI model to use (default: auto)')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def analyze(ctx, goal, session, continue_findings, files, analysis_type, model, output_json):
    """Comprehensive code analysis and architecture assessment

    Multi-step workflow with automatic session management for deep analysis.

    WORKFLOW MODES:
      • Start new workflow: zen analyze "Goal" --files *.py
      • Continue workflow:  zen analyze --session <id> --continue "findings"

    Examples:
        # Start new analysis
        zen analyze "Understand authentication flow" --files src/*.py
        zen analyze "Find performance issues" --analysis-type complexity

        # Continue analysis
        zen analyze --session analyze_xxx --continue "Found JWT implementation in auth.py"
    """
    tool_name = "analyze"

    try:
        from tools.analyze import AnalyzeTool
        from utils.workflow_session import (
            generate_session_id, load_session_state, save_session_state,
            enhance_with_continuation_instructions, build_continuation_arguments
        )

        # Determine continuation vs new workflow
        is_continuation = bool(continue_findings and session)

        if is_continuation:
            # Load session and build continuation arguments
            session_id = session
            session_state = load_session_state(session_id)

            if not session_state:
                console.print(f"[red]Error:[/red] Session '{session_id}' not found or expired (TTL: 3 hours)")
                sys.exit(1)

            console.print(f"[dim]Continuing session {session_id} (step {session_state['step_number'] + 1})...[/dim]\n")
            arguments = build_continuation_arguments(session_state, continue_findings, model)

        else:
            # Start new workflow
            if not goal:
                console.print("[red]Error:[/red] Goal required for new workflow. Use --session and --continue for continuation.")
                console.print("Example: zen analyze \"Understand architecture\" --files src/*.py")
                sys.exit(1)

            session_id = session or generate_session_id(tool_name)

            arguments = {
                "step": goal,
                "step_number": 1,
                "total_steps": 5,
                "next_step_required": True,
                "working_directory": os.getcwd(),
                "files": list(files) if files else [],
                "findings": f"Initializing {tool_name} workflow",
                "files_checked": [],
                "relevant_files": list(files) if files else [],
                "relevant_context": [],
                "confidence": "exploring",
                "analysis_type": analysis_type,
            }

            if model:
                arguments["model"] = model

            console.print(f"[dim]Starting new workflow session: {session_id}[/dim]\n")

        # Execute workflow step
        result = asyncio.run(AnalyzeTool().execute(arguments))
        result_data = json.loads(result[0].text)

        # Save session state for next step (if needed)
        if result_data.get("next_step_required", False):
            save_session_state(session_id, tool_name, result_data, arguments)

        # Enhance response with continuation instructions
        enhanced_result = enhance_with_continuation_instructions(
            result_data,
            session_id,
            tool_name
        )

        # Present results
        if output_json:
            console.print_json(data=enhanced_result)
        else:
            _present_workflow_step(enhanced_result, session_id, tool_name)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        logger.error(f"Analyze workflow failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument('question', required=False)
@click.option('--session', '-s', help='Session ID (auto-generated if not provided)')
@click.option('--continue', 'continue_findings', help='Continue with findings/work results')
@click.option('--thinking-budget', type=int, help='Thinking token budget (128-32768)')
@click.option('--model', '-m', help='AI model to use (must support extended thinking)')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def thinkdeep(ctx, question, session, continue_findings, thinking_budget, model, output_json):
    """Extended reasoning mode for complex problems

    Multi-step workflow with deep reasoning for complex architectural and design decisions.
    Requires models that support extended thinking (e.g., Gemini 2.5 Pro, o3)

    WORKFLOW MODES:
      • Start new workflow: zen thinkdeep "Complex question"
      • Continue workflow:  zen thinkdeep --session <id> --continue "findings"

    Examples:
        # Start deep reasoning
        zen thinkdeep "How should we architect this microservice?"
        zen thinkdeep "Debug this race condition" --thinking-budget 16384

        # Continue reasoning
        zen thinkdeep --session thinkdeep_xxx --continue "Investigated and found..."
    """
    tool_name = "thinkdeep"

    try:
        from tools.thinkdeep import ThinkDeepTool
        from utils.workflow_session import (
            generate_session_id, load_session_state, save_session_state,
            enhance_with_continuation_instructions, build_continuation_arguments
        )

        # Determine continuation vs new workflow
        is_continuation = bool(continue_findings and session)

        if is_continuation:
            # Load session and build continuation arguments
            session_id = session
            session_state = load_session_state(session_id)

            if not session_state:
                console.print(f"[red]Error:[/red] Session '{session_id}' not found or expired (TTL: 3 hours)")
                sys.exit(1)

            console.print(f"[dim]Continuing session {session_id} (step {session_state['step_number'] + 1})...[/dim]\n")
            arguments = build_continuation_arguments(session_state, continue_findings, model)

        else:
            # Start new workflow
            if not question:
                console.print("[red]Error:[/red] Question required for new workflow. Use --session and --continue for continuation.")
                console.print("Example: zen thinkdeep \"How should we architect this?\"")
                sys.exit(1)

            session_id = session or generate_session_id(tool_name)

            arguments = {
                "step": question,
                "step_number": 1,
                "total_steps": 5,
                "next_step_required": True,
                "working_directory": os.getcwd(),
                "findings": f"Initializing {tool_name} workflow",
                "files_checked": [],
                "relevant_files": [],
                "relevant_context": [],
                "confidence": "exploring",
                "reasoning_depth": "extended",
            }

            if thinking_budget:
                arguments["thinking_budget"] = thinking_budget
            if model:
                arguments["model"] = model

            console.print(f"[dim]Starting new workflow session: {session_id}[/dim]\n")

        # Execute workflow step
        result = asyncio.run(ThinkDeepTool().execute(arguments))
        result_data = json.loads(result[0].text)

        # Save session state for next step (if needed)
        if result_data.get("next_step_required", False):
            save_session_state(session_id, tool_name, result_data, arguments)

        # Enhance response with continuation instructions
        enhanced_result = enhance_with_continuation_instructions(
            result_data,
            session_id,
            tool_name
        )

        # Present results
        if output_json:
            console.print_json(data=enhanced_result)
        else:
            _present_workflow_step(enhanced_result, session_id, tool_name)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        logger.error(f"ThinkDeep workflow failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument('prompt_text', required=False)
@click.option('--cli-name', help='CLI client to invoke (gemini, codex, claude)')
@click.option('--role', help='Role preset for the CLI (default, planner, codereviewer)')
@click.option('--files', '-f', multiple=True, help='Files to pass to the CLI')
@click.option('--images', '-i', multiple=True, help='Images to pass to the CLI')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def clink(ctx, prompt_text, cli_name, role, files, images, output_json):
    """CLI-to-CLI bridge - spawn external AI CLIs as subagents

    NEW in v9.0.0: Recursive AI agents! Claude Code can spawn Codex,
    Codex can spawn Gemini CLI, etc. Offload tasks to fresh contexts.

    Examples:
        zen clink "Review auth module" --cli-name codex --role codereviewer
        zen clink "Implement dark mode" --cli-name claude
        zen clink "Search for best practices" --cli-name gemini
    """
    prompt = prompt_text or click.prompt("Enter your prompt for the CLI")

    # Build arguments matching ClinkRequest schema
    arguments = {
        "prompt": prompt,
        "cli_name": cli_name or "default",  # Required field
        "role": role or "assistant",         # Optional with default
        "files": list(files) if files else [],
        "images": list(images) if images else [],
    }
    # Note: working_directory removed - not in ClinkRequest schema

    try:
        from tools.clink import CLinkTool
        result = asyncio.run(CLinkTool().execute(arguments))

        if output_json:
            console.print_json(data=result)
        else:
            if isinstance(result, list) and len(result) > 0:
                content = json.loads(result[0].text)
                console.print(Markdown(content.get('content', str(content))))
            else:
                console.print(result)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        sys.exit(1)


@cli.command()
@click.argument('goal', required=False)
@click.option('--session', '-s', help='Session ID (auto-generated if not provided)')
@click.option('--continue', 'continue_findings', help='Continue with findings/work results')
@click.option('--files', '-f', multiple=True, help='Files to validate before commit')
@click.option('--model', '-m', help='AI model to use (default: auto)')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def precommit(ctx, goal, session, continue_findings, files, model, output_json):
    """Pre-commit validation and quality checks

    Multi-step workflow for comprehensive pre-commit validation.

    WORKFLOW MODES:
      • Start new workflow: zen precommit "Validate changes" --files *.py
      • Continue workflow:  zen precommit --session <id> --continue "findings"

    Examples:
        # Start validation
        zen precommit "Check code quality" --files src/*.py
        zen precommit "Validate commit" --files *.js --model gemini-pro

        # Continue validation
        zen precommit --session precommit_xxx --continue "Fixed linting issues"
    """
    tool_name = "precommit"

    try:
        from tools.precommit import PrecommitTool
        from utils.workflow_session import (
            generate_session_id, load_session_state, save_session_state,
            enhance_with_continuation_instructions, build_continuation_arguments
        )

        # Determine continuation vs new workflow
        is_continuation = bool(continue_findings and session)

        if is_continuation:
            # Load session and build continuation arguments
            session_id = session
            session_state = load_session_state(session_id)

            if not session_state:
                console.print(f"[red]Error:[/red] Session '{session_id}' not found or expired (TTL: 3 hours)")
                sys.exit(1)

            console.print(f"[dim]Continuing session {session_id} (step {session_state['step_number'] + 1})...[/dim]\n")
            arguments = build_continuation_arguments(session_state, continue_findings, model)

        else:
            # Start new workflow
            if not goal:
                console.print("[red]Error:[/red] Goal required for new workflow. Use --session and --continue for continuation.")
                console.print("Example: zen precommit \"Validate changes\" --files src/*.py")
                sys.exit(1)

            session_id = session or generate_session_id(tool_name)

            arguments = {
                "step": goal,
                "step_number": 1,
                "total_steps": 5,
                "next_step_required": True,
                "working_directory": os.getcwd(),
                "files": list(files) if files else [],
                "findings": f"Initializing {tool_name} workflow",
                "files_checked": [],
                "relevant_files": list(files) if files else [],
                "relevant_context": [],
                "confidence": "exploring",
                "validation_type": "all",
            }

            if model:
                arguments["model"] = model

            console.print(f"[dim]Starting new workflow session: {session_id}[/dim]\n")

        # Execute workflow step
        result = asyncio.run(PrecommitTool().execute(arguments))
        result_data = json.loads(result[0].text)

        # Save session state for next step (if needed)
        if result_data.get("next_step_required", False):
            save_session_state(session_id, tool_name, result_data, arguments)

        # Enhance response with continuation instructions
        enhanced_result = enhance_with_continuation_instructions(
            result_data,
            session_id,
            tool_name
        )

        # Present results
        if output_json:
            console.print_json(data=enhanced_result)
        else:
            _present_workflow_step(enhanced_result, session_id, tool_name)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        logger.error(f"Precommit workflow failed: {e}", exc_info=True)
        sys.exit(1)


# ============================================================================
# QUALITY TOOLS
# ============================================================================

@cli.command()
@click.argument('goal', required=False)
@click.option('--session', '-s', help='Session ID (auto-generated if not provided)')
@click.option('--continue', 'continue_findings', help='Continue with findings/work results')
@click.option('--files', '-f', multiple=True, help='Files to generate tests for')
@click.option('--framework', help='Test framework (pytest, jest, etc.)')
@click.option('--test-type', type=click.Choice(['unit', 'integration', 'e2e', 'all']),
              default='unit', help='Type of tests to generate')
@click.option('--model', '-m', help='AI model to use (default: auto)')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def testgen(ctx, goal, session, continue_findings, files, framework, test_type, model, output_json):
    """Generate comprehensive test suites

    Multi-step workflow for systematic test generation.

    WORKFLOW MODES:
      • Start new workflow: zen testgen "Generate tests" --files *.py
      • Continue workflow:  zen testgen --session <id> --continue "findings"

    Examples:
        # Start test generation
        zen testgen "Create unit tests" --files auth.py
        zen testgen "Generate API tests" --files api.js --framework jest

        # Continue test generation
        zen testgen --session testgen_xxx --continue "Analyzed auth.py structure"
    """
    tool_name = "testgen"

    try:
        from tools.testgen import TestGenTool
        from utils.workflow_session import (
            generate_session_id, load_session_state, save_session_state,
            enhance_with_continuation_instructions, build_continuation_arguments
        )

        # Determine continuation vs new workflow
        is_continuation = bool(continue_findings and session)

        if is_continuation:
            # Load session and build continuation arguments
            session_id = session
            session_state = load_session_state(session_id)

            if not session_state:
                console.print(f"[red]Error:[/red] Session '{session_id}' not found or expired (TTL: 3 hours)")
                sys.exit(1)

            console.print(f"[dim]Continuing session {session_id} (step {session_state['step_number'] + 1})...[/dim]\n")
            arguments = build_continuation_arguments(session_state, continue_findings, model)

        else:
            # Start new workflow
            if not goal:
                console.print("[red]Error:[/red] Goal required for new workflow. Use --session and --continue for continuation.")
                console.print("Example: zen testgen \"Generate unit tests\" --files auth.py")
                sys.exit(1)

            session_id = session or generate_session_id(tool_name)

            arguments = {
                "step": goal,
                "step_number": 1,
                "total_steps": 5,
                "next_step_required": True,
                "working_directory": os.getcwd(),
                "files": list(files) if files else [],
                "findings": f"Initializing {tool_name} workflow",
                "files_checked": [],
                "relevant_files": list(files) if files else [],
                "relevant_context": [],
                "confidence": "exploring",
                "framework": framework or "pytest",
                "test_type": test_type,
            }

            if model:
                arguments["model"] = model

            console.print(f"[dim]Starting new workflow session: {session_id}[/dim]\n")

        # Execute workflow step
        result = asyncio.run(TestGenTool().execute(arguments))
        result_data = json.loads(result[0].text)

        # Save session state for next step (if needed)
        if result_data.get("next_step_required", False):
            save_session_state(session_id, tool_name, result_data, arguments)

        # Enhance response with continuation instructions
        enhanced_result = enhance_with_continuation_instructions(
            result_data,
            session_id,
            tool_name
        )

        # Present results
        if output_json:
            console.print_json(data=enhanced_result)
        else:
            _present_workflow_step(enhanced_result, session_id, tool_name)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        logger.error(f"TestGen workflow failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument('goal', required=False)
@click.option('--session', '-s', help='Session ID (auto-generated if not provided)')
@click.option('--continue', 'continue_findings', help='Continue with findings/work results')
@click.option('--files', '-f', multiple=True, help='Files to audit')
@click.option('--focus', type=click.Choice(['auth', 'crypto', 'injection', 'all']),
              default='all', help='Security focus area')
@click.option('--model', '-m', help='AI model to use (default: auto)')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def secaudit(ctx, goal, session, continue_findings, files, focus, model, output_json):
    """Security audit and vulnerability assessment

    Multi-step workflow for comprehensive security analysis.

    WORKFLOW MODES:
      • Start new workflow: zen secaudit "Audit security" --files *.py
      • Continue workflow:  zen secaudit --session <id> --continue "findings"

    Examples:
        # Start security audit
        zen secaudit "Check for vulnerabilities" --files auth.py
        zen secaudit "Audit authentication" --files api/*.js --focus auth

        # Continue audit
        zen secaudit --session secaudit_xxx --continue "Found SQL injection risk"
    """
    tool_name = "secaudit"

    try:
        from tools.secaudit import SecauditTool
        from utils.workflow_session import (
            generate_session_id, load_session_state, save_session_state,
            enhance_with_continuation_instructions, build_continuation_arguments
        )

        # Determine continuation vs new workflow
        is_continuation = bool(continue_findings and session)

        if is_continuation:
            # Load session and build continuation arguments
            session_id = session
            session_state = load_session_state(session_id)

            if not session_state:
                console.print(f"[red]Error:[/red] Session '{session_id}' not found or expired (TTL: 3 hours)")
                sys.exit(1)

            console.print(f"[dim]Continuing session {session_id} (step {session_state['step_number'] + 1})...[/dim]\n")
            arguments = build_continuation_arguments(session_state, continue_findings, model)

        else:
            # Start new workflow
            if not goal:
                console.print("[red]Error:[/red] Goal required for new workflow. Use --session and --continue for continuation.")
                console.print("Example: zen secaudit \"Check for vulnerabilities\" --files auth.py")
                sys.exit(1)

            session_id = session or generate_session_id(tool_name)

            arguments = {
                "step": goal,
                "step_number": 1,
                "total_steps": 5,
                "next_step_required": True,
                "working_directory": os.getcwd(),
                "files": list(files) if files else [],
                "findings": f"Initializing {tool_name} workflow",
                "files_checked": [],
                "relevant_files": list(files) if files else [],
                "relevant_context": [],
                "confidence": "exploring",
                "focus": focus,
                "issues_found": [],
            }

            if model:
                arguments["model"] = model

            console.print(f"[dim]Starting new workflow session: {session_id}[/dim]\n")

        # Execute workflow step
        result = asyncio.run(SecauditTool().execute(arguments))
        result_data = json.loads(result[0].text)

        # Save session state for next step (if needed)
        if result_data.get("next_step_required", False):
            save_session_state(session_id, tool_name, result_data, arguments)

        # Enhance response with continuation instructions
        enhanced_result = enhance_with_continuation_instructions(
            result_data,
            session_id,
            tool_name
        )

        # Present results
        if output_json:
            console.print_json(data=enhanced_result)
        else:
            _present_workflow_step(enhanced_result, session_id, tool_name)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        logger.error(f"Secaudit workflow failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument('goal', required=False)
@click.option('--session', '-s', help='Session ID (auto-generated if not provided)')
@click.option('--continue', 'continue_findings', help='Continue with findings/work results')
@click.option('--files', '-f', multiple=True, help='Files to refactor')
@click.option('--refactor-type', type=click.Choice(['readability', 'performance', 'maintainability', 'codesmells', 'all']),
              default='codesmells', help='Type of refactoring to perform')
@click.option('--model', '-m', help='AI model to use (default: auto)')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def refactor(ctx, goal, session, continue_findings, files, refactor_type, model, output_json):
    """Code refactoring suggestions and improvements

    Multi-step workflow for systematic refactoring analysis.

    WORKFLOW MODES:
      • Start new workflow: zen refactor "Improve code" --files *.py
      • Continue workflow:  zen refactor --session <id> --continue "findings"

    Examples:
        # Start refactoring
        zen refactor "Improve readability" --files legacy.py
        zen refactor "Optimize performance" --files utils.js --refactor-type performance

        # Continue refactoring
        zen refactor --session refactor_xxx --continue "Identified code smells"
    """
    tool_name = "refactor"

    try:
        from tools.refactor import RefactorTool
        from utils.workflow_session import (
            generate_session_id, load_session_state, save_session_state,
            enhance_with_continuation_instructions, build_continuation_arguments
        )

        # Determine continuation vs new workflow
        is_continuation = bool(continue_findings and session)

        if is_continuation:
            # Load session and build continuation arguments
            session_id = session
            session_state = load_session_state(session_id)

            if not session_state:
                console.print(f"[red]Error:[/red] Session '{session_id}' not found or expired (TTL: 3 hours)")
                sys.exit(1)

            console.print(f"[dim]Continuing session {session_id} (step {session_state['step_number'] + 1})...[/dim]\n")
            arguments = build_continuation_arguments(session_state, continue_findings, model)

        else:
            # Start new workflow
            if not goal:
                console.print("[red]Error:[/red] Goal required for new workflow. Use --session and --continue for continuation.")
                console.print("Example: zen refactor \"Improve readability\" --files legacy.py")
                sys.exit(1)

            session_id = session or generate_session_id(tool_name)

            arguments = {
                "step": goal,
                "step_number": 1,
                "total_steps": 5,
                "next_step_required": True,
                "working_directory": os.getcwd(),
                "files": list(files) if files else [],
                "findings": f"Initializing {tool_name} workflow",
                "files_checked": [],
                "relevant_files": list(files) if files else [],
                "relevant_context": [],
                "confidence": "exploring",
                "refactor_type": refactor_type,
                "focus_areas": [],
                "issues_found": [],
            }

            if model:
                arguments["model"] = model

            console.print(f"[dim]Starting new workflow session: {session_id}[/dim]\n")

        # Execute workflow step
        result = asyncio.run(RefactorTool().execute(arguments))
        result_data = json.loads(result[0].text)

        # Save session state for next step (if needed)
        if result_data.get("next_step_required", False):
            save_session_state(session_id, tool_name, result_data, arguments)

        # Enhance response with continuation instructions
        enhanced_result = enhance_with_continuation_instructions(
            result_data,
            session_id,
            tool_name
        )

        # Present results
        if output_json:
            console.print_json(data=enhanced_result)
        else:
            _present_workflow_step(enhanced_result, session_id, tool_name)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        logger.error(f"Refactor workflow failed: {e}", exc_info=True)
        sys.exit(1)


# ============================================================================
# UTILITY TOOLS
# ============================================================================

@cli.command()
@click.argument('goal', required=False)
@click.option('--session', '-s', help='Session ID (auto-generated if not provided)')
@click.option('--continue', 'continue_findings', help='Continue with findings/work results')
@click.option('--files', '-f', multiple=True, help='Files to document')
@click.option('--style', type=click.Choice(['docstring', 'markdown', 'jsdoc', 'godoc']),
              default='docstring', help='Documentation style')
@click.option('--model', '-m', help='AI model to use (default: auto)')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def docgen(ctx, goal, session, continue_findings, files, style, model, output_json):
    """Generate comprehensive documentation

    Multi-step workflow for systematic documentation generation.

    WORKFLOW MODES:
      • Start new workflow: zen docgen "Document code" --files *.py
      • Continue workflow:  zen docgen --session <id> --continue "findings"

    Examples:
        # Start documentation
        zen docgen "Generate API docs" --files api.py
        zen docgen "Document utilities" --files utils.js --style jsdoc

        # Continue documentation
        zen docgen --session docgen_xxx --continue "Analyzed module structure"
    """
    tool_name = "docgen"

    try:
        from tools.docgen import DocgenTool
        from utils.workflow_session import (
            generate_session_id, load_session_state, save_session_state,
            enhance_with_continuation_instructions, build_continuation_arguments
        )

        # Determine continuation vs new workflow
        is_continuation = bool(continue_findings and session)

        if is_continuation:
            # Load session and build continuation arguments
            session_id = session
            session_state = load_session_state(session_id)

            if not session_state:
                console.print(f"[red]Error:[/red] Session '{session_id}' not found or expired (TTL: 3 hours)")
                sys.exit(1)

            console.print(f"[dim]Continuing session {session_id} (step {session_state['step_number'] + 1})...[/dim]\n")
            arguments = build_continuation_arguments(session_state, continue_findings, model)

        else:
            # Start new workflow
            if not goal:
                console.print("[red]Error:[/red] Goal required for new workflow. Use --session and --continue for continuation.")
                console.print("Example: zen docgen \"Generate API documentation\" --files api.py")
                sys.exit(1)

            session_id = session or generate_session_id(tool_name)

            arguments = {
                "step": goal,
                "step_number": 1,
                "total_steps": 5,
                "next_step_required": True,
                "working_directory": os.getcwd(),
                "findings": "Discovery phase - identifying files needing documentation",
                "relevant_files": list(files) if files else [],
                "relevant_context": [],
                "num_files_documented": 0,
                "total_files_to_document": 0,
                "document_complexity": True,
                "document_flow": True,
                "update_existing": True,
                "comments_on_complex_logic": True,
                "style": style,
            }

            if model:
                arguments["model"] = model

            console.print(f"[dim]Starting new workflow session: {session_id}[/dim]\n")

        # Execute workflow step
        result = asyncio.run(DocgenTool().execute(arguments))
        result_data = json.loads(result[0].text)

        # Save session state for next step (if needed)
        if result_data.get("next_step_required", False):
            save_session_state(session_id, tool_name, result_data, arguments)

        # Enhance response with continuation instructions
        enhanced_result = enhance_with_continuation_instructions(
            result_data,
            session_id,
            tool_name
        )

        # Present results
        if output_json:
            console.print_json(data=enhanced_result)
        else:
            _present_workflow_step(enhanced_result, session_id, tool_name)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        logger.error(f"Docgen workflow failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument('target', required=False)
@click.option('--session', '-s', help='Session ID (auto-generated if not provided)')
@click.option('--continue', 'continue_findings', help='Continue with findings/work results')
@click.option('--depth', type=int, default=3, help='Trace depth (default: 3)')
@click.option('--trace-mode', type=click.Choice(['forward', 'backward', 'both', 'ask']),
              default='ask', help='Trace direction')
@click.option('--model', '-m', help='AI model to use (default: auto)')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def tracer(ctx, target, session, continue_findings, depth, trace_mode, model, output_json):
    """Trace code execution flow and dependencies

    Multi-step workflow for systematic code flow tracing.

    WORKFLOW MODES:
      • Start new workflow: zen tracer "handleRequest"
      • Continue workflow:  zen tracer --session <id> --continue "findings"

    Examples:
        # Start tracing
        zen tracer "handleRequest function"
        zen tracer "auth.py authentication flow" --depth 5

        # Continue tracing
        zen tracer --session tracer_xxx --continue "Traced to middleware.py"
    """
    tool_name = "tracer"

    try:
        from tools.tracer import TracerTool
        from utils.workflow_session import (
            generate_session_id, load_session_state, save_session_state,
            enhance_with_continuation_instructions, build_continuation_arguments
        )

        # Determine continuation vs new workflow
        is_continuation = bool(continue_findings and session)

        if is_continuation:
            # Load session and build continuation arguments
            session_id = session
            session_state = load_session_state(session_id)

            if not session_state:
                console.print(f"[red]Error:[/red] Session '{session_id}' not found or expired (TTL: 3 hours)")
                sys.exit(1)

            console.print(f"[dim]Continuing session {session_id} (step {session_state['step_number'] + 1})...[/dim]\n")
            arguments = build_continuation_arguments(session_state, continue_findings, model)

        else:
            # Start new workflow
            if not target:
                console.print("[red]Error:[/red] Target required for new workflow. Use --session and --continue for continuation.")
                console.print("Example: zen tracer \"handleRequest function\"")
                sys.exit(1)

            session_id = session or generate_session_id(tool_name)

            arguments = {
                "step": f"Beginning trace analysis of: {target}",
                "step_number": 1,
                "total_steps": 5,
                "next_step_required": True,
                "working_directory": os.getcwd(),
                "findings": f"Beginning trace analysis of: {target}",
                "files_checked": [],
                "relevant_files": [],
                "relevant_context": [],
                "trace_mode": trace_mode,
                "target_description": target,
                "depth": depth,
            }

            if model:
                arguments["model"] = model

            console.print(f"[dim]Starting new workflow session: {session_id}[/dim]\n")

        # Execute workflow step
        result = asyncio.run(TracerTool().execute(arguments))
        result_data = json.loads(result[0].text)

        # Save session state for next step (if needed)
        if result_data.get("next_step_required", False):
            save_session_state(session_id, tool_name, result_data, arguments)

        # Enhance response with continuation instructions
        enhanced_result = enhance_with_continuation_instructions(
            result_data,
            session_id,
            tool_name
        )

        # Present results
        if output_json:
            console.print_json(data=enhanced_result)
        else:
            _present_workflow_step(enhanced_result, session_id, tool_name)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        logger.error(f"Tracer workflow failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument('statement', nargs=-1, required=True)
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def challenge(ctx, statement, output_json):
    """Challenge assumptions and explore alternatives

    Wraps statements in critical thinking instructions to encourage
    thoughtful analysis rather than reflexive agreement.

    Examples:
        zen challenge "We need a microservice architecture"
        zen challenge "Redis is the best choice for session storage"
        zen challenge "We should use GraphQL instead of REST"
    """
    # Join all statement words into single prompt
    full_statement = ' '.join(statement)

    # Build arguments matching ChallengeRequest schema
    arguments = {
        "prompt": full_statement,  # Only field in ChallengeRequest
    }
    # Note: context, model, working_directory removed - not in schema

    try:
        from tools.challenge import ChallengeTool
        result = asyncio.run(ChallengeTool().execute(arguments))

        if output_json:
            console.print_json(data=result)
        else:
            if isinstance(result, list) and len(result) > 0:
                content = json.loads(result[0].text)
                console.print(Markdown(content.get('content', str(content))))
            else:
                console.print(result)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        sys.exit(1)


@cli.command()
@click.argument('query', nargs=-1, required=True)
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.pass_context
def apilookup(ctx, query, output_json):
    """Look up API documentation and usage examples

    Provides instructions for web search to find latest API/SDK documentation,
    version info, breaking changes, and migration guides.

    Examples:
        zen apilookup express
        zen apilookup "flask 3.0 latest features"
        zen apilookup "react hooks API 2025"
    """
    # Join all query words into single prompt
    full_query = ' '.join(query)

    # Build arguments matching LookupRequest schema
    arguments = {
        "prompt": full_query,  # Only field in LookupRequest
    }
    # Note: version, model, working_directory removed - not in schema

    try:
        from tools.apilookup import LookupTool
        result = asyncio.run(LookupTool().execute(arguments))

        if output_json:
            console.print_json(data=result)
        else:
            if isinstance(result, list) and len(result) > 0:
                content = json.loads(result[0].text)
                console.print(Markdown(content.get('content', str(content))))
            else:
                console.print(result)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    cli(obj={})
