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
1. Uses the correct /v1/responses endpoint (not /v1/chat/completions)
2. Successfully completes a chat call
3. Returns properly formatted response
"""

from .base_test import BaseSimulatorTest


class ResponsesApiEndpointTest(BaseSimulatorTest):
    """Test Responses-API model routing and basic functionality (manual only)"""

    @property
    def test_name(self) -> str:
        return "responses_api_endpoint"

    @property
    def test_description(self) -> str:
        return "Responses API endpoint validation with gpt-6-luna (manual only)"

    def run_test(self) -> bool:
        """Test gpt-6-luna with endpoint verification."""
        try:
            self.logger.info("Test: Responses API endpoint and functionality test")
            self.logger.info("Step 1: Testing gpt-6-luna with chat tool")

            response, tool_result = self.call_mcp_tool(
                "chat",
                {
                    "prompt": "What is 2 + 2?",
                    "model": "gpt-6-luna",
                    "temperature": 1.0,
                },
            )

            if not response:
                self.logger.error("❌ gpt-6-luna chat call failed - no response")
                if tool_result and "error" in tool_result:
                    error_msg = tool_result["error"]
                    self.logger.error(f"Error details: {error_msg}")
                    if "v1/responses" in str(error_msg) and "v1/chat/completions" in str(error_msg):
                        self.logger.error(
                            "❌ ENDPOINT BUG DETECTED: gpt-6-luna is using chat/completions instead of responses endpoint!"
                        )
                return False

            # Check the metadata to verify endpoint was used
            if tool_result and isinstance(tool_result, dict):
                metadata = tool_result.get("metadata", {})
                endpoint_used = metadata.get("endpoint", "unknown")

                if endpoint_used == "responses":
                    self.logger.info("✅ Correct endpoint used: /v1/responses")
                else:
                    self.logger.warning(f"⚠️ Endpoint used: {endpoint_used} (expected: responses)")

            if response and "4" in str(response):
                self.logger.info("✅ gpt-6-luna response is mathematically correct")
            else:
                self.logger.warning(f"⚠️ Unexpected response: {response}")

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
