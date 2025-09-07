"""Synchronous wrapper for async tools to work with CLI."""

import json
import logging
import time
from typing import Any, Dict

from zen_cli.types import TextContent

logger = logging.getLogger(__name__)


def execute_chat_sync(tool, arguments: dict) -> list[TextContent]:
    """Execute chat tool synchronously."""
    from zen_cli.providers.registry import ModelProviderRegistry
    
    # Extract required arguments
    prompt = arguments.get('prompt', '')
    model_name = arguments.get('model', 'auto')
    files = arguments.get('files', [])
    continuation_id = arguments.get('continuation_id')
    
    # Handle auto model resolution
    if model_name.lower() == 'auto':
        registry = ModelProviderRegistry()
        model_name = registry.get_preferred_fallback_model('default')
    
    # Get the provider
    registry = ModelProviderRegistry()
    provider = registry.get_provider_for_model(model_name)
    if not provider:
        error_msg = f"Model '{model_name}' is not available"
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": error_msg
            })
        )]
    
    # Read files if provided
    context_content = ""
    if files:
        from zen_cli.utils.file_utils import read_files
        file_contents = read_files(files)
        if file_contents:
            context_content = "\n\n## Context Files:\n" + file_contents
    
    # Build the full prompt
    full_prompt = prompt
    if context_content:
        full_prompt = f"{prompt}\n{context_content}"
    
    # Get system prompt
    from zen_cli.systemprompts.chat_prompt import CHAT_PROMPT
    system_prompt = CHAT_PROMPT
    
    try:
        # Generate content synchronously
        response = provider.generate_content(
            prompt=full_prompt,
            model_name=model_name,
            system_prompt=system_prompt,
            temperature=0.7
        )
        
        # Format response
        result = {
            "status": "success",
            "content": response.content if response else "No response generated"
        }
        
        # Handle conversation memory if needed
        # TODO: Re-enable when storage is fully working
        pass
        
        return [TextContent(
            type="text",
            text=json.dumps(result)
        )]
        
    except Exception as e:
        logger.error(f"Error in chat sync execution: {e}")
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": str(e)
            })
        )]


def execute_listmodels_sync(tool, arguments: dict) -> list[TextContent]:
    """Execute listmodels tool synchronously."""
    from zen_cli.providers.registry import ModelProviderRegistry
    import os
    
    try:
        registry = ModelProviderRegistry()
        output_lines = ["# Available AI Models\n"]
        
        # List models from each provider
        provider_info = {
            'google': {
                'name': 'Google Gemini',
                'env_key': 'GEMINI_API_KEY',
            },
            'openai': {
                'name': 'OpenAI',
                'env_key': 'OPENAI_API_KEY',
            }
        }
        
        configured_count = 0
        total_models = 0
        
        for provider_type, info in provider_info.items():
            api_key = os.getenv(info['env_key'])
            is_configured = api_key and api_key != f"your_{provider_type}_api_key_here"
            
            output_lines.append(f"\n## {info['name']} {'✅' if is_configured else '❌'}")
            
            if is_configured:
                configured_count += 1
                output_lines.append(f"**Status**: Configured and available\n")
                
                # Get provider
                from zen_cli.providers.base import ProviderType
                provider = ModelProviderRegistry.get_provider(getattr(ProviderType, provider_type.upper()))
                
                if provider:
                    output_lines.append("**Models**:")
                    models = provider.list_models()
                    total_models += len(models)
                    for model in models:
                        output_lines.append(f"- {model}")
            else:
                output_lines.append(f"**Status**: Not configured (set {info['env_key']})")
            
            output_lines.append("")
        
        output_lines.append(f"\n## Summary")
        output_lines.append(f"**Configured Providers**: {configured_count}")
        output_lines.append(f"**Total Available Models**: {total_models}")
        
        result = "\n".join(output_lines)
        
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "success",
                "content": result
            })
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": str(e)
            })
        )]


def execute_version_sync(tool, arguments: dict) -> list[TextContent]:
    """Execute version tool synchronously."""
    from zen_cli.config import __version__
    import os
    from pathlib import Path
    
    try:
        output_lines = ["# Zen CLI Version\n"]
        
        # Basic version info
        output_lines.append(f"**Version**: {__version__}")
        output_lines.append(f"**Installation Path**: {Path.cwd()}")
        
        # Provider status
        output_lines.append("\n## Configuration")
        output_lines.append("\n**Providers**:")
        
        providers = {
            'Google Gemini': 'GEMINI_API_KEY',
            'OpenAI': 'OPENAI_API_KEY',
        }
        
        for name, env_key in providers.items():
            api_key = os.getenv(env_key)
            is_configured = api_key and api_key != f"your_{env_key.lower()}_here"
            status = "✅ Configured" if is_configured else "❌ Not configured"
            output_lines.append(f"- {name}: {status}")
        
        result = "\n".join(output_lines)
        
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "success",
                "content": result
            })
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": str(e)
            })
        )]


def execute_debug_sync(tool, arguments: dict) -> list[TextContent]:
    """Execute debug tool synchronously."""
    from zen_cli.providers.registry import ModelProviderRegistry
    from zen_cli.systemprompts.debug_prompt import DEBUG_ISSUE_PROMPT
    
    # Extract arguments
    request = arguments.get('request', '')
    model_name = arguments.get('model', 'auto')
    files = arguments.get('files', [])
    confidence = arguments.get('confidence', 'exploring')
    
    # Handle auto model resolution
    if model_name.lower() == 'auto':
        registry = ModelProviderRegistry()
        model_name = registry.get_preferred_fallback_model('reasoning')
    
    # Get the provider
    registry = ModelProviderRegistry()
    provider = registry.get_provider_for_model(model_name)
    if not provider:
        error_msg = f"Model '{model_name}' is not available"
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": error_msg
            })
        )]
    
    # Read files if provided
    context_content = ""
    if files:
        from zen_cli.utils.file_utils import read_files
        file_contents = read_files(files)
        if file_contents:
            context_content = f"\n\n## Context Files:\n{file_contents}"
    
    # Build the prompt
    full_prompt = f"Problem description: {request}\nConfidence level: {confidence}{context_content}"
    
    try:
        # Generate content synchronously
        response = provider.generate_content(
            prompt=full_prompt,
            model_name=model_name,
            system_prompt=DEBUG_ISSUE_PROMPT,
            temperature=0.7
        )
        
        result = {
            "status": "success",
            "content": response.content if response else "No response generated"
        }
        
        return [TextContent(
            type="text",
            text=json.dumps(result)
        )]
        
    except Exception as e:
        logger.error(f"Error in debug sync execution: {e}")
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": str(e)
            })
        )]

def execute_simple_tool_sync(tool, arguments: dict) -> list[TextContent]:
    """Execute a SimpleTool synchronously."""
    from zen_cli.providers.registry import ModelProviderRegistry
    
    # Extract arguments
    prompt = arguments.get('prompt', '')
    model_name = arguments.get('model', 'auto')
    
    # Create registry once
    registry = ModelProviderRegistry()
    
    # Handle auto model resolution
    if model_name.lower() == 'auto':
        model_name = registry.get_preferred_fallback_model(tool.get_model_category())
    
    # Get the provider
    provider = registry.get_provider_for_model(model_name)
    if not provider:
        error_msg = f"Model '{model_name}' is not available"
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": error_msg
            })
        )]
    
    try:
        # Generate content synchronously
        response = provider.generate_content(
            prompt=prompt,
            model_name=model_name,
            system_prompt=tool.get_system_prompt(),
            temperature=tool.get_default_temperature()
        )
        
        result = {
            "status": "success",
            "content": response.content if response else "No response generated"
        }
        
        return [TextContent(
            type="text",
            text=json.dumps(result)
        )]
        
    except Exception as e:
        logger.error(f"Error in simple tool sync execution: {e}")
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": str(e)
            })
        )]

def execute_workflow_tool_sync(tool, arguments: dict) -> list[TextContent]:
    """Execute a WorkflowTool synchronously."""
    from zen_cli.providers.registry import ModelProviderRegistry
    
    # For workflow tools, we need to handle the step-by-step nature
    # TODO: Implement proper multi-step workflow execution
    # For now, just execute the first step
    request = arguments.get('request', {})
    model_name = arguments.get('model', 'auto')
    
    # Create registry once
    registry = ModelProviderRegistry()
    
    # Handle auto model resolution
    if model_name.lower() == 'auto':
        model_name = registry.get_preferred_fallback_model(tool.get_model_category())
    
    # Get the provider
    provider = registry.get_provider_for_model(model_name)
    if not provider:
        error_msg = f"Model '{model_name}' is not available"
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": error_msg
            })
        )]
    
    try:
        # Build prompt for workflow step
        prompt = json.dumps(request)
        
        # Generate content synchronously
        response = provider.generate_content(
            prompt=prompt,
            model_name=model_name,
            system_prompt=tool.get_system_prompt(),
            temperature=tool.get_default_temperature()
        )
        
        result = {
            "status": "success",
            "content": response.content if response else "No response generated"
        }
        
        return [TextContent(
            type="text",
            text=json.dumps(result)
        )]
        
    except Exception as e:
        logger.error(f"Error in workflow tool sync execution: {e}")
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": str(e)
            })
        )]

def execute_tool_sync(tool_name: str, tool, arguments: dict) -> list[TextContent]:
    """Execute any tool synchronously based on tool name."""
    
    # Map specific tools to their sync executors
    sync_executors = {
        'chat': execute_chat_sync,
        'debug': execute_debug_sync,
        'listmodels': execute_listmodels_sync,
        'version': execute_version_sync,
        # Add more specific implementations as needed
    }
    
    executor = sync_executors.get(tool_name)
    if executor:
        return executor(tool, arguments)
    
    # Check tool type for generic handlers
    from .simple.base import SimpleTool
    from .workflow.base import WorkflowTool
    
    if isinstance(tool, SimpleTool):
        return execute_simple_tool_sync(tool, arguments)
    elif isinstance(tool, WorkflowTool):
        return execute_workflow_tool_sync(tool, arguments)
    else:
        # Fallback for tools without sync implementation
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": f"No synchronous implementation for tool: {tool_name}"
            })
        )]