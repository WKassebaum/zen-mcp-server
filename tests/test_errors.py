"""
Unit tests for standardized error handling

This module tests the error handling utilities and custom exception types
to ensure consistent error handling across the codebase.
"""

import logging
import time
import unittest
from unittest.mock import patch, MagicMock, call

from src.zen_cli.utils.errors import (
    ZenError, ConfigurationError, APIError, StorageError, ValidationError,
    ToolExecutionError, AuthenticationError, RateLimitError, NetworkError,
    handle_error, safe_execute, error_handler, validate_required,
    format_error_message, ErrorContext, retry_on_error
)


class TestCustomExceptions(unittest.TestCase):
    """Test cases for custom exception classes."""
    
    def test_zen_error_basic(self):
        """Test basic ZenError functionality."""
        error = ZenError("Test error message")
        self.assertEqual(str(error), "Test error message")
        self.assertEqual(error.message, "Test error message")
        self.assertEqual(error.details, {})
    
    def test_zen_error_with_details(self):
        """Test ZenError with details."""
        details = {"code": 123, "context": "testing"}
        error = ZenError("Test error", details=details)
        self.assertEqual(error.details, details)
        self.assertIn("details", str(error))
        self.assertIn("123", str(error))
    
    def test_configuration_error(self):
        """Test ConfigurationError."""
        error = ConfigurationError("Invalid configuration")
        self.assertIsInstance(error, ZenError)
        self.assertEqual(error.message, "Invalid configuration")
    
    def test_api_error(self):
        """Test APIError with provider and status code."""
        error = APIError(
            "API call failed",
            provider="openai",
            status_code=500,
            details={"endpoint": "/v1/chat"}
        )
        self.assertEqual(error.provider, "openai")
        self.assertEqual(error.status_code, 500)
        self.assertEqual(error.details["endpoint"], "/v1/chat")
    
    def test_storage_error(self):
        """Test StorageError with storage type."""
        error = StorageError("Storage failed", storage_type="redis")
        self.assertEqual(error.storage_type, "redis")
    
    def test_validation_error(self):
        """Test ValidationError with field and value."""
        error = ValidationError(
            "Invalid input",
            field="email",
            value="not-an-email"
        )
        self.assertEqual(error.field, "email")
        self.assertEqual(error.value, "not-an-email")
    
    def test_tool_execution_error(self):
        """Test ToolExecutionError with tool name."""
        error = ToolExecutionError("Execution failed", tool_name="debug")
        self.assertEqual(error.tool_name, "debug")
    
    def test_rate_limit_error(self):
        """Test RateLimitError with retry_after."""
        error = RateLimitError(
            "Rate limit exceeded",
            provider="gemini",
            retry_after=60
        )
        self.assertEqual(error.retry_after, 60)
        self.assertEqual(error.status_code, 429)
        self.assertEqual(error.provider, "gemini")


class TestErrorHandling(unittest.TestCase):
    """Test cases for error handling utilities."""
    
    @patch('src.zen_cli.utils.errors.logger')
    def test_handle_error_logging(self, mock_logger):
        """Test handle_error logs correctly."""
        error = ValueError("Test error")
        
        with self.assertRaises(ValueError):
            handle_error(
                error,
                context="test_context",
                user_message="User friendly message",
                log_level=logging.ERROR,
                reraise=True
            )
        
        # Check logging was called
        mock_logger.log.assert_called_once()
        call_args = mock_logger.log.call_args
        self.assertEqual(call_args[0][0], logging.ERROR)
        self.assertIn("test_context", call_args[0][1])
        self.assertIn("Test error", call_args[0][1])
    
    @patch('src.zen_cli.utils.errors.logger')
    @patch('click.echo')
    def test_handle_error_user_message(self, mock_echo, mock_logger):
        """Test handle_error displays user message."""
        error = ValueError("Internal error")
        
        handle_error(
            error,
            context="internal",
            user_message="Something went wrong",
            reraise=False
        )
        
        # Check user message was displayed
        mock_echo.assert_called_once_with("❌ Something went wrong", err=True)
    
    def test_safe_execute_success(self):
        """Test safe_execute with successful function."""
        def test_func(x, y):
            return x + y
        
        result = safe_execute(test_func, 2, 3)
        self.assertEqual(result, 5)
    
    def test_safe_execute_with_error(self):
        """Test safe_execute with function that raises error."""
        def failing_func():
            raise ValueError("Test error")
        
        result = safe_execute(
            failing_func,
            default="default_value",
            error_types=(ValueError,)
        )
        self.assertEqual(result, "default_value")
    
    def test_safe_execute_unhandled_error(self):
        """Test safe_execute with unhandled error type."""
        def failing_func():
            raise KeyError("Not handled")
        
        result = safe_execute(
            failing_func,
            default="default",
            error_types=(ValueError,)  # Won't catch KeyError
        )
        self.assertEqual(result, "default")  # Falls back to Exception
    
    def test_error_handler_decorator_success(self):
        """Test error_handler decorator with successful function."""
        @error_handler(context="test", default=None)
        def test_func(x):
            return x * 2
        
        result = test_func(5)
        self.assertEqual(result, 10)
    
    def test_error_handler_decorator_with_error(self):
        """Test error_handler decorator with error."""
        @error_handler(
            context="test",
            user_message="Function failed",
            default="fallback"
        )
        def failing_func():
            raise ValueError("Error in function")
        
        result = failing_func()
        self.assertEqual(result, "fallback")


class TestValidation(unittest.TestCase):
    """Test cases for validation utilities."""
    
    def test_validate_required_none(self):
        """Test validate_required with None value."""
        with self.assertRaises(ValidationError) as cm:
            validate_required(None, "test_field")
        
        error = cm.exception
        self.assertEqual(error.field, "test_field")
        self.assertIn("required", error.message)
    
    def test_validate_required_type_check(self):
        """Test validate_required with type checking."""
        # Valid type
        result = validate_required("test", "field", value_type=str)
        self.assertEqual(result, "test")
        
        # Invalid type
        with self.assertRaises(ValidationError) as cm:
            validate_required(123, "field", value_type=str)
        
        error = cm.exception
        self.assertIn("must be of type str", error.message)
    
    def test_validate_required_length_check(self):
        """Test validate_required with length constraints."""
        # Valid length
        result = validate_required("test", "field", min_length=2, max_length=10)
        self.assertEqual(result, "test")
        
        # Too short
        with self.assertRaises(ValidationError) as cm:
            validate_required("a", "field", min_length=2)
        
        self.assertIn("at least 2", cm.exception.message)
        
        # Too long
        with self.assertRaises(ValidationError) as cm:
            validate_required("a" * 20, "field", max_length=10)
        
        self.assertIn("at most 10", cm.exception.message)
    
    def test_validate_required_choices(self):
        """Test validate_required with choice constraints."""
        # Valid choice
        result = validate_required("red", "color", choices=["red", "green", "blue"])
        self.assertEqual(result, "red")
        
        # Invalid choice
        with self.assertRaises(ValidationError) as cm:
            validate_required("yellow", "color", choices=["red", "green", "blue"])
        
        self.assertIn("must be one of", cm.exception.message)
        self.assertIn("red", cm.exception.message)


class TestErrorFormatting(unittest.TestCase):
    """Test cases for error formatting."""
    
    def test_format_basic_error(self):
        """Test formatting basic exception."""
        error = ValueError("Test error")
        formatted = format_error_message(error)
        
        self.assertIn("ValueError", formatted)
        self.assertIn("Test error", formatted)
    
    def test_format_api_error(self):
        """Test formatting APIError with details."""
        error = APIError(
            "API failed",
            provider="openai",
            status_code=500
        )
        formatted = format_error_message(error)
        
        self.assertIn("APIError", formatted)
        self.assertIn("API failed", formatted)
        self.assertIn("Provider: openai", formatted)
        self.assertIn("Status: 500", formatted)
    
    def test_format_validation_error(self):
        """Test formatting ValidationError."""
        error = ValidationError(
            "Invalid value",
            field="username",
            value="abc"
        )
        formatted = format_error_message(error)
        
        self.assertIn("Field: username", formatted)
        self.assertIn("Value: abc", formatted)
    
    def test_format_with_details(self):
        """Test formatting error with details."""
        error = ZenError("Error", details={"key1": "value1", "key2": 123})
        formatted = format_error_message(error)
        
        self.assertIn("Details:", formatted)
        self.assertIn("key1=value1", formatted)
        self.assertIn("key2=123", formatted)
    
    def test_format_with_traceback(self):
        """Test formatting with traceback."""
        try:
            raise ValueError("Test error")
        except ValueError as e:
            formatted = format_error_message(e, include_traceback=True)
            
            self.assertIn("Traceback:", formatted)
            self.assertIn("raise ValueError", formatted)


class TestErrorContext(unittest.TestCase):
    """Test cases for ErrorContext context manager."""
    
    @patch('src.zen_cli.utils.errors.handle_error')
    def test_error_context_no_error(self, mock_handle):
        """Test ErrorContext when no error occurs."""
        with ErrorContext("test context"):
            result = 1 + 1
        
        self.assertEqual(result, 2)
        mock_handle.assert_not_called()
    
    @patch('src.zen_cli.utils.errors.handle_error')
    def test_error_context_with_error(self, mock_handle):
        """Test ErrorContext when error occurs."""
        with self.assertRaises(ValueError):
            with ErrorContext("test context", user_message="Failed"):
                raise ValueError("Test error")
        
        mock_handle.assert_called_once()
        call_args = mock_handle.call_args
        self.assertIsInstance(call_args[0][0], ValueError)
        self.assertEqual(call_args[1]["context"], "test context")
        self.assertEqual(call_args[1]["user_message"], "Failed")
    
    @patch('src.zen_cli.utils.errors.handle_error')
    def test_error_context_no_reraise(self, mock_handle):
        """Test ErrorContext with reraise=False."""
        with ErrorContext("test", reraise=False):
            raise ValueError("Should be suppressed")
        
        # Should not raise
        mock_handle.assert_called_once()


class TestRetryDecorator(unittest.TestCase):
    """Test cases for retry_on_error decorator."""
    
    def test_retry_success_first_attempt(self):
        """Test retry decorator with success on first attempt."""
        call_count = 0
        
        @retry_on_error(max_attempts=3)
        def test_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = test_func()
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 1)
    
    def test_retry_success_after_failures(self):
        """Test retry decorator with eventual success."""
        call_count = 0
        
        @retry_on_error(
            max_attempts=3,
            delay=0.01,
            error_types=(ValueError,)
        )
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"
        
        result = test_func()
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 3)
    
    def test_retry_all_attempts_fail(self):
        """Test retry decorator when all attempts fail."""
        call_count = 0
        
        @retry_on_error(
            max_attempts=2,
            delay=0.01,
            error_types=(ValueError,)
        )
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Persistent error")
        
        with self.assertRaises(ValueError) as cm:
            test_func()
        
        self.assertEqual(str(cm.exception), "Persistent error")
        self.assertEqual(call_count, 2)
    
    @patch('time.sleep')
    def test_retry_rate_limit_handling(self, mock_sleep):
        """Test retry decorator with RateLimitError."""
        call_count = 0
        
        @retry_on_error(
            max_attempts=2,
            delay=1.0,
            error_types=(RateLimitError,)
        )
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError("Rate limited", retry_after=5)
            return "success"
        
        result = test_func()
        self.assertEqual(result, "success")
        
        # Should sleep for retry_after value
        mock_sleep.assert_called_with(5)
    
    @patch('time.sleep')
    def test_retry_exponential_backoff(self, mock_sleep):
        """Test retry decorator with exponential backoff."""
        @retry_on_error(
            max_attempts=3,
            delay=1.0,
            backoff=2.0,
            error_types=(NetworkError,)
        )
        def test_func():
            raise NetworkError("Network error")
        
        with self.assertRaises(NetworkError):
            test_func()
        
        # Check sleep calls with exponential backoff
        calls = mock_sleep.call_args_list
        self.assertEqual(len(calls), 2)  # 2 retries (3 attempts total)
        self.assertEqual(calls[0], call(1.0))  # First delay
        self.assertEqual(calls[1], call(2.0))  # Second delay (1.0 * 2.0)


if __name__ == "__main__":
    unittest.main()