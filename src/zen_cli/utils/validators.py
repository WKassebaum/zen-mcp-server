"""Input validation utilities for the Zen CLI.

This module provides validation functions for common inputs like
file paths, model names, and other parameters to ensure proper
error handling and user feedback.
"""

import os
from pathlib import Path
from typing import List, Optional
import typer


def validate_file_paths(paths: List[str], must_exist: bool = True) -> List[str]:
    """Validate file paths exist and are readable.
    
    Args:
        paths: List of file paths to validate
        must_exist: Whether files must exist (True for reading, False for writing)
        
    Returns:
        List of validated absolute paths
        
    Raises:
        typer.BadParameter: If any path is invalid
    """
    validated = []
    
    for path in paths:
        path_obj = Path(path)
        
        # Convert to absolute path
        abs_path = path_obj.absolute()
        
        if must_exist:
            # Check if file exists
            if not abs_path.exists():
                raise typer.BadParameter(
                    f"File not found: {path}\n"
                    f"Please check the path and try again."
                )
            
            # Check if it's actually a file
            if not abs_path.is_file():
                if abs_path.is_dir():
                    raise typer.BadParameter(
                        f"Path is a directory, not a file: {path}\n"
                        f"Please specify individual files."
                    )
                else:
                    raise typer.BadParameter(
                        f"Path is not a regular file: {path}"
                    )
            
            # Check if file is readable
            if not os.access(abs_path, os.R_OK):
                raise typer.BadParameter(
                    f"File is not readable: {path}\n"
                    f"Check file permissions."
                )
        else:
            # For writing, just check parent directory exists and is writable
            parent = abs_path.parent
            if not parent.exists():
                raise typer.BadParameter(
                    f"Parent directory does not exist: {parent}\n"
                    f"Please create the directory first."
                )
            
            if not os.access(parent, os.W_OK):
                raise typer.BadParameter(
                    f"Parent directory is not writable: {parent}\n"
                    f"Check directory permissions."
                )
        
        validated.append(str(abs_path))
    
    return validated


def validate_model_name(model: str, registry=None) -> str:
    """Validate model name is available or is 'auto'.
    
    Args:
        model: Model name to validate
        registry: Optional ModelProviderRegistry instance
        
    Returns:
        Validated model name
        
    Raises:
        typer.BadParameter: If model is not available
    """
    # Auto is always valid
    if model.lower() == "auto":
        return model
    
    # If registry provided, check if model is available
    if registry:
        try:
            # Check if model is available
            provider = registry.get_provider_for_model(model)
            if not provider:
                # Get list of available models
                available = []
                for provider_type in registry._providers:
                    provider = registry.get_provider(provider_type)
                    if provider:
                        available.extend(provider.list_models())
                
                if available:
                    raise typer.BadParameter(
                        f"Model '{model}' is not available.\n"
                        f"Available models: {', '.join(sorted(available))}\n"
                        f"Or use 'auto' for automatic selection."
                    )
                else:
                    raise typer.BadParameter(
                        f"No models available. Please configure API keys:\n"
                        f"  export GEMINI_API_KEY=your_key\n"
                        f"  export OPENAI_API_KEY=your_key"
                    )
        except Exception as e:
            # If there's an error checking, just warn
            if not model.startswith(("gpt", "gemini", "claude", "o1", "o3")):
                typer.echo(
                    f"Warning: Could not validate model '{model}': {e}",
                    err=True
                )
    
    return model


def validate_review_type(review_type: str) -> str:
    """Validate code review type.
    
    Args:
        review_type: Review type to validate
        
    Returns:
        Validated review type
        
    Raises:
        typer.BadParameter: If review type is invalid
    """
    valid_types = ["all", "security", "performance", "quality"]
    
    if review_type.lower() not in valid_types:
        raise typer.BadParameter(
            f"Invalid review type: '{review_type}'\n"
            f"Valid types: {', '.join(valid_types)}"
        )
    
    return review_type.lower()


def validate_analysis_type(analysis_type: str) -> str:
    """Validate analysis type.
    
    Args:
        analysis_type: Analysis type to validate
        
    Returns:
        Validated analysis type
        
    Raises:
        typer.BadParameter: If analysis type is invalid
    """
    valid_types = ["general", "architecture", "complexity"]
    
    if analysis_type.lower() not in valid_types:
        raise typer.BadParameter(
            f"Invalid analysis type: '{analysis_type}'\n"
            f"Valid types: {', '.join(valid_types)}"
        )
    
    return analysis_type.lower()


def validate_trace_mode(trace_mode: str) -> str:
    """Validate trace mode.
    
    Args:
        trace_mode: Trace mode to validate
        
    Returns:
        Validated trace mode
        
    Raises:
        typer.BadParameter: If trace mode is invalid
    """
    valid_modes = ["ask", "precision", "dependencies"]
    
    if trace_mode.lower() not in valid_modes:
        raise typer.BadParameter(
            f"Invalid trace mode: '{trace_mode}'\n"
            f"Valid modes: {', '.join(valid_modes)}"
        )
    
    return trace_mode.lower()


def validate_threat_level(threat_level: str) -> str:
    """Validate security threat level.
    
    Args:
        threat_level: Threat level to validate
        
    Returns:
        Validated threat level
        
    Raises:
        typer.BadParameter: If threat level is invalid
    """
    valid_levels = ["low", "medium", "high", "critical"]
    
    if threat_level.lower() not in valid_levels:
        raise typer.BadParameter(
            f"Invalid threat level: '{threat_level}'\n"
            f"Valid levels: {', '.join(valid_levels)}"
        )
    
    return threat_level.lower()


def validate_security_scope(scope: str) -> str:
    """Validate security audit scope.
    
    Args:
        scope: Security scope to validate
        
    Returns:
        Validated scope
        
    Raises:
        typer.BadParameter: If scope is invalid
    """
    valid_scopes = ["web", "mobile", "api", "enterprise", "cloud"]
    
    if scope.lower() not in valid_scopes:
        raise typer.BadParameter(
            f"Invalid security scope: '{scope}'\n"
            f"Valid scopes: {', '.join(valid_scopes)}"
        )
    
    return scope.lower()


def validate_confidence_level(confidence: str) -> str:
    """Validate confidence level.
    
    Args:
        confidence: Confidence level to validate
        
    Returns:
        Validated confidence level
        
    Raises:
        typer.BadParameter: If confidence level is invalid
    """
    valid_levels = ["exploring", "low", "medium", "high", "very_high", "almost_certain", "certain"]
    
    if confidence.lower() not in valid_levels:
        raise typer.BadParameter(
            f"Invalid confidence level: '{confidence}'\n"
            f"Valid levels: {', '.join(valid_levels)}"
        )
    
    return confidence.lower()


def validate_git_ref(ref: Optional[str], repo_path: str = ".") -> Optional[str]:
    """Validate git reference (branch, tag, or commit).
    
    Args:
        ref: Git reference to validate
        repo_path: Path to git repository
        
    Returns:
        Validated git reference or None
        
    Raises:
        typer.BadParameter: If reference is invalid
    """
    if not ref:
        return None
    
    import subprocess
    
    try:
        # Check if ref exists in repo
        result = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            # Try to provide helpful error message
            if "unknown revision" in result.stderr.lower():
                # List available branches and tags
                branches_result = subprocess.run(
                    ["git", "branch", "-a"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                tags_result = subprocess.run(
                    ["git", "tag"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                branches = [b.strip().replace("* ", "") for b in branches_result.stdout.splitlines()]
                tags = tags_result.stdout.splitlines()
                
                raise typer.BadParameter(
                    f"Git reference '{ref}' not found.\n"
                    f"Available branches: {', '.join(branches[:5])}{'...' if len(branches) > 5 else ''}\n"
                    f"Available tags: {', '.join(tags[:5])}{'...' if len(tags) > 5 else ''}"
                )
            else:
                raise typer.BadParameter(
                    f"Invalid git reference '{ref}': {result.stderr}"
                )
        
        return ref
        
    except subprocess.TimeoutExpired:
        raise typer.BadParameter(
            f"Timeout validating git reference '{ref}'"
        )
    except FileNotFoundError:
        raise typer.BadParameter(
            "Git is not installed or not in PATH"
        )
    except Exception as e:
        # Non-fatal, just warn
        typer.echo(
            f"Warning: Could not validate git reference '{ref}': {e}",
            err=True
        )
        return ref