"""Retry logic with exponential backoff for API calls.

This module provides retry functionality with exponential backoff for handling
transient failures in API calls, network issues, and rate limiting.
"""

import logging
import random
import time
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type, Union

logger = logging.getLogger(__name__)


class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""
    
    def __init__(self, message: str, last_error: Optional[Exception] = None):
        super().__init__(message)
        self.last_error = last_error


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retry_on: Optional[Tuple[Type[Exception], ...]] = None,
        retry_condition: Optional[Callable[[Exception], bool]] = None
    ):
        """Initialize retry configuration.
        
        Args:
            max_attempts: Maximum number of retry attempts (including initial)
            initial_delay: Initial delay in seconds between retries
            max_delay: Maximum delay in seconds between retries
            exponential_base: Base for exponential backoff calculation
            jitter: Whether to add random jitter to delays
            retry_on: Tuple of exception types to retry on
            retry_condition: Optional function to determine if error is retryable
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retry_on = retry_on or (Exception,)
        self.retry_condition = retry_condition
    
    def should_retry(self, error: Exception) -> bool:
        """Determine if an error should trigger a retry.
        
        Args:
            error: The exception that occurred
            
        Returns:
            True if the error should trigger a retry
        """
        # Check if error type is in retry_on tuple
        if not isinstance(error, self.retry_on):
            return False
        
        # Apply custom retry condition if provided
        if self.retry_condition:
            return self.retry_condition(error)
        
        return True
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number.
        
        Args:
            attempt: The attempt number (0-based)
            
        Returns:
            Delay in seconds
        """
        # Calculate exponential delay
        delay = min(
            self.initial_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        
        # Add jitter if enabled
        if self.jitter:
            delay = delay * (0.5 + random.random())
        
        return delay


# Default configurations for different scenarios
DEFAULT_CONFIG = RetryConfig()

API_CONFIG = RetryConfig(
    max_attempts=3,
    initial_delay=1.0,
    max_delay=30.0,
    exponential_base=2.0,
    jitter=True
)

NETWORK_CONFIG = RetryConfig(
    max_attempts=5,
    initial_delay=0.5,
    max_delay=60.0,
    exponential_base=2.0,
    jitter=True
)

RATE_LIMIT_CONFIG = RetryConfig(
    max_attempts=5,
    initial_delay=2.0,
    max_delay=120.0,
    exponential_base=2.0,
    jitter=True
)


def with_retry(
    config: Optional[RetryConfig] = None,
    *,
    max_attempts: Optional[int] = None,
    initial_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    exponential_base: Optional[float] = None,
    jitter: Optional[bool] = None,
    retry_on: Optional[Tuple[Type[Exception], ...]] = None,
    retry_condition: Optional[Callable[[Exception], bool]] = None
):
    """Decorator to add retry logic to a function.
    
    Can be used with or without arguments:
    - @with_retry
    - @with_retry()
    - @with_retry(config=API_CONFIG)
    - @with_retry(max_attempts=5, initial_delay=2.0)
    
    Args:
        config: Pre-configured RetryConfig object
        max_attempts: Override max attempts
        initial_delay: Override initial delay
        max_delay: Override max delay
        exponential_base: Override exponential base
        jitter: Override jitter setting
        retry_on: Override exception types to retry
        retry_condition: Override retry condition function
    
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Use provided config or create new one with overrides
            retry_config = config or DEFAULT_CONFIG
            
            # Apply overrides if provided
            if max_attempts is not None:
                retry_config = RetryConfig(
                    max_attempts=max_attempts,
                    initial_delay=retry_config.initial_delay if initial_delay is None else initial_delay,
                    max_delay=retry_config.max_delay if max_delay is None else max_delay,
                    exponential_base=retry_config.exponential_base if exponential_base is None else exponential_base,
                    jitter=retry_config.jitter if jitter is None else jitter,
                    retry_on=retry_config.retry_on if retry_on is None else retry_on,
                    retry_condition=retry_config.retry_condition if retry_condition is None else retry_condition
                )
            elif any(param is not None for param in [initial_delay, max_delay, exponential_base, jitter, retry_on, retry_condition]):
                retry_config = RetryConfig(
                    max_attempts=retry_config.max_attempts,
                    initial_delay=initial_delay or retry_config.initial_delay,
                    max_delay=max_delay or retry_config.max_delay,
                    exponential_base=exponential_base or retry_config.exponential_base,
                    jitter=jitter if jitter is not None else retry_config.jitter,
                    retry_on=retry_on or retry_config.retry_on,
                    retry_condition=retry_condition or retry_config.retry_condition
                )
            
            last_error = None
            for attempt in range(retry_config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    
                    # Check if we should retry
                    if not retry_config.should_retry(e):
                        logger.debug(
                            f"[RETRY] {func.__name__}: Error not retryable: {type(e).__name__}: {e}"
                        )
                        raise
                    
                    # Check if this was the last attempt
                    if attempt >= retry_config.max_attempts - 1:
                        logger.warning(
                            f"[RETRY] {func.__name__}: All {retry_config.max_attempts} attempts exhausted. "
                            f"Last error: {type(e).__name__}: {e}"
                        )
                        raise RetryError(
                            f"Failed after {retry_config.max_attempts} attempts",
                            last_error=e
                        )
                    
                    # Calculate delay and wait
                    delay = retry_config.get_delay(attempt)
                    logger.info(
                        f"[RETRY] {func.__name__}: Attempt {attempt + 1}/{retry_config.max_attempts} failed "
                        f"with {type(e).__name__}. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            raise RetryError(
                f"Failed after {retry_config.max_attempts} attempts",
                last_error=last_error
            )
        
        return wrapper
    
    # Handle decorator being used without arguments
    if callable(config):
        func = config
        config = None
        return decorator(func)
    
    return decorator


def retry_on_rate_limit(error: Exception) -> bool:
    """Check if error is a rate limit error that should be retried.
    
    Args:
        error: The exception to check
        
    Returns:
        True if error indicates rate limiting
    """
    error_str = str(error).lower()
    rate_limit_indicators = [
        'rate limit',
        'rate_limit',
        'too many requests',
        '429',
        'quota exceeded',
        'resource_exhausted',
        'throttled'
    ]
    
    return any(indicator in error_str for indicator in rate_limit_indicators)


def retry_on_network_error(error: Exception) -> bool:
    """Check if error is a network error that should be retried.
    
    Args:
        error: The exception to check
        
    Returns:
        True if error indicates network issues
    """
    import socket
    from urllib.error import URLError
    
    # Check for common network error types
    network_errors = (
        ConnectionError,
        TimeoutError,
        socket.timeout,
        socket.error,
        URLError,
    )
    
    if isinstance(error, network_errors):
        return True
    
    # Check error message for network-related strings
    error_str = str(error).lower()
    network_indicators = [
        'connection',
        'timeout',
        'network',
        'socket',
        'unreachable',
        'refused',
        'reset',
        'broken pipe'
    ]
    
    return any(indicator in error_str for indicator in network_indicators)


# Specialized retry configurations
RATE_LIMIT_RETRY = RetryConfig(
    max_attempts=5,
    initial_delay=2.0,
    max_delay=120.0,
    exponential_base=2.0,
    jitter=True,
    retry_condition=retry_on_rate_limit
)

NETWORK_RETRY = RetryConfig(
    max_attempts=3,
    initial_delay=1.0,
    max_delay=30.0,
    exponential_base=2.0,
    jitter=True,
    retry_condition=retry_on_network_error
)


def combine_retry_conditions(*conditions: Callable[[Exception], bool]) -> Callable[[Exception], bool]:
    """Combine multiple retry conditions with OR logic.
    
    Args:
        *conditions: Variable number of retry condition functions
        
    Returns:
        A function that returns True if any condition returns True
    """
    def combined_condition(error: Exception) -> bool:
        return any(condition(error) for condition in conditions)
    
    return combined_condition


# Combined configuration for API calls (handles both rate limits and network issues)
API_RETRY = RetryConfig(
    max_attempts=5,
    initial_delay=1.0,
    max_delay=60.0,
    exponential_base=2.0,
    jitter=True,
    retry_condition=combine_retry_conditions(retry_on_rate_limit, retry_on_network_error)
)