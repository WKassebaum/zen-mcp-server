"""
Standardized error handling for Zen CLI

This module provides consistent error types and handling utilities to ensure
uniform error handling across the entire codebase.

Key Features:
- Custom exception hierarchy for different error types
- Automatic error logging with appropriate levels
- User-friendly error messages
- Error context preservation for debugging
- Retry logic for transient failures
"""

import logging
import sys
import traceback
from functools import wraps
from typing import Any, Callable, Optional, Type, Union, Dict

logger = logging.getLogger(__name__)


# Base Exception Classes

class ZenError(Exception):
    """Base exception for all Zen CLI errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        
    def __str__(self):
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


class ConfigurationError(ZenError):
    """Raised when there's a configuration issue."""
    pass


class APIError(ZenError):
    """Raised when an API call fails."""
    
    def __init__(self, message: str, provider: Optional[str] = None, 
                 status_code: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.provider = provider
        self.status_code = status_code


class StorageError(ZenError):
    """Raised when storage operations fail."""
    
    def __init__(self, message: str, storage_type: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.storage_type = storage_type


class ValidationError(ZenError):
    """Raised when input validation fails."""
    
    def __init__(self, message: str, field: Optional[str] = None,
                 value: Optional[Any] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.field = field
        self.value = value


class ToolExecutionError(ZenError):
    """Raised when a tool execution fails."""
    
    def __init__(self, message: str, tool_name: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.tool_name = tool_name


class AuthenticationError(ZenError):
    """Raised when authentication fails."""
    pass


class RateLimitError(APIError):
    """Raised when API rate limit is exceeded."""
    
    def __init__(self, message: str, provider: Optional[str] = None,
                 retry_after: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, provider, status_code=429, details=details)
        self.retry_after = retry_after


class NetworkError(ZenError):
    """Raised when network operations fail."""
    pass


# Error Handling Utilities

def handle_error(error: Exception, 
                 context: str = "",
                 user_message: Optional[str] = None,
                 log_level: int = logging.ERROR,
                 reraise: bool = True) -> None:
    """
    Standardized error handler that logs errors consistently.
    
    Args:
        error: The exception to handle
        context: Additional context about where the error occurred
        user_message: User-friendly message to display
        log_level: Logging level to use
        reraise: Whether to re-raise the exception
    """
    # Build error details
    error_details = {
        "type": type(error).__name__,
        "message": str(error),
        "context": context
    }
    
    # Add exception-specific details
    if isinstance(error, ZenError) and error.details:
        error_details["details"] = error.details
    
    # Log the error
    logger.log(
        log_level,
        f"Error in {context}: {error}",
        extra={"error_details": error_details},
        exc_info=(log_level >= logging.ERROR)
    )
    
    # Display user message if provided
    if user_message:
        # Use click.echo if available, otherwise print
        try:
            import click
            click.echo(f"❌ {user_message}", err=True)
        except ImportError:
            print(f"Error: {user_message}", file=sys.stderr)
    
    # Re-raise if requested
    if reraise:
        raise


def safe_execute(func: Callable,
                 *args,
                 context: str = "",
                 default: Any = None,
                 error_types: tuple = (Exception,),
                 log_errors: bool = True,
                 **kwargs) -> Any:
    """
    Safely execute a function with error handling.
    
    Args:
        func: Function to execute
        *args: Positional arguments for the function
        context: Context for error logging
        default: Default value to return on error
        error_types: Tuple of exception types to catch
        log_errors: Whether to log errors
        **kwargs: Keyword arguments for the function
        
    Returns:
        Function result or default value on error
    """
    try:
        return func(*args, **kwargs)
    except error_types as e:
        if log_errors:
            handle_error(
                e,
                context=context or f"executing {func.__name__}",
                reraise=False
            )
        return default


def error_handler(context: str = "",
                  user_message: Optional[str] = None,
                  default: Any = None,
                  error_types: tuple = (Exception,),
                  log_level: int = logging.ERROR):
    """
    Decorator for standardized error handling.
    
    Args:
        context: Context for error logging
        user_message: User-friendly error message
        default: Default return value on error
        error_types: Exception types to catch
        log_level: Logging level to use
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except error_types as e:
                handle_error(
                    e,
                    context=context or f"{func.__module__}.{func.__name__}",
                    user_message=user_message,
                    log_level=log_level,
                    reraise=(default is None)
                )
                return default
        return wrapper
    return decorator


def validate_required(value: Any,
                     name: str,
                     value_type: Optional[Type] = None,
                     min_length: Optional[int] = None,
                     max_length: Optional[int] = None,
                     choices: Optional[list] = None) -> Any:
    """
    Validate a required value with optional type and constraint checking.
    
    Args:
        value: Value to validate
        name: Name of the value (for error messages)
        value_type: Expected type
        min_length: Minimum length (for strings/lists)
        max_length: Maximum length (for strings/lists)
        choices: Valid choices for the value
        
    Returns:
        The validated value
        
    Raises:
        ValidationError: If validation fails
    """
    # Check if value is provided
    if value is None:
        raise ValidationError(f"{name} is required", field=name)
    
    # Type checking
    if value_type and not isinstance(value, value_type):
        raise ValidationError(
            f"{name} must be of type {value_type.__name__}",
            field=name,
            value=value
        )
    
    # Length checking
    if hasattr(value, '__len__'):
        if min_length is not None and len(value) < min_length:
            raise ValidationError(
                f"{name} must have at least {min_length} items/characters",
                field=name,
                value=value
            )
        if max_length is not None and len(value) > max_length:
            raise ValidationError(
                f"{name} must have at most {max_length} items/characters",
                field=name,
                value=value
            )
    
    # Choices validation
    if choices is not None and value not in choices:
        raise ValidationError(
            f"{name} must be one of: {', '.join(map(str, choices))}",
            field=name,
            value=value
        )
    
    return value


def format_error_message(error: Exception, include_traceback: bool = False) -> str:
    """
    Format an error message for display to the user.
    
    Args:
        error: The exception to format
        include_traceback: Whether to include the full traceback
        
    Returns:
        Formatted error message
    """
    message_parts = []
    
    # Add error type and message
    error_type = type(error).__name__
    message_parts.append(f"{error_type}: {str(error)}")
    
    # Add exception-specific details
    if isinstance(error, APIError):
        if error.provider:
            message_parts.append(f"Provider: {error.provider}")
        if error.status_code:
            message_parts.append(f"Status: {error.status_code}")
    
    elif isinstance(error, ValidationError):
        if error.field:
            message_parts.append(f"Field: {error.field}")
        if error.value is not None:
            message_parts.append(f"Value: {error.value}")
    
    elif isinstance(error, StorageError):
        if error.storage_type:
            message_parts.append(f"Storage: {error.storage_type}")
    
    elif isinstance(error, ToolExecutionError):
        if error.tool_name:
            message_parts.append(f"Tool: {error.tool_name}")
    
    elif isinstance(error, RateLimitError):
        if error.retry_after:
            message_parts.append(f"Retry after: {error.retry_after}s")
    
    # Add details if available
    if isinstance(error, ZenError) and error.details:
        details_str = ", ".join(f"{k}={v}" for k, v in error.details.items())
        message_parts.append(f"Details: {details_str}")
    
    # Add traceback if requested
    if include_traceback:
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        message_parts.append("\nTraceback:\n" + "".join(tb))
    
    return "\n".join(message_parts)


class ErrorContext:
    """
    Context manager for handling errors in a specific context.
    
    Example:
        with ErrorContext("processing API request", user_message="Failed to process request"):
            # Code that might raise exceptions
            api_call()
    """
    
    def __init__(self,
                 context: str,
                 user_message: Optional[str] = None,
                 log_level: int = logging.ERROR,
                 reraise: bool = True):
        self.context = context
        self.user_message = user_message
        self.log_level = log_level
        self.reraise = reraise
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            handle_error(
                exc_val,
                context=self.context,
                user_message=self.user_message,
                log_level=self.log_level,
                reraise=self.reraise
            )
        return not self.reraise


# Retry decorator with error handling
def retry_on_error(max_attempts: int = 3,
                   delay: float = 1.0,
                   backoff: float = 2.0,
                   error_types: tuple = (NetworkError, APIError),
                   context: str = ""):
    """
    Decorator to retry a function on specific errors.
    
    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between retries (seconds)
        backoff: Backoff multiplier for delay
        error_types: Exception types to retry on
        context: Context for logging
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_error = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except error_types as e:
                    last_error = e
                    
                    if attempt < max_attempts:
                        logger.warning(
                            f"Attempt {attempt}/{max_attempts} failed in "
                            f"{context or func.__name__}: {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        
                        # Handle rate limiting
                        if isinstance(e, RateLimitError) and e.retry_after:
                            import time
                            time.sleep(e.retry_after)
                        else:
                            import time
                            time.sleep(current_delay)
                            current_delay *= backoff
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed in "
                            f"{context or func.__name__}"
                        )
            
            # Re-raise the last error if all attempts failed
            if last_error:
                raise last_error
                
        return wrapper
    return decorator