"""Anthropic Claude model provider implementation."""

import logging
import os
from typing import Optional, Dict, Any, List

from anthropic import Anthropic

from .base import (
    ModelCapabilities,
    ModelProvider,
    ModelResponse,
    ProviderType,
    RangeTemperatureConstraint,
)

logger = logging.getLogger(__name__)


class AnthropicProvider(ModelProvider):
    """Anthropic Claude API provider."""

    FRIENDLY_NAME = "Anthropic"

    # Model configurations using ModelCapabilities objects
    SUPPORTED_MODELS = {
        "claude-opus-4-1-20250805": ModelCapabilities(
            provider=ProviderType.ANTHROPIC,
            model_name="claude-opus-4-1-20250805",
            friendly_name="Anthropic (Claude Opus 4.1)",
            context_window=200_000,  # 200K tokens
            max_output_tokens=4_096,  # 4K max output
            supports_extended_thinking=True,
            supports_system_prompts=True,
            supports_streaming=True,
            supports_function_calling=True,
            supports_json_mode=True,
            supports_images=True,
            max_image_size_mb=20.0,
            supports_temperature=True,
            temperature_constraint=RangeTemperatureConstraint(0.0, 1.0, 0.7),
            description="Claude Opus 4.1 - Most capable Claude model with frontier intelligence",
            aliases=["opus-4.1", "claude-opus", "opus", "claude-opus-4.1", "claude-opus-4-1"],
        ),
        "claude-sonnet-4-5-20250929": ModelCapabilities(
            provider=ProviderType.ANTHROPIC,
            model_name="claude-sonnet-4-5-20250929",
            friendly_name="Anthropic (Claude Sonnet 4.5)",
            context_window=200_000,  # 200K tokens, 1M extended option available
            max_output_tokens=64_000,  # 64K max output - significantly increased!
            supports_extended_thinking=True,
            supports_system_prompts=True,
            supports_streaming=True,
            supports_function_calling=True,
            supports_json_mode=True,
            supports_images=True,
            max_image_size_mb=20.0,
            supports_temperature=True,
            temperature_constraint=RangeTemperatureConstraint(0.0, 1.0, 0.7),
            description="Claude Sonnet 4.5 - Most advanced model for autonomous agents and extended coding (released Sept 29, 2025)",
            aliases=["sonnet-4.5", "claude-sonnet-4.5", "claude-sonnet-4-5", "sonnet", "sonnet45"],
        ),
        "claude-sonnet-4-20250514": ModelCapabilities(
            provider=ProviderType.ANTHROPIC,
            model_name="claude-sonnet-4-20250514",
            friendly_name="Anthropic (Claude Sonnet 4)",
            context_window=200_000,  # 200K tokens, 1M in preview
            max_output_tokens=8_192,  # 8K max output
            supports_extended_thinking=True,
            supports_system_prompts=True,
            supports_streaming=True,
            supports_function_calling=True,
            supports_json_mode=True,
            supports_images=True,
            max_image_size_mb=20.0,
            supports_temperature=True,
            temperature_constraint=RangeTemperatureConstraint(0.0, 1.0, 0.7),
            description="Claude Sonnet 4 - Hybrid reasoning model with extended thinking",
            aliases=["sonnet-4", "claude-sonnet-4", "sonnet4", "sonnet"],
        ),
        "claude-3-7-sonnet-20250219": ModelCapabilities(
            provider=ProviderType.ANTHROPIC,
            model_name="claude-3-7-sonnet-20250219",
            friendly_name="Anthropic (Claude 3.7 Sonnet)",
            context_window=200_000,  # 200K tokens
            max_output_tokens=8_192,  # 8K max output
            supports_extended_thinking=True,
            supports_system_prompts=True,
            supports_streaming=True,
            supports_function_calling=True,
            supports_json_mode=True,
            supports_images=True,
            max_image_size_mb=20.0,
            supports_temperature=True,
            temperature_constraint=RangeTemperatureConstraint(0.0, 1.0, 0.7),
            description="Claude 3.7 Sonnet - First hybrid reasoning model generally available",
            aliases=["sonnet-3.7", "claude-3-7-sonnet", "claude-3-7-sonnet-latest"],
        ),
        "claude-3-5-haiku-20241022": ModelCapabilities(
            provider=ProviderType.ANTHROPIC,
            model_name="claude-3-5-haiku-20241022",
            friendly_name="Anthropic (Claude 3.5 Haiku)",
            context_window=200_000,  # 200K tokens
            max_output_tokens=8_192,  # 8K max output
            supports_extended_thinking=False,
            supports_system_prompts=True,
            supports_streaming=True,
            supports_function_calling=True,
            supports_json_mode=True,
            supports_images=False,  # Haiku is text-only
            max_image_size_mb=0.0,
            supports_temperature=True,
            temperature_constraint=RangeTemperatureConstraint(0.0, 1.0, 0.7),
            description="Claude 3.5 Haiku - Fast and cost-effective",
            aliases=["haiku-3.5", "claude-haiku", "haiku", "claude-3.5-haiku", "claude-3-5-haiku-latest"],
        ),
    }

    # Model resolution aliases - map common names to official model names
    MODEL_ALIASES = {
        # Opus 4.1 aliases
        "opus-4.1": "claude-opus-4-1-20250805",
        "claude-opus": "claude-opus-4-1-20250805",
        "opus": "claude-opus-4-1-20250805",
        "claude-opus-4.1": "claude-opus-4-1-20250805",
        "claude-opus-4-1": "claude-opus-4-1-20250805",

        # Sonnet 4.5 aliases (newest - default "sonnet" alias)
        "sonnet-4.5": "claude-sonnet-4-5-20250929",
        "claude-sonnet-4.5": "claude-sonnet-4-5-20250929",
        "claude-sonnet-4-5": "claude-sonnet-4-5-20250929",
        "sonnet45": "claude-sonnet-4-5-20250929",
        "sonnet": "claude-sonnet-4-5-20250929",  # Points to newest Sonnet

        # Sonnet 4 aliases
        "sonnet-4": "claude-sonnet-4-20250514",
        "claude-sonnet-4": "claude-sonnet-4-20250514",
        "sonnet4": "claude-sonnet-4-20250514",

        # Sonnet 3.7 aliases
        "sonnet-3.7": "claude-3-7-sonnet-20250219",
        "claude-3-7-sonnet": "claude-3-7-sonnet-20250219",
        "claude-3-7-sonnet-latest": "claude-3-7-sonnet-20250219",

        # Haiku 3.5 aliases
        "haiku-3.5": "claude-3-5-haiku-20241022",
        "claude-haiku": "claude-3-5-haiku-20241022",
        "haiku": "claude-3-5-haiku-20241022",
        "claude-3.5-haiku": "claude-3-5-haiku-20241022",
        "claude-3-5-haiku": "claude-3-5-haiku-20241022",
        "claude-3-5-haiku-latest": "claude-3-5-haiku-20241022",
    }

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key (or uses ANTHROPIC_API_KEY env var)
            **kwargs: Additional configuration
        """
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Anthropic API key is required. Set ANTHROPIC_API_KEY environment variable.")
        
        super().__init__(api_key=api_key, **kwargs)
        self.client = Anthropic(api_key=api_key)

    def _resolve_model_name(self, model_name: str) -> str:
        """Resolve model aliases to official model names.

        Args:
            model_name: Input model name or alias

        Returns:
            Official model name
        """
        resolved = self.MODEL_ALIASES.get(model_name.lower(), model_name)
        if resolved != model_name:
            logger.info(f"Resolved model alias '{model_name}' to '{resolved}'")
        return resolved

    def get_capabilities(self, model_name: str) -> ModelCapabilities:
        """Get capabilities for a model.

        Args:
            model_name: Name of the model

        Returns:
            ModelCapabilities object
        """
        resolved_name = self._resolve_model_name(model_name)
        
        # Try to get from our configured models
        capabilities = self.SUPPORTED_MODELS.get(resolved_name)
        
        if not capabilities:
            # If not found, create generic capabilities
            logger.warning(f"Model '{resolved_name}' not in configured models, using generic capabilities")
            capabilities = ModelCapabilities(
                provider=ProviderType.ANTHROPIC,
                model_name=resolved_name,
                friendly_name=f"Anthropic ({resolved_name})",
                context_window=200_000,  # Conservative default
                max_output_tokens=4_096,
                supports_extended_thinking=False,
                supports_system_prompts=True,
                supports_streaming=True,
                supports_function_calling=True,
                supports_json_mode=True,
                supports_images=False,
                max_image_size_mb=0.0,
                supports_temperature=True,
                temperature_constraint=RangeTemperatureConstraint(0.0, 1.0, 0.7),
                description=f"Claude model: {resolved_name}",
                aliases=[],
            )
        
        return capabilities

    def list_models(self, respect_restrictions: bool = True) -> List[str]:
        """List available models.

        Args:
            respect_restrictions: Whether to apply provider-specific restriction logic.

        Returns:
            List of model names
        """
        # For now, return all models - restrictions can be added later if needed
        models = list(self.SUPPORTED_MODELS.keys())
        
        # Also include aliases
        for model_name in self.SUPPORTED_MODELS.keys():
            capabilities = self.SUPPORTED_MODELS[model_name]
            if capabilities.aliases:
                models.extend(capabilities.aliases)
        
        return models

    async def generate(
        self,
        prompt: str,
        model_name: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        images: Optional[List[str]] = None,
        **kwargs
    ) -> ModelResponse:
        """Generate a response using Anthropic's API.

        Args:
            prompt: User prompt
            model_name: Model to use
            system_prompt: Optional system prompt
            temperature: Optional temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            images: Optional list of base64-encoded images
            **kwargs: Additional parameters

        Returns:
            ModelResponse with generated text
        """
        resolved_name = self._resolve_model_name(model_name)
        capabilities = self.get_capabilities(resolved_name)
        
        # Prepare messages
        messages = []
        
        # Add user message
        user_content = []
        user_content.append({"type": "text", "text": prompt})
        
        # Add images if provided
        if images and capabilities.supports_images:
            for image_data in images:
                # Anthropic expects image data without the data URL prefix
                if image_data.startswith("data:"):
                    # Extract base64 data from data URL
                    image_data = image_data.split(",", 1)[1]
                
                user_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",  # You might want to detect this
                        "data": image_data
                    }
                })
        
        messages.append({"role": "user", "content": user_content})
        
        # Set parameters
        params = {
            "model": resolved_name,
            "messages": messages,
            "max_tokens": max_tokens or capabilities.max_output_tokens,
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
            if hasattr(response, 'usage'):
                usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                }
            
            return ModelResponse(
                content=text,
                usage=usage,
                model_name=resolved_name,
                friendly_name=self.FRIENDLY_NAME
            )
            
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise

    # Sync wrapper for the async generate method
    def generate_sync(
        self,
        prompt: str,
        model_name: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        images: Optional[List[str]] = None,
        **kwargs
    ) -> ModelResponse:
        """Synchronous wrapper for generate method."""
        import asyncio
        
        # Create new event loop if none exists
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run async method in event loop
        return loop.run_until_complete(
            self.generate(
                prompt=prompt,
                model_name=model_name,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                images=images,
                **kwargs
            )
        )

    def generate_content(
        self,
        prompt: str,
        model_name: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_output_tokens: Optional[int] = None,
        **kwargs,
    ) -> ModelResponse:
        """Generate content using the model (sync version for compatibility)."""
        return self.generate_sync(
            prompt=prompt,
            model_name=model_name,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_output_tokens,
            **kwargs
        )

    def count_tokens(self, text: str, model_name: str) -> int:
        """Count tokens for the given text.
        
        Note: This is an approximation as Anthropic doesn't provide a token counter.
        """
        # Rough approximation: 1 token ≈ 4 characters
        return len(text) // 4

    def get_provider_type(self) -> ProviderType:
        """Get the provider type."""
        return ProviderType.ANTHROPIC

    def validate_model_name(self, model_name: str) -> bool:
        """Validate if the model name is supported by this provider."""
        resolved = self._resolve_model_name(model_name)
        return resolved in self.SUPPORTED_MODELS

    def supports_thinking_mode(self, model_name: str) -> bool:
        """Check if the model supports extended thinking mode."""
        resolved = self._resolve_model_name(model_name)
        capabilities = self.get_capabilities(resolved)
        return capabilities.supports_extended_thinking