"""Anthropic Claude model provider implementation."""

import base64
import logging
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Optional

if TYPE_CHECKING:
    from tools.models import ToolModelCategory

from anthropic import Anthropic

from utils.image_utils import validate_image
from utils.media import MediaKind, MediaNotSupportedError, format_size

from .base import ModelProvider, ModelResponse
from .registries.anthropic import AnthropicModelRegistry
from .registry_provider_mixin import RegistryBackedProviderMixin
from .shared import ModelCapabilities, ProviderType, usage_count

logger = logging.getLogger(__name__)


class AnthropicProvider(RegistryBackedProviderMixin, ModelProvider):
    """First-party Anthropic Claude integration built on the official Anthropic SDK.

    Supports extended thinking mode, vision capabilities, and function calling
    across Claude's Opus, Sonnet, and Haiku model families.
    """

    REGISTRY_CLASS = AnthropicModelRegistry
    MODEL_CAPABILITIES: ClassVar[dict[str, ModelCapabilities]] = {}
    MEDIA_KINDS = frozenset({MediaKind.PDF})
    # Anthropic limits the whole request body to 32 MB, base64 media included.
    MEDIA_REQUEST_MAX_BYTES = 32_000_000
    # Anthropic documents 1,500-3,000 tokens per PDF page (text plus a page image). Measured 2026-10-03: a near-empty
    # page cost about 1,570 tokens on every Claude model and a letter-size scanned page 1,611 (claude-sonnet-5-5),
    # which leaves about 1,400 tokens for a dense page's text.
    PDF_TOKENS_PER_PAGE = 3_000

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
        media: Optional[list] = None,
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
            media: Optional list of utils.media.MediaAttachment (PDF only), sent inline as base64
                document blocks before the prompt text
            **kwargs: Additional keyword arguments

        Returns:
            ModelResponse: Contains the generated content, token usage, and metadata
        """
        # Fetch capabilities and derive the effective temperature. Adaptive-thinking
        # Claude models (Opus 4.7+, Sonnet 5, Fable 5) reject non-default temperature
        # with a 400 error, so the parameter must be omitted entirely for them.
        capabilities = self.get_capabilities(model_name)
        effective_temperature = capabilities.get_effective_temperature(temperature)
        if effective_temperature is not None:
            self.validate_parameters(model_name, effective_temperature)

        resolved_model_name = self._resolve_model_name(model_name)

        # Prepare messages
        messages = []

        # PDF document blocks first, then the prompt text, then any images. The system prompt stays in
        # params["system"]; media-free requests keep today's layout byte for byte.
        media = list(media) if media else []  # read more than once below; an iterator would be used up
        media_attached: list[dict] = []
        document_blocks: list[dict] = []
        if media:
            self.ensure_media_encodable(media)
            document_blocks, media_attached = self._build_document_blocks(media)

        # Add images if provided and model supports vision
        image_blocks: list[dict] = []
        if images and capabilities.supports_images:
            for image in images:
                try:
                    # Tools pass file paths or data URLs; both resolve to raw bytes and their real MIME type.
                    image_bytes, mime_type = validate_image(image)
                    image_blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": base64.b64encode(image_bytes).decode(),
                            },
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to process image: {e}")
                    continue
        elif images and not capabilities.supports_images:
            logger.warning(f"Model {resolved_model_name} does not support images, ignoring {len(images)} image(s)")

        if document_blocks or image_blocks:
            self._check_request_size(document_blocks, image_blocks, prompt, system_prompt)
        user_content = [*document_blocks, {"type": "text", "text": prompt}, *image_blocks]
        messages.append({"role": "user", "content": user_content})

        # Set parameters
        params = {
            "model": resolved_model_name,
            "messages": messages,
            "max_tokens": max_output_tokens or capabilities.max_output_tokens,
        }

        if system_prompt:
            params["system"] = system_prompt

        if effective_temperature is not None:
            params["temperature"] = effective_temperature

        try:
            # Make API call with streaming to avoid 10-minute timeout limit
            # Anthropic requires streaming for operations that may take longer than 10 minutes
            logger.debug(f"Starting streaming request to Anthropic for model {resolved_model_name}")

            text = ""
            usage = {}
            finish_reason = "stop"

            # Use streaming context manager
            with self.client.messages.stream(**params) as stream:
                # Accumulate text from stream chunks
                for text_chunk in stream.text_stream:
                    text += text_chunk

                # Get final message with usage information
                final_message = stream.get_final_message()

                # Extract usage info from final message
                if hasattr(final_message, "usage"):
                    usage = self._extract_usage(final_message.usage)

                # Extract finish reason
                if hasattr(final_message, "stop_reason") and final_message.stop_reason:
                    finish_reason = final_message.stop_reason

            logger.debug(f"Streaming completed for {resolved_model_name}, received {len(text)} characters")

            metadata = {"finish_reason": finish_reason}
            if media_attached:
                metadata["media_attached"] = media_attached

            return ModelResponse(
                content=text,
                usage=usage,
                model_name=resolved_model_name,
                friendly_name="Anthropic",
                provider=ProviderType.ANTHROPIC,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise RuntimeError(f"Anthropic API error for model {resolved_model_name}: {e}") from e

    @staticmethod
    def _extract_usage(usage) -> dict[str, int]:
        """Token counts from a Messages API ``usage``.

        ``input_tokens`` counts uncached input only. Prompt-cache reads are recorded as ``cached_input_tokens`` and
        cache writes as ``cache_write_input_tokens``, each only when the API reports it.
        """
        counts = {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.input_tokens + usage.output_tokens,
        }
        for field_name, key in (
            ("cache_read_input_tokens", "cached_input_tokens"),
            ("cache_creation_input_tokens", "cache_write_input_tokens"),
        ):
            value = usage_count(getattr(usage, field_name, None))
            if value is not None:
                counts[key] = value
        return counts

    def _build_document_blocks(self, media) -> tuple[list[dict], list[dict]]:
        """Base64 document blocks in input order, and the media_attached records for the response metadata.

        Bytes are read from ``source_path`` (resolved and validated), never from the caller's ``path``.
        """
        blocks: list[dict] = []
        attached: list[dict] = []
        for attachment in media:
            data = base64.b64encode(Path(attachment.source_path).read_bytes()).decode()
            blocks.append(
                {"type": "document", "source": {"type": "base64", "media_type": attachment.mime_type, "data": data}}
            )
            attached.append(
                {
                    "name": attachment.name,
                    "kind": attachment.kind.value,
                    "bytes": attachment.size_bytes,
                    "transport": "inline",
                }
            )
        return blocks, attached

    def _check_request_size(
        self, document_blocks: list[dict], image_blocks: list[dict], prompt: str, system_prompt: Optional[str]
    ) -> None:
        """Fail before sending rather than surface an HTTP 413: the 32 MB limit covers the whole body.

        The base64 data of PDF and image blocks counts, along with the prompt and system prompt.
        """
        total = sum(len(block["source"]["data"]) for block in (*document_blocks, *image_blocks))
        total += len(prompt.encode()) + len((system_prompt or "").encode())
        if total > self.MEDIA_REQUEST_MAX_BYTES:
            carried = " and ".join(
                name for name, blocks in (("PDFs", document_blocks), ("images", image_blocks)) if blocks
            )
            raise MediaNotSupportedError(
                f"anthropic requests are limited to {format_size(self.MEDIA_REQUEST_MAX_BYTES)}; this one would be "
                f"{format_size(total)} with its {carried} base64-encoded. Gemini models take larger media."
            )

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

    def get_preferred_model(self, category: "ToolModelCategory", allowed_models: list[str]) -> Optional[str]:
        """Get Anthropic's preferred model for a given category from allowed models."""
        from tools.models import ToolModelCategory

        if not allowed_models:
            return None

        def find_first(preferences: list[str]) -> Optional[str]:
            for model in preferences:
                if model in allowed_models:
                    return model
            return None

        if category == ToolModelCategory.EXTENDED_REASONING:
            # Fable 5.1 is the current Mythos-class frontier model for deep reasoning.
            return (
                find_first(
                    [
                        "claude-fable-5-1",
                        "claude-fable-5",
                        "claude-opus-5-5",
                        "claude-sonnet-5-5",
                        "claude-opus-5",
                        "claude-opus-4-8",
                        "claude-opus-4-7",
                        "claude-opus-4-6",
                        "claude-sonnet-5",
                        "claude-sonnet-4-6",
                    ]
                )
                or allowed_models[0]
            )

        elif category == ToolModelCategory.FAST_RESPONSE:
            # Haiku is purpose-built for speed; Sonnet 5.5 is the fast capable fallback (30%+ faster than Sonnet 5).
            preferred = find_first(
                [
                    "claude-haiku-4-5-20251001",
                    "claude-sonnet-5-5",
                    "claude-sonnet-4-6",
                ]
            )
            if preferred:
                return preferred
            # No allowed model is on the list: take the lowest-ranked one (allowed_models[0] is the most capable).
            return self.pick_fast_by_rank(allowed_models) or allowed_models[0]

        else:  # BALANCED
            # Sonnet 5.5 roughly matches Opus 5.5 (GDPval-AA 1844 vs 1846) at half the price ($2/$10).
            return (
                find_first(
                    [
                        "claude-sonnet-5-5",
                        "claude-opus-5-5",
                        "claude-opus-5",
                        "claude-opus-4-8",
                        "claude-fable-5-1",
                        "claude-fable-5",
                        "claude-opus-4-7",
                        "claude-sonnet-5",
                        "claude-sonnet-4-6",
                    ]
                )
                or allowed_models[0]
            )

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
