"""Tests for OpenRouter store parameter handling in responses endpoint.

Regression tests for GitHub Issue #348: OpenAI "store" parameter validation error
for certain models via OpenRouter.

OpenRouter's /responses endpoint rejects store:true via Zod validation but accepts
store:false (verified live 2026-09-27). zen resends the full conversation on every turn
and never uses previous_response_id, so it has no use for server-side retention.
These tests verify that both providers send store: false:
- OpenRouter never receives store:true (the Issue #348 failure)
- Direct OpenAI opts out of OpenAI's default store:true, so prompts are not retained

Before 2026-09-27 direct OpenAI requests sent store:true and OpenRouter requests omitted
the parameter; the tests were updated when that retention was switched off.
"""

import unittest
from unittest.mock import Mock, patch

from providers.openai_compatible import OpenAICompatibleProvider
from providers.shared import ProviderType


class MockOpenRouterProvider(OpenAICompatibleProvider):
    """Mock provider that simulates OpenRouter behavior."""

    FRIENDLY_NAME = "OpenRouter Test"

    def get_provider_type(self):
        return ProviderType.OPENROUTER

    def get_capabilities(self, model_name):
        mock_caps = Mock()
        mock_caps.default_reasoning_effort = "high"
        return mock_caps

    def validate_model_name(self, model_name):
        return True

    def list_models(self, **kwargs):
        return ["openai/gpt-5-pro", "openai/gpt-5.1-codex"]


class MockOpenAIProvider(OpenAICompatibleProvider):
    """Mock provider that simulates direct OpenAI behavior."""

    FRIENDLY_NAME = "OpenAI Test"

    def get_provider_type(self):
        return ProviderType.OPENAI

    def get_capabilities(self, model_name):
        mock_caps = Mock()
        mock_caps.default_reasoning_effort = "high"
        return mock_caps

    def validate_model_name(self, model_name):
        return True

    def list_models(self, **kwargs):
        return ["gpt-5-pro", "gpt-5.1-codex"]


class TestStoreParameterHandling(unittest.TestCase):
    """Test store parameter is conditionally included based on provider type.

    **Feature: openrouter-store-parameter-fix, Property 1: OpenRouter requests never send store:true**
    **Feature: responses-no-retention, Property 2: Direct OpenAI requests send store:false**
    """

    def test_openrouter_responses_sends_store_false(self):
        """Test that OpenRouter provider sends store:false (never store:true) to the responses endpoint.

        **Feature: openrouter-store-parameter-fix, Property 1: OpenRouter requests never send store:true**
        **Validates: Requirements 1.1, 2.1**

        OpenRouter's /responses endpoint rejects store:true via Zod validation (Issue #348)
        and accepts store:false.
        """
        # Capture the completion_params passed to the API
        captured_params = {}

        def capture_create(**kwargs):
            captured_params.update(kwargs)
            # Return a mock response
            mock_response = Mock()
            mock_response.output_text = "Test response"
            mock_response.usage = None
            return mock_response

        mock_client_instance = Mock()
        mock_client_instance.responses.create = capture_create

        with patch.object(
            MockOpenRouterProvider, "client", new_callable=lambda: property(lambda self: mock_client_instance)
        ):
            provider = MockOpenRouterProvider("test-key")

            # Call the method that builds completion_params
            provider._generate_with_responses_endpoint(
                model_name="openai/gpt-5-pro",
                messages=[{"role": "user", "content": "test"}],
                temperature=0.7,
            )

        # store:true is what OpenRouter rejects; store:false is accepted
        self.assertIn("store", captured_params, "OpenRouter requests should send store explicitly")
        self.assertIs(captured_params["store"], False, "OpenRouter requests must not send store=True")

    def test_openai_responses_sends_store_false(self):
        """Test that direct OpenAI provider sends store:false to the responses endpoint.

        **Feature: responses-no-retention, Property 2: Direct OpenAI requests send store:false**
        **Validates: Requirements 1.2, 2.2**

        OpenAI's Responses API stores responses unless told otherwise. zen never reads a
        stored response back, so the provider must opt out explicitly.
        """
        # Capture the completion_params passed to the API
        captured_params = {}

        def capture_create(**kwargs):
            captured_params.update(kwargs)
            # Return a mock response
            mock_response = Mock()
            mock_response.output_text = "Test response"
            mock_response.usage = None
            return mock_response

        mock_client_instance = Mock()
        mock_client_instance.responses.create = capture_create

        with patch.object(
            MockOpenAIProvider, "client", new_callable=lambda: property(lambda self: mock_client_instance)
        ):
            provider = MockOpenAIProvider("test-key")

            # Call the method that builds completion_params
            provider._generate_with_responses_endpoint(
                model_name="gpt-5-pro",
                messages=[{"role": "user", "content": "test"}],
                temperature=0.7,
            )

        # Omitting store would leave OpenAI's default (true) in effect, so it must be explicit
        self.assertIn("store", captured_params, "OpenAI requests should include 'store' parameter")
        self.assertIs(captured_params["store"], False, "OpenAI requests should have store=False")


if __name__ == "__main__":
    unittest.main()
