"""Anthropic Claude model provider implementation."""

import logging
from typing import ClassVar, Optional

from anthropic import Anthropic

from .base import ModelProvider, ModelResponse
from .registries.anthropic import AnthropicModelRegistry
from .registry_provider_mixin import RegistryBackedProviderMixin
from .shared import ModelCapabilities, ProviderType

logger = logging.getLogger(__name__)


class AnthropicProvider(RegistryBackedProviderMixin, ModelProvider):
    """First-party Anthropic Claude integration built on the official Anthropic SDK.

    Supports extended thinking mode, vision capabilities, and function calling
    across Claude's Opus, Sonnet, and Haiku model families.
    """

    REGISTRY_CLASS = AnthropicModelRegistry
    MODEL_CAPABILITIES: ClassVar[dict[str, ModelCapabilities]] = {}

    def __init__(self, api_key: str, **kwargs):
        """Initialize Anthropic provider with API key.

        Args:
            api_key: Anthropic API key
            **kwargs: Additional configuration
        """
        self._ensure_registry()
        super().__init__(api_key, **kwargs)
        self._client = None
        self._invalidate_capability_cache()

    @property
    def client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            self._client = Anthropic(api_key=self.api_key)
        return self._client

    def generate_content(
        self,
        prompt: str,
        model_name: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_output_tokens: Optional[int] = None,
        images: Optional[list[str]] = None,
        **kwargs,
    ) -> ModelResponse:
        """Generate content using Anthropic's API.

        Args:
            prompt: The main user prompt/query to send to the model
            model_name: Canonical model name or its alias (e.g., "opus", "sonnet")
            system_prompt: Optional system instructions to prepend to the prompt
            temperature: Controls randomness in generation (0.0-1.0), default 0.3
            max_output_tokens: Optional maximum number of tokens to generate
            images: Optional list of image paths or data URLs (for vision models)
            **kwargs: Additional keyword arguments

        Returns:
            ModelResponse: Contains the generated content, token usage, and metadata
        """
        # Validate parameters and fetch capabilities
        self.validate_parameters(model_name, temperature)
        capabilities = self.get_capabilities(model_name)

        resolved_model_name = self._resolve_model_name(model_name)

        # Prepare messages
        messages = []

        # Add user message with text
        user_content = []
        user_content.append({"type": "text", "text": prompt})

        # Add images if provided and model supports vision
        if images and capabilities.supports_images:
            for image_data in images:
                try:
                    # Anthropic expects image data without the data URL prefix
                    if image_data.startswith("data:"):
                        # Extract base64 data from data URL
                        image_data = image_data.split(",", 1)[1]

                    user_content.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",  # Default to PNG
                                "data": image_data,
                            },
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to process image: {e}")
                    continue
        elif images and not capabilities.supports_images:
            logger.warning(f"Model {resolved_model_name} does not support images, ignoring {len(images)} image(s)")

        messages.append({"role": "user", "content": user_content})

        # Set parameters
        params = {
            "model": resolved_model_name,
            "messages": messages,
            "max_tokens": max_output_tokens or capabilities.max_output_tokens,
        }

        if system_prompt:
            params["system"] = system_prompt

        if temperature is not None:
            params["temperature"] = temperature

        try:
            # Make API call
            response = self.client.messages.create(**params)

            # Extract text from response
            text = response.content[0].text if response.content else ""

            # Build usage info
            usage = {}
            if hasattr(response, "usage"):
                usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                }

            return ModelResponse(
                content=text,
                usage=usage,
                model_name=resolved_model_name,
                friendly_name="Anthropic",
                provider=ProviderType.ANTHROPIC,
                metadata={
                    "finish_reason": "stop",
                },
            )

        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise RuntimeError(f"Anthropic API error for model {resolved_model_name}: {e}") from e

    def get_provider_type(self) -> ProviderType:
        """Get the provider type."""
        return ProviderType.ANTHROPIC

    def count_tokens(self, text: str, model_name: str) -> int:
        """Count tokens for the given text.

        Note: This is an approximation as Anthropic doesn't provide a token counter.
        Uses rough estimate of 1 token ≈ 4 characters.

        Args:
            text: Text to count tokens for
            model_name: Model name (not used in approximation)

        Returns:
            Approximate token count
        """
        return len(text) // 4

    def supports_thinking_mode(self, model_name: str) -> bool:
        """Check if the model supports extended thinking mode.

        Args:
            model_name: Name of the model

        Returns:
            True if model supports extended thinking
        """
        capabilities = self.get_capabilities(model_name)
        return capabilities.supports_extended_thinking


# Load registry data at import time for registry consumers
AnthropicProvider._ensure_registry()
