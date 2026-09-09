"""
Tests for Zen CLI command-line interface

These tests verify CLI command parsing and tool invocation.
Tests run against the actual CLI implementation in src/zen_cli/main.py
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

# Import CLI
from zen_cli.main import cli


class TestCLIBasicCommands:
    """Test basic CLI command parsing and execution"""

    def setup_method(self):
        """Setup for each test method"""
        self.runner = CliRunner()
        # Set minimal required env vars for provider initialization
        os.environ.setdefault("GEMINI_API_KEY", "test-key-gemini")
        os.environ.setdefault("OPENAI_API_KEY", "test-key-openai")

    def test_version_command(self):
        """Test --version flag"""
        result = self.runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "zen, version" in result.output or "version" in result.output.lower()

    def test_help_command(self):
        """Test --help flag"""
        result = self.runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Zen CLI" in result.output
        assert "AI-powered development assistant" in result.output

    def test_verbose_flag(self):
        """Test --verbose flag"""
        result = self.runner.invoke(cli, ["--verbose", "--help"])
        assert result.exit_code == 0


class TestChatCommand:
    """Test chat command"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()
        os.environ.setdefault("GEMINI_API_KEY", "test-key-gemini")
        os.environ.setdefault("OPENAI_API_KEY", "test-key-openai")

    def test_chat_help(self):
        """Test chat command help"""
        result = self.runner.invoke(cli, ["chat", "--help"])
        assert result.exit_code == 0
        assert "Chat with AI" in result.output

    @pytest.mark.asyncio
    async def test_chat_command_invokes_tool(self):
        """Test that chat command invokes ChatTool.execute()"""
        # Mock the ChatTool.execute method
        with patch("tools.chat.ChatTool.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"content": "# Test Response\n\nThis is a test response from AI."}

            self.runner.invoke(cli, ["chat", "Hello AI"])

            # Verify ChatTool.execute was called
            assert mock_execute.called
            # Verify arguments structure
            call_args = mock_execute.call_args[0][0]  # First positional arg
            assert isinstance(call_args, dict)
            assert call_args["prompt"] == "Hello AI"
            assert call_args["model"] == "auto"

    @pytest.mark.asyncio
    async def test_chat_with_model_option(self):
        """Test chat with explicit model"""
        with patch("tools.chat.ChatTool.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"content": "Test response"}

            self.runner.invoke(cli, ["chat", "Test message", "--model", "gemini-pro"])

            call_args = mock_execute.call_args[0][0]
            assert call_args["model"] == "gemini-pro"

    @pytest.mark.asyncio
    async def test_chat_with_files(self):
        """Test chat with context files"""
        with patch("tools.chat.ChatTool.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"content": "Test response"}

            self.runner.invoke(cli, ["chat", "Analyze this", "--files", "file1.py", "--files", "file2.py"])

            call_args = mock_execute.call_args[0][0]
            # ChatRequest declares absolute_file_paths, not files. Asserting the
            # old name here is what let the silent-drop bug survive.
            assert "files" not in call_args
            assert call_args["absolute_file_paths"] == [
                os.path.abspath("file1.py"),
                os.path.abspath("file2.py"),
            ]


class TestDebugCommand:
    """Test debug command"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()
        os.environ.setdefault("GEMINI_API_KEY", "test-key-gemini")
        os.environ.setdefault("OPENAI_API_KEY", "test-key-openai")

    def test_debug_help(self):
        """Test debug command help"""
        result = self.runner.invoke(cli, ["debug", "--help"])
        assert result.exit_code == 0
        assert "Debug issues" in result.output

    @pytest.mark.asyncio
    async def test_debug_command_invokes_tool(self):
        """Test that debug command invokes DebugIssueTool.execute()"""
        with patch("tools.debug.DebugIssueTool.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"content": "# Debug Analysis\n\nRoot cause identified."}

            self.runner.invoke(cli, ["debug", "OAuth not working"])

            assert mock_execute.called
            call_args = mock_execute.call_args[0][0]
            # DebugIssueTool is a workflow tool: the problem arrives as `step`.
            assert call_args["step"] == "OAuth not working"
            assert call_args["step_number"] == 1
            assert call_args["next_step_required"] is False
            assert call_args["confidence"] == "exploring"
            assert call_args["model"] == "auto"

    @pytest.mark.asyncio
    async def test_debug_with_confidence(self):
        """Test debug with confidence level"""
        with patch("tools.debug.DebugIssueTool.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"content": "Debug result"}

            self.runner.invoke(cli, ["debug", "Memory leak", "--confidence", "high"])

            call_args = mock_execute.call_args[0][0]
            assert call_args["confidence"] == "high"


class TestCodeReviewCommand:
    """Test codereview command"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()
        os.environ.setdefault("GEMINI_API_KEY", "test-key-gemini")
        os.environ.setdefault("OPENAI_API_KEY", "test-key-openai")

    def test_codereview_help(self):
        """Test codereview command help"""
        result = self.runner.invoke(cli, ["codereview", "--help"])
        assert result.exit_code == 0
        assert "code review" in result.output.lower()

    @pytest.mark.asyncio
    async def test_codereview_requires_files(self):
        """Test that codereview warns when no files provided"""
        result = self.runner.invoke(cli, ["codereview"])
        # Should show warning but not crash
        assert "No files specified" in result.output or result.exit_code == 0

    @pytest.mark.asyncio
    async def test_codereview_with_files(self):
        """Test codereview with files"""
        with patch("tools.codereview.CodeReviewTool.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"content": "Review complete"}

            self.runner.invoke(cli, ["codereview", "--files", "src/main.py", "--type", "security"])

            call_args = mock_execute.call_args[0][0]
            assert "files" not in call_args
            assert call_args["relevant_files"] == [os.path.abspath("src/main.py")]
            assert call_args["review_type"] == "security"


class TestConsensusCommand:
    """Test consensus command"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()
        os.environ.setdefault("GEMINI_API_KEY", "test-key-gemini")
        os.environ.setdefault("OPENAI_API_KEY", "test-key-openai")

    def test_consensus_help(self):
        """Test consensus command help"""
        result = self.runner.invoke(cli, ["consensus", "--help"])
        assert result.exit_code == 0
        assert "consensus" in result.output.lower()

    @pytest.mark.asyncio
    async def test_consensus_with_models(self):
        """Test consensus with multiple models"""
        with patch("tools.consensus.ConsensusTool.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"content": "Consensus reached"}

            self.runner.invoke(cli, ["consensus", "Should we use microservices?", "--models", "gemini-pro,o3"])

            call_args = mock_execute.call_args[0][0]
            assert call_args["step"] == "Should we use microservices?"
            assert "models" in call_args
            # Models should be parsed into list of dicts
            assert isinstance(call_args["models"], list)


class TestListModelsCommand:
    """Test listmodels command"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()
        os.environ.setdefault("GEMINI_API_KEY", "test-key-gemini")
        os.environ.setdefault("OPENAI_API_KEY", "test-key-openai")

    def test_listmodels_help(self):
        """Test listmodels command help"""
        result = self.runner.invoke(cli, ["listmodels", "--help"])
        assert result.exit_code == 0
        assert "List all available AI models" in result.output

    def test_listmodels_default_format(self):
        """Test listmodels with default table format"""
        # This should run the actual command since it doesn't make API calls
        result = self.runner.invoke(cli, ["listmodels"])
        # Should complete (may fail if API keys invalid, that's OK)
        # The important thing is it doesn't crash
        assert result.exit_code in [0, 1]  # Allow either success or graceful failure
        # If it succeeded, should contain provider information
        if result.exit_code == 0:
            assert "Provider" in result.output or "Models" in result.output

    def test_listmodels_json_format(self):
        """Test listmodels with JSON output"""
        result = self.runner.invoke(cli, ["listmodels", "--format", "json"])
        # Allow graceful failure if API keys invalid
        assert result.exit_code in [0, 1]
        # If successful, should produce valid JSON output
        if result.exit_code == 0:
            assert "{" in result.output and "}" in result.output

    def test_listmodels_simple_format(self):
        """Test listmodels with simple format"""
        result = self.runner.invoke(cli, ["listmodels", "--format", "simple"])
        # Allow graceful failure if API keys invalid
        assert result.exit_code in [0, 1]


class TestVersionCommand:
    """Test version command"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()

    def test_version_command(self):
        """Test version command"""
        result = self.runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "Zen CLI" in result.output
        assert "v9" in result.output  # Should show version


class TestCLIErrorHandling:
    """Test CLI error handling"""

    def setup_method(self):
        """Setup for each test"""
        self.runner = CliRunner()
        os.environ.setdefault("GEMINI_API_KEY", "test-key-gemini")
        os.environ.setdefault("OPENAI_API_KEY", "test-key-openai")

    def test_unknown_command(self):
        """Test handling of unknown command"""
        result = self.runner.invoke(cli, ["nonexistent"])
        assert result.exit_code != 0
        assert "Error" in result.output or "No such command" in result.output

    @pytest.mark.asyncio
    async def test_tool_execution_error(self):
        """Test handling of tool execution errors"""
        with patch("tools.chat.ChatTool.execute", new_callable=AsyncMock) as mock_execute:
            # Simulate tool execution error
            mock_execute.side_effect = Exception("API error occurred")

            result = self.runner.invoke(cli, ["chat", "Test"])

            # Should handle error gracefully
            assert "Error" in result.output


class TestPrintResultJson:
    """Regression tests for print_result_json (--json serialization of tool results).

    Guards against the "Object of type TextContent is not JSON serializable" crash
    that affected chat/debug/codereview/clink/challenge/apilookup with --json.
    """

    def _capture(self, result):
        import json as _json

        from rich.console import Console

        from zen_cli import main as cli_main

        buffer = Console(record=True, force_terminal=False)
        original = cli_main.console
        cli_main.console = buffer
        try:
            cli_main.print_result_json(result)
        finally:
            cli_main.console = original
        return _json.loads(buffer.export_text())

    def test_single_textcontent_json_payload(self):
        """List with one TextContent whose .text is JSON -> parsed object."""

        class TC:
            text = '{"status": "success", "content": "pong"}'

        assert self._capture([TC()]) == {"status": "success", "content": "pong"}

    def test_empty_list_yields_empty_array(self):
        """Empty result list must not crash; serializes to []."""
        assert self._capture([]) == []

    def test_multiple_textcontent_items_preserved(self):
        """Multiple items are preserved as a list, not silently dropped."""

        class TC:
            def __init__(self, t):
                self.text = t

        assert self._capture([TC('{"a": 1}'), TC('{"b": 2}')]) == [{"a": 1}, {"b": 2}]

    def test_non_json_text_wrapped_in_content(self):
        """Plain (non-JSON) text degrades to a {"content": ...} object."""

        class TC:
            text = "just a plain string"

        assert self._capture([TC()]) == {"content": "just a plain string"}


class TestPrintResultHuman:
    """Regression tests for print_result_human (human pretty-print of tool results)."""

    def _capture(self, result):
        from rich.console import Console

        from zen_cli import main as cli_main

        buffer = Console(record=True, force_terminal=False)
        original = cli_main.console
        cli_main.console = buffer
        try:
            cli_main.print_result_human(result)
        finally:
            cli_main.console = original
        return buffer.export_text()

    def test_textcontent_tooloutput_renders_content(self):
        class TC:
            text = '{"status": "success", "content": "Hello from the model"}'

        assert "Hello from the model" in self._capture([TC()])

    def test_plain_dict_content_field(self):
        assert "legacy path" in self._capture({"content": "legacy path"})

    def test_empty_list_is_quiet(self):
        assert "no content" in self._capture([]).lower()


class TestChatJsonSerializationEndToEnd:
    """CLI-level regression: chat --json must not crash on list[TextContent]."""

    def setup_method(self):
        self.runner = CliRunner()
        os.environ.setdefault("GEMINI_API_KEY", "test-key-gemini")
        os.environ.setdefault("OPENAI_API_KEY", "test-key-openai")

    def test_chat_json_with_textcontent_list(self):
        import json as _json

        class TC:
            text = '{"status": "success", "content": "pong", "content_type": "text"}'

        with patch("tools.chat.ChatTool.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = [TC()]
            result = self.runner.invoke(cli, ["chat", "ping", "--json"])

        assert result.exit_code == 0, result.output
        assert "not JSON serializable" not in result.output
        payload = _json.loads(result.output)
        assert payload["status"] == "success"
        assert payload["content"] == "pong"

    def test_chat_human_with_textcontent_list(self):
        class TC:
            text = '{"status": "success", "content": "human readable answer"}'

        with patch("tools.chat.ChatTool.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = [TC()]
            result = self.runner.invoke(cli, ["chat", "ping"])

        assert result.exit_code == 0, result.output
        assert "human readable answer" in result.output


class TestClinkModelFlag:
    """CLI wiring: zen clink --model is forwarded into CLinkTool arguments."""

    def setup_method(self):
        self.runner = CliRunner()
        os.environ.setdefault("GEMINI_API_KEY", "test-key-gemini")
        os.environ.setdefault("OPENAI_API_KEY", "test-key-openai")

    def test_clink_model_option_forwarded(self):
        class TC:
            text = '{"status": "success", "content": "ok"}'

        with patch("tools.clink.CLinkTool.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = [TC()]
            result = self.runner.invoke(
                cli,
                ["clink", "review this", "--cli-name", "claude", "--model", "fable", "--json"],
            )

        assert result.exit_code == 0, result.output
        assert mock_execute.called
        call_args = mock_execute.call_args[0][0]
        assert call_args["model"] == "fable"
        assert call_args["cli_name"] == "claude"

    def test_clink_without_model_omits_key(self):
        class TC:
            text = '{"status": "success", "content": "ok"}'

        with patch("tools.clink.CLinkTool.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = [TC()]
            result = self.runner.invoke(cli, ["clink", "hello", "--cli-name", "gemini", "--json"])

        assert result.exit_code == 0, result.output
        call_args = mock_execute.call_args[0][0]
        assert "model" not in call_args


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestCLIToolContract:
    """Every CLI command must send arguments its tool actually accepts.

    Regression guard for the d2773f4 drift: the tool request models were renamed
    (files -> absolute_file_paths / relevant_files) but src/zen_cli/main.py kept
    sending the old keys. Pydantic ignores unknown keys, so -f/--files was
    accepted, discarded, and the model answered with no file attached - no error
    anywhere. The previous tests missed it because they mocked execute() and then
    asserted the CLI's own wrong contract back at itself.

    This validates the captured argument dict against the REAL request model, so
    the next rename fails here instead of silently dropping user data.
    """

    CASES = [
        ("chat", "tools.chat.ChatTool.execute", "tools.chat", "ChatTool", ["chat", "hi", "-f", "a.py"]),
        ("clink", "tools.clink.CLinkTool.execute", "tools.clink", "CLinkTool", ["clink", "hi", "-f", "a.py"]),
        (
            "debug",
            "tools.debug.DebugIssueTool.execute",
            "tools.debug",
            "DebugIssueTool",
            ["debug", "boom", "-f", "a.py"],
        ),
        (
            "codereview",
            "tools.codereview.CodeReviewTool.execute",
            "tools.codereview",
            "CodeReviewTool",
            ["codereview", "-f", "a.py", "--type", "security"],
        ),
        (
            "analyze",
            "tools.analyze.AnalyzeTool.execute",
            "tools.analyze",
            "AnalyzeTool",
            ["analyze", "goal", "-f", "a.py"],
        ),
        (
            "precommit",
            "tools.precommit.PrecommitTool.execute",
            "tools.precommit",
            "PrecommitTool",
            ["precommit", "goal", "-f", "a.py"],
        ),
        (
            "testgen",
            "tools.testgen.TestGenTool.execute",
            "tools.testgen",
            "TestGenTool",
            ["testgen", "goal", "-f", "a.py"],
        ),
        (
            "secaudit",
            "tools.secaudit.SecauditTool.execute",
            "tools.secaudit",
            "SecauditTool",
            ["secaudit", "goal", "-f", "a.py"],
        ),
        (
            "refactor",
            "tools.refactor.RefactorTool.execute",
            "tools.refactor",
            "RefactorTool",
            ["refactor", "goal", "-f", "a.py"],
        ),
    ]

    def setup_method(self):
        self.runner = CliRunner()
        os.environ.setdefault("GEMINI_API_KEY", "test-key-gemini")
        os.environ.setdefault("OPENAI_API_KEY", "test-key-openai")

    def _capture(self, target, argv):
        with patch(target, new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"content": "ok"}
            self.runner.invoke(cli, argv)
            assert mock_execute.called, f"{argv[0]} never invoked its tool"
            return mock_execute.call_args[0][0]

    @staticmethod
    def _request_model(tool, module, cls):
        if cls == "ChatTool":
            from tools.chat import ChatRequest

            return ChatRequest
        if cls == "CLinkTool":
            from tools.clink import CLinkRequest

            return CLinkRequest
        return tool.get_workflow_request_model()

    @pytest.mark.parametrize("name,target,module,cls,argv", CASES, ids=[c[0] for c in CASES])
    def test_arguments_contain_no_unknown_keys(self, name, target, module, cls, argv):
        """A key the schema does not declare is silently dropped, not rejected."""
        args = self._capture(target, argv)
        tool = getattr(__import__(module, fromlist=[cls]), cls)()
        declared = set(tool.get_input_schema().get("properties", {}))
        unknown = sorted(set(args) - declared)
        assert not unknown, f"{name} sends keys its tool will discard: {unknown}"

    @pytest.mark.parametrize("name,target,module,cls,argv", CASES, ids=[c[0] for c in CASES])
    def test_arguments_validate_against_request_model(self, name, target, module, cls, argv):
        """The dict the CLI builds must actually construct the tool's request."""
        args = self._capture(target, argv)
        tool = getattr(__import__(module, fromlist=[cls]), cls)()
        self._request_model(tool, module, cls)(**args)

    @pytest.mark.parametrize("name,target,module,cls,argv", CASES, ids=[c[0] for c in CASES])
    def test_files_option_reaches_the_tool(self, name, target, module, cls, argv):
        """-f must land in a field the tool reads, under some declared name."""
        args = self._capture(target, argv)
        landed = [k for k in ("absolute_file_paths", "relevant_files") if args.get(k)]
        assert landed, f"{name} dropped its -f/--files argument entirely"
