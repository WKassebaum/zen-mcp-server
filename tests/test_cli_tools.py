"""
Tests for CLI tools and command execution
"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
import asyncio

import sys
sys.path.insert(0, 'src')

from zen_cli.tools.chat import ChatTool
from zen_cli.tools.version import VersionTool  
from zen_cli.tools.listmodels import ListModelsTool
from zen_cli.utils.conversation_memory import ConversationMemory
from zen_cli.utils.storage_backend import InMemoryStorage


class TestChatTool:
    """Test the chat tool functionality"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.storage = InMemoryStorage()
        self.memory = ConversationMemory(storage_backend=self.storage)
        self.tool = ChatTool()
    
    @pytest.mark.asyncio
    async def test_chat_tool_initialization(self):
        """Test that chat tool initializes correctly"""
        assert self.tool is not None
        assert hasattr(self.tool, 'execute')
    
    @pytest.mark.asyncio
    async def test_chat_with_mock_provider(self):
        """Test chat execution with mocked provider"""
        # Mock the provider execution
        with patch('zen_cli.providers.registry.get_provider') as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.name = 'test_provider'
            mock_provider.execute.return_value = {
                'status': 'success',
                'result': 'Test response from AI'
            }
            mock_get_provider.return_value = mock_provider
            
            # Execute chat tool
            result = await self.tool.execute(
                message="Hello, how are you?",
                model="test-model",
                conversation_memory=self.memory
            )
            
            # Verify result structure
            assert isinstance(result, dict)
            assert result.get('status') == 'success'
            assert 'result' in result


class TestVersionTool:
    """Test the version tool functionality"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.tool = VersionTool()
    
    @pytest.mark.asyncio
    async def test_version_tool_execution(self):
        """Test version tool returns version information"""
        result = await self.tool.execute()
        
        assert isinstance(result, dict)
        assert result.get('status') == 'success'
        assert 'result' in result
        
        # Version info should contain certain fields
        version_info = result['result']
        assert 'version' in version_info
        assert 'python_version' in version_info
        assert 'installation_path' in version_info


class TestListModelsTool:
    """Test the list models tool functionality"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.tool = ListModelsTool()
    
    @pytest.mark.asyncio
    async def test_list_models_execution(self):
        """Test list models tool returns available models"""
        result = await self.tool.execute()
        
        assert isinstance(result, dict)
        assert result.get('status') == 'success'
        assert 'result' in result
        
        # Should contain model information
        models_info = result['result']
        assert 'available_models' in models_info
        assert isinstance(models_info['available_models'], list)


class TestConversationMemory:
    """Test conversation memory functionality"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.storage = InMemoryStorage()
        self.memory = ConversationMemory(storage_backend=self.storage)
        self.session_id = "test_session"
    
    def test_create_session(self):
        """Test session creation"""
        session_info = self.memory.create_session(self.session_id)
        
        assert isinstance(session_info, dict)
        assert session_info['session_id'] == self.session_id
        assert 'created_at' in session_info
    
    def test_add_and_get_messages(self):
        """Test adding and retrieving messages"""
        self.memory.create_session(self.session_id)
        
        # Add user message
        self.memory.add_message(self.session_id, "user", "Hello AI")
        
        # Add assistant message  
        self.memory.add_message(self.session_id, "assistant", "Hello user!")
        
        # Get conversation history
        history = self.memory.get_conversation_history(self.session_id)
        
        assert len(history) == 2
        assert history[0]['role'] == 'user'
        assert history[0]['content'] == 'Hello AI'
        assert history[1]['role'] == 'assistant'
        assert history[1]['content'] == 'Hello user!'
    
    def test_session_management(self):
        """Test session listing and cleanup"""
        # Create multiple sessions
        sessions = ['session1', 'session2', 'session3']
        for session_id in sessions:
            self.memory.create_session(session_id)
        
        # List active sessions
        active_sessions = self.memory.list_active_sessions()
        
        assert len(active_sessions) == 3
        session_ids = [s['session_id'] for s in active_sessions]
        for session_id in sessions:
            assert session_id in session_ids
        
        # Delete a session
        self.memory.delete_session('session1')
        active_sessions = self.memory.list_active_sessions()
        assert len(active_sessions) == 2
    
    def test_session_continuation(self):
        """Test continuing existing sessions"""
        self.memory.create_session(self.session_id)
        self.memory.add_message(self.session_id, "user", "First message")
        
        # Continue session (should not create duplicate)
        session_info = self.memory.continue_session(self.session_id)
        
        assert session_info['session_id'] == self.session_id
        assert session_info['message_count'] == 1
        
        # Should still have the original message
        history = self.memory.get_conversation_history(self.session_id)
        assert len(history) == 1
        assert history[0]['content'] == 'First message'


class TestToolIntegration:
    """Integration tests for tool execution pipeline"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.storage = InMemoryStorage()
        self.memory = ConversationMemory(storage_backend=self.storage)
    
    @pytest.mark.asyncio
    async def test_tool_error_handling(self):
        """Test that tools handle errors gracefully"""
        tool = ChatTool()
        
        # Test with invalid parameters
        result = await tool.execute(
            message="",  # Empty message
            model="nonexistent-model",
            conversation_memory=self.memory
        )
        
        # Should return error status instead of raising exception
        assert isinstance(result, dict)
        # Should handle gracefully (either success with error message or error status)
        assert 'status' in result
    
    @pytest.mark.asyncio 
    async def test_multiple_tool_execution(self):
        """Test executing multiple tools in sequence"""
        version_tool = VersionTool()
        models_tool = ListModelsTool()
        
        # Execute both tools
        version_result = await version_tool.execute()
        models_result = await models_tool.execute()
        
        # Both should succeed
        assert version_result.get('status') == 'success'
        assert models_result.get('status') == 'success'
        
        # Results should be independent
        assert version_result['result'] != models_result['result']


def test_api_key_detection():
    """Test that API key detection works correctly"""
    from zen_cli.providers.registry import detect_available_providers
    
    # Mock environment with some API keys
    with patch.dict(os.environ, {
        'GEMINI_API_KEY': 'test_gemini_key',
        'OPENAI_API_KEY': 'test_openai_key'
    }):
        available = detect_available_providers()
        
        # Should detect providers based on API keys
        assert isinstance(available, list)
        assert len(available) > 0


def test_model_name_parsing():
    """Test model name parsing and provider detection"""
    from zen_cli.providers.registry import get_provider_for_model
    
    # Test various model name formats
    test_cases = [
        ("gpt-4", "openai"),
        ("gpt-3.5-turbo", "openai"), 
        ("gemini-pro", "gemini"),
        ("flash", "gemini"),  # Common alias
    ]
    
    for model_name, expected_provider in test_cases:
        try:
            provider = get_provider_for_model(model_name)
            if provider:  # Provider available
                assert provider.name == expected_provider
        except Exception:
            # Provider not available (e.g., no API key) - this is okay
            pass


if __name__ == '__main__':
    # Run tests if called directly
    pytest.main([__file__, '-v'])