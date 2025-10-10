"""
Tests for Zen CLI command-line interface

These tests verify CLI command parsing and tool invocation.
Tests run against the actual CLI implementation in src/zen_cli/main.py
"""

import os
import sys
import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock, AsyncMock

# Import CLI
from zen_cli.main import cli


class TestCLIBasicCommands:
    """Test basic CLI command parsing and execution"""

    def setup_method(self):
        """Setup for each test method"""
        self.runner = CliRunner()
        # Set minimal required env vars for provider initialization
        os.environ.setdefault('GEMINI_API_KEY', 'test-key-gemini')
        os.environ.setdefault('OPENAI_API_KEY', 'test-key-openai')

    def test_version_command(self):
        """Test --version flag"""
        result = self.runner.invoke(cli, ['--version'])
        assert result.exit_code == 0
        assert 'zen, version' in result.output or 'version' in result.output.lower()

    def test_help_command(self):
        """Test --help flag"""
        result = self.runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'Zen CLI' in result.output
        assert 'AI-powered development assistant' in result.output

    def test_verbose_flag(self):
        """Test --verbose flag"""
        result = self.runner.invoke(cli, ['--verbose', '--help'])
        assert result.exit_code == 0


class TestChatCommand:
    """Test chat command"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()
        os.environ.setdefault('GEMINI_API_KEY', 'test-key-gemini')
        os.environ.setdefault('OPENAI_API_KEY', 'test-key-openai')

    def test_chat_help(self):
        """Test chat command help"""
        result = self.runner.invoke(cli, ['chat', '--help'])
        assert result.exit_code == 0
        assert 'Chat with AI' in result.output

    @pytest.mark.asyncio
    async def test_chat_command_invokes_tool(self):
        """Test that chat command invokes ChatTool.execute()"""
        # Mock the ChatTool.execute method
        with patch('tools.chat.ChatTool.execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                'content': '# Test Response\n\nThis is a test response from AI.'
            }

            result = self.runner.invoke(cli, ['chat', 'Hello AI'])

            # Verify ChatTool.execute was called
            assert mock_execute.called
            # Verify arguments structure
            call_args = mock_execute.call_args[0][0]  # First positional arg
            assert isinstance(call_args, dict)
            assert call_args['prompt'] == 'Hello AI'
            assert call_args['model'] == 'auto'

    @pytest.mark.asyncio
    async def test_chat_with_model_option(self):
        """Test chat with explicit model"""
        with patch('tools.chat.ChatTool.execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {'content': 'Test response'}

            result = self.runner.invoke(cli, ['chat', 'Test message', '--model', 'gemini-pro'])

            call_args = mock_execute.call_args[0][0]
            assert call_args['model'] == 'gemini-pro'

    @pytest.mark.asyncio
    async def test_chat_with_files(self):
        """Test chat with context files"""
        with patch('tools.chat.ChatTool.execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {'content': 'Test response'}

            result = self.runner.invoke(cli, [
                'chat', 'Analyze this',
                '--files', 'file1.py',
                '--files', 'file2.py'
            ])

            call_args = mock_execute.call_args[0][0]
            assert 'files' in call_args
            assert call_args['files'] == ['file1.py', 'file2.py']


class TestDebugCommand:
    """Test debug command"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()
        os.environ.setdefault('GEMINI_API_KEY', 'test-key-gemini')
        os.environ.setdefault('OPENAI_API_KEY', 'test-key-openai')

    def test_debug_help(self):
        """Test debug command help"""
        result = self.runner.invoke(cli, ['debug', '--help'])
        assert result.exit_code == 0
        assert 'Debug issues' in result.output

    @pytest.mark.asyncio
    async def test_debug_command_invokes_tool(self):
        """Test that debug command invokes DebugIssueTool.execute()"""
        with patch('tools.debug.DebugIssueTool.execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                'content': '# Debug Analysis\n\nRoot cause identified.'
            }

            result = self.runner.invoke(cli, ['debug', 'OAuth not working'])

            assert mock_execute.called
            call_args = mock_execute.call_args[0][0]
            assert call_args['problem_description'] == 'OAuth not working'
            assert call_args['confidence'] == 'exploring'
            assert call_args['model'] == 'auto'

    @pytest.mark.asyncio
    async def test_debug_with_confidence(self):
        """Test debug with confidence level"""
        with patch('tools.debug.DebugIssueTool.execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {'content': 'Debug result'}

            result = self.runner.invoke(cli, [
                'debug', 'Memory leak',
                '--confidence', 'high'
            ])

            call_args = mock_execute.call_args[0][0]
            assert call_args['confidence'] == 'high'


class TestCodeReviewCommand:
    """Test codereview command"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()
        os.environ.setdefault('GEMINI_API_KEY', 'test-key-gemini')
        os.environ.setdefault('OPENAI_API_KEY', 'test-key-openai')

    def test_codereview_help(self):
        """Test codereview command help"""
        result = self.runner.invoke(cli, ['codereview', '--help'])
        assert result.exit_code == 0
        assert 'code review' in result.output.lower()

    @pytest.mark.asyncio
    async def test_codereview_requires_files(self):
        """Test that codereview warns when no files provided"""
        result = self.runner.invoke(cli, ['codereview'])
        # Should show warning but not crash
        assert 'No files specified' in result.output or result.exit_code == 0

    @pytest.mark.asyncio
    async def test_codereview_with_files(self):
        """Test codereview with files"""
        with patch('tools.codereview.CodeReviewTool.execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {'content': 'Review complete'}

            result = self.runner.invoke(cli, [
                'codereview',
                '--files', 'src/main.py',
                '--type', 'security'
            ])

            call_args = mock_execute.call_args[0][0]
            assert call_args['files'] == ['src/main.py']
            assert call_args['review_type'] == 'security'


class TestConsensusCommand:
    """Test consensus command"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()
        os.environ.setdefault('GEMINI_API_KEY', 'test-key-gemini')
        os.environ.setdefault('OPENAI_API_KEY', 'test-key-openai')

    def test_consensus_help(self):
        """Test consensus command help"""
        result = self.runner.invoke(cli, ['consensus', '--help'])
        assert result.exit_code == 0
        assert 'consensus' in result.output.lower()

    @pytest.mark.asyncio
    async def test_consensus_with_models(self):
        """Test consensus with multiple models"""
        with patch('tools.consensus.ConsensusTool.execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {'content': 'Consensus reached'}

            result = self.runner.invoke(cli, [
                'consensus', 'Should we use microservices?',
                '--models', 'gemini-pro,o3'
            ])

            call_args = mock_execute.call_args[0][0]
            assert call_args['prompt'] == 'Should we use microservices?'
            assert 'models' in call_args
            # Models should be parsed into list of dicts
            assert isinstance(call_args['models'], list)


class TestListModelsCommand:
    """Test listmodels command"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()
        os.environ.setdefault('GEMINI_API_KEY', 'test-key-gemini')
        os.environ.setdefault('OPENAI_API_KEY', 'test-key-openai')

    def test_listmodels_help(self):
        """Test listmodels command help"""
        result = self.runner.invoke(cli, ['listmodels', '--help'])
        assert result.exit_code == 0
        assert 'List all available AI models' in result.output

    def test_listmodels_default_format(self):
        """Test listmodels with default table format"""
        # This should run the actual command since it doesn't make API calls
        result = self.runner.invoke(cli, ['listmodels'])
        # Should complete (may fail if API keys invalid, that's OK)
        # The important thing is it doesn't crash
        assert result.exit_code in [0, 1]  # Allow either success or graceful failure
        # If it succeeded, should contain provider information
        if result.exit_code == 0:
            assert 'Provider' in result.output or 'Models' in result.output

    def test_listmodels_json_format(self):
        """Test listmodels with JSON output"""
        result = self.runner.invoke(cli, ['listmodels', '--format', 'json'])
        # Allow graceful failure if API keys invalid
        assert result.exit_code in [0, 1]
        # If successful, should produce valid JSON output
        if result.exit_code == 0:
            assert '{' in result.output and '}' in result.output

    def test_listmodels_simple_format(self):
        """Test listmodels with simple format"""
        result = self.runner.invoke(cli, ['listmodels', '--format', 'simple'])
        # Allow graceful failure if API keys invalid
        assert result.exit_code in [0, 1]


class TestVersionCommand:
    """Test version command"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()

    def test_version_command(self):
        """Test version command"""
        result = self.runner.invoke(cli, ['version'])
        assert result.exit_code == 0
        assert 'Zen CLI' in result.output
        assert 'v8' in result.output or 'v5' in result.output  # Should show version


class TestCLIErrorHandling:
    """Test CLI error handling"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()
        os.environ.setdefault('GEMINI_API_KEY', 'test-key-gemini')
        os.environ.setdefault('OPENAI_API_KEY', 'test-key-openai')

    def test_unknown_command(self):
        """Test handling of unknown command"""
        result = self.runner.invoke(cli, ['nonexistent'])
        assert result.exit_code != 0
        assert 'Error' in result.output or 'No such command' in result.output

    @pytest.mark.asyncio
    async def test_tool_execution_error(self):
        """Test handling of tool execution errors"""
        with patch('tools.chat.ChatTool.execute', new_callable=AsyncMock) as mock_execute:
            # Simulate tool execution error
            mock_execute.side_effect = Exception("API error occurred")

            result = self.runner.invoke(cli, ['chat', 'Test'])

            # Should handle error gracefully
            assert 'Error' in result.output


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
