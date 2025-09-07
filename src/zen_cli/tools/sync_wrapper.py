"""Synchronous wrapper for async tools to work with CLI."""

import json
import logging
import time
from typing import Any, Dict

from zen_cli.types import TextContent
from zen_cli.utils.retry import RetryError

logger = logging.getLogger(__name__)


def execute_chat_sync(tool, arguments: dict, registry=None) -> list[TextContent]:
    """Execute chat tool synchronously."""
    from zen_cli.providers.registry import ModelProviderRegistry
    
    # Use provided registry or create new one
    if registry is None:
        registry = ModelProviderRegistry()
    
    # Extract required arguments
    prompt = arguments.get('prompt', '')
    model_name = arguments.get('model', 'auto')
    files = arguments.get('files', [])
    continuation_id = arguments.get('continuation_id')
    
    # Handle auto model resolution
    if model_name.lower() == 'auto':
        model_name = registry.get_preferred_fallback_model('default')
    
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
        
    except RetryError as e:
        logger.error(f"All retry attempts exhausted in chat: {e}")
        error_msg = f"Failed after multiple attempts: {str(e.last_error) if e.last_error else str(e)}"
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": error_msg,
                "retry_exhausted": True
            })
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


def execute_listmodels_sync(tool, arguments: dict, registry=None) -> list[TextContent]:
    """Execute listmodels tool synchronously."""
    from zen_cli.providers.registry import ModelProviderRegistry
    import os
    
    # Registry not needed for listmodels but accept for consistency
    
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


def execute_version_sync(tool, arguments: dict, registry=None) -> list[TextContent]:
    """Execute version tool synchronously."""
    from zen_cli.config import __version__
    import os
    from pathlib import Path
    
    # Registry not needed for version but accept for consistency
    
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


def execute_debug_sync(tool, arguments: dict, registry=None) -> list[TextContent]:
    """Execute debug tool synchronously."""
    from zen_cli.providers.registry import ModelProviderRegistry
    from zen_cli.systemprompts.debug_prompt import DEBUG_ISSUE_PROMPT
    from zen_cli.tools.workflow.base import WorkflowTool
    
    # Check if this is actually a WorkflowTool
    if isinstance(tool, WorkflowTool):
        # Debug is a workflow tool, use the workflow executor
        return execute_workflow_tool_sync(tool, arguments, registry)
    
    # Use provided registry or create new one
    if registry is None:
        registry = ModelProviderRegistry()
    
    # Fall back to simple implementation for non-workflow debug
    # Extract arguments
    request = arguments.get('request', '')
    model_name = arguments.get('model', 'auto')
    files = arguments.get('files', [])
    confidence = arguments.get('confidence', 'exploring')
    
    # Handle auto model resolution
    if model_name.lower() == 'auto':
        model_name = registry.get_preferred_fallback_model('reasoning')
    
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
        
    except RetryError as e:
        logger.error(f"All retry attempts exhausted in debug: {e}")
        error_msg = f"Failed after multiple attempts: {str(e.last_error) if e.last_error else str(e)}"
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": error_msg,
                "retry_exhausted": True
            })
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

def execute_simple_tool_sync(tool, arguments: dict, registry=None) -> list[TextContent]:
    """Execute a SimpleTool synchronously."""
    from zen_cli.providers.registry import ModelProviderRegistry
    
    # Use provided registry or create new one
    if registry is None:
        registry = ModelProviderRegistry()
    
    # Extract arguments
    prompt = arguments.get('prompt', '')
    model_name = arguments.get('model', 'auto')
    
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
        
    except RetryError as e:
        logger.error(f"All retry attempts exhausted in {tool.get_name() if hasattr(tool, 'get_name') else 'tool'}: {e}")
        error_msg = f"Failed after multiple attempts: {str(e.last_error) if e.last_error else str(e)}"
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": error_msg,
                "retry_exhausted": True
            })
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

def execute_workflow_tool_sync(tool, arguments: dict, registry=None) -> list[TextContent]:
    """Execute a WorkflowTool synchronously with multi-step support."""
    from zen_cli.providers.registry import ModelProviderRegistry
    from zen_cli.utils.workflow_state import get_workflow_manager, WorkflowState
    from zen_cli.utils.file_utils import read_files
    
    # Use provided registry or create new one
    if registry is None:
        registry = ModelProviderRegistry()
    
    # Get workflow manager
    manager = get_workflow_manager()
    
    # Extract key arguments
    tool_name = tool.get_name() if hasattr(tool, 'get_name') else 'unknown'
    continuation_id = arguments.get('continuation_id', 'default')
    request = arguments.get('request', {})
    model_name = arguments.get('model', 'auto')
    max_steps = arguments.get('max_steps', 5)  # Safety limit
    files = arguments.get('files', [])  # Extract files early
    
    # Handle initial call from CLI where request is just a string
    if isinstance(request, str):
        # Convert simple string request to workflow format for first step
        request = {
            'problem': request,  # Store original problem description
            'step': f"Starting investigation: {request}",
            'step_number': 1,
            'total_steps': 3,  # Initial estimate
            'next_step_required': True,
            'findings': "Beginning investigation",
            'files_checked': [],
            'relevant_files': files if files else [],
            'issues_found': [],
            'confidence': arguments.get('confidence', 'exploring')
        }
    
    # Handle files if provided
    file_content_str = ""
    if files:
        logger.debug(f"Reading {len(files)} files for workflow tool {tool_name}")
        file_contents = read_files(files)
        if file_contents:
            file_content_str = f"\n\n=== FILE CONTENTS ===\n{file_contents}\n=== END FILE CONTENTS ==="
    
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
    
    # Get or create workflow state
    state = manager.get_state(continuation_id, tool_name)
    if state is None:
        # First execution - create new state
        state = WorkflowState(
            tool_name=tool_name,
            continuation_id=continuation_id,
            current_step=1,
            total_steps=request.get('total_steps', 3),
            next_step_required=True
        )
    
    # Collect all step results
    all_results = []
    steps_executed = 0
    
    try:
        while state.next_step_required and steps_executed < max_steps:
            # Update request with current state
            step_request = {**request}
            step_request.update({
                'step_number': state.current_step,
                'total_steps': state.total_steps,
                'findings': state.findings,
                'files_checked': state.files_checked,
                'relevant_files': state.relevant_files if not files else files,  # Use provided files
                'issues_found': state.issues_found,
                'confidence': state.confidence,
                'continuation_id': continuation_id
            })
            
            # Build prompt for workflow step
            prompt = json.dumps(step_request)
            
            # Add file contents if we have them
            if file_content_str and state.current_step == 1:
                # Only add file contents on first step to avoid duplication
                prompt = f"{prompt}{file_content_str}"
            
            logger.debug(f"Executing {tool_name} step {state.current_step}/{state.total_steps}")
            
            # Generate content synchronously
            response = provider.generate_content(
                prompt=prompt,
                model_name=model_name,
                system_prompt=tool.get_system_prompt(),
                temperature=tool.get_default_temperature()
            )
            
            # Parse response to check for workflow continuation
            if response and response.content:
                try:
                    # Try to parse as JSON to extract workflow metadata
                    response_data = json.loads(response.content)
                    
                    # Update state from response
                    state = manager.update_from_response(state, response_data)
                    
                    # Save the updated state
                    manager.save_state(state)
                    
                    # Add this step's result
                    all_results.append(response_data)
                    
                    # Check if we should continue
                    if not state.next_step_required:
                        logger.debug(f"{tool_name} workflow complete at step {state.current_step}")
                        break
                    
                    # Advance to next step
                    state.advance_step()
                    
                except json.JSONDecodeError:
                    # Response isn't JSON, treat as final result
                    all_results.append({"content": response.content})
                    break
            
            steps_executed += 1
        
        # Clean up completed workflow
        if not state.next_step_required:
            manager.delete_state(continuation_id, tool_name)
        
        # Format final result
        if len(all_results) == 1:
            # Single step result
            result = {
                "status": "success",
                "content": json.dumps(all_results[0]) if isinstance(all_results[0], dict) else all_results[0]
            }
        else:
            # Multi-step result - combine findings
            combined_result = {
                "status": "success",
                "total_steps_executed": steps_executed,
                "workflow_complete": not state.next_step_required,
                "final_confidence": state.confidence,
                "all_findings": state.findings,
                "issues_found": state.issues_found,
                "steps": all_results
            }
            result = {
                "status": "success",
                "content": json.dumps(combined_result)
            }
        
        return [TextContent(
            type="text",
            text=json.dumps(result)
        )]
        
    except RetryError as e:
        logger.error(f"All retry attempts exhausted in workflow {tool_name}: {e}")
        # Clean up on error
        manager.delete_state(continuation_id, tool_name)
        error_msg = f"Failed after multiple attempts: {str(e.last_error) if e.last_error else str(e)}"
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": error_msg,
                "retry_exhausted": True
            })
        )]
    except Exception as e:
        logger.error(f"Error in workflow tool sync execution: {e}")
        # Clean up on error
        manager.delete_state(continuation_id, tool_name)
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": str(e)
            })
        )]

def execute_tool_sync(tool_name: str, tool, arguments: dict, registry=None) -> list[TextContent]:
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
        return executor(tool, arguments, registry)
    
    # Check tool type for generic handlers
    from .simple.base import SimpleTool
    from .workflow.base import WorkflowTool
    
    if isinstance(tool, SimpleTool):
        return execute_simple_tool_sync(tool, arguments, registry)
    elif isinstance(tool, WorkflowTool):
        return execute_workflow_tool_sync(tool, arguments, registry)
    else:
        # Fallback for tools without sync implementation
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "error",
                "error": f"No synchronous implementation for tool: {tool_name}"
            })
        )]