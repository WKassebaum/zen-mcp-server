#!/usr/bin/env python3
"""
Responses API Endpoint Test

Originally the o3-pro "expensive" test. o3-pro was retired upstream and pruned from
the catalog on 2026-09-26, so this now exercises the same /v1/responses routing with
gpt-6-luna, OpenAI's low-cost Responses-API model ($0.10/$0.50 per 1M tokens).

Not in TEST_REGISTRY by default (it needs a real OpenAI key). Run it manually by
enabling the commented-out registry entry, then:
    python communication_simulator_test.py --individual responses_api_endpoint

Tests that gpt-6-luna:
1. Successfully completes a chat call (any tool error fails the test)
2. Uses the /v1/responses endpoint (checked in logs/mcp_server.log; needs LOG_LEVEL INFO or DEBUG)
3. Answers "What is 2 + 2?" with 4
"""

import json
import os
import re
import tempfile

from .base_test import BaseSimulatorTest
from .log_utils import LogUtils

# Logged by OpenAICompatibleProvider._generate_with_responses_endpoint right before
# client.responses.create(); the chat/completions path never writes it.
RESPONSES_LOG_MARKER = "Responses API request (sanitized)"
# The sanitized params follow the marker as indented JSON; OpenRouter uses the prefixed ID.
RESPONSES_MODEL_RE = re.compile(r'"model": "(?:openai/)?gpt-6-luna"')
OK_STATUSES = {"success", "continuation_available"}


class ResponsesApiEndpointTest(BaseSimulatorTest):
    """Test Responses-API model routing and basic functionality (manual only)"""

    @property
    def test_name(self) -> str:
        return "responses_api_endpoint"

    @property
    def test_description(self) -> str:
        return "Responses API endpoint validation with gpt-6-luna (manual only)"

    @staticmethod
    def _log_size() -> int:
        try:
            return os.path.getsize(LogUtils.MAIN_LOG_FILE)
        except OSError:
            return 0

    @staticmethod
    def _read_log_from(offset: int) -> str:
        """Return what the server wrote to the main log after `offset` (whole file if it rotated)."""
        try:
            if os.path.getsize(LogUtils.MAIN_LOG_FILE) < offset:
                offset = 0
            with open(LogUtils.MAIN_LOG_FILE, encoding="utf-8", errors="replace") as f:
                f.seek(offset)
                return f.read()
        except OSError:
            return ""

    def run_test(self) -> bool:
        """Test gpt-6-luna with endpoint verification. Any tool error or wrong endpoint fails."""
        try:
            self.logger.info("Test: Responses API endpoint and functionality test")
            self.logger.info("Step 1: Testing gpt-6-luna with chat tool")

            log_offset = self._log_size()

            # call_mcp_tool returns (tool output text, continuation_id); the text is the
            # tool's ToolOutput JSON. MCP isError results carry the same JSON (status "error"),
            # except schema-validation failures, which come back as plain text.
            with tempfile.TemporaryDirectory(prefix="zen_responses_api_") as work_dir:
                response_text, _continuation_id = self.call_mcp_tool(
                    "chat",
                    {
                        "prompt": "What is 2 + 2?",
                        "model": "gpt-6-luna",
                        "temperature": 1.0,
                        "working_directory_absolute_path": work_dir,
                    },
                )

            if not response_text:
                self.logger.error("❌ gpt-6-luna chat call failed - no response from the MCP server")
                return False

            try:
                output = json.loads(response_text)
            except json.JSONDecodeError:
                self.logger.error(f"❌ Tool output is not ToolOutput JSON: {response_text[:500]}")
                return False

            status = output.get("status")
            if status not in OK_STATUSES:
                self.logger.error(f"❌ Tool returned status {status!r}: {str(output.get('content'))[:500]}")
                return False

            model_used = (output.get("metadata") or {}).get("model_used")
            if model_used not in ("gpt-6-luna", "openai/gpt-6-luna"):
                self.logger.error(f"❌ Expected gpt-6-luna, tool reports model_used={model_used!r}")
                return False

            # Endpoint check. The tool output does not carry the provider's endpoint metadata
            # (it only reaches conversation memory), so read the server log written during
            # this call. The marker is logged at INFO, so LOG_LEVEL must be INFO or DEBUG.
            new_logs = self._read_log_from(log_offset)
            marker_at = new_logs.find(RESPONSES_LOG_MARKER)
            if marker_at == -1:
                self.logger.error(
                    f"❌ No '{RESPONSES_LOG_MARKER}' line in {LogUtils.MAIN_LOG_FILE} for this call: "
                    "gpt-6-luna did not go through /v1/responses (or LOG_LEVEL is above INFO)"
                )
                return False
            if not RESPONSES_MODEL_RE.search(new_logs, marker_at, marker_at + 2000):
                self.logger.error("❌ Responses API request was logged, but not for gpt-6-luna")
                return False
            self.logger.info("✅ Correct endpoint used: /v1/responses")

            content = str(output.get("content", ""))
            if "4" not in content:
                self.logger.error(f"❌ Unexpected answer to 'What is 2 + 2?': {content[:500]}")
                return False
            self.logger.info("✅ gpt-6-luna response is mathematically correct")

            self.logger.info("✅ Responses API endpoint test completed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Responses API endpoint test failed with exception: {e}")
            import traceback

            self.logger.error(f"Full traceback: {traceback.format_exc()}")
            return False


def main():
    """Run the Responses API endpoint test"""
    import sys

    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    test = ResponsesApiEndpointTest(verbose=verbose)

    success = test.run_test()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
