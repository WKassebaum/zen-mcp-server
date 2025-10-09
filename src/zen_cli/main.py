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
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

# Load environment variables from ~/.zen-cli/.env
zen_config_dir = Path.home() / ".zen-cli"
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
    console.print(f"Based on Zen MCP Server v8.0.0")


if __name__ == '__main__':
    cli(obj={})
