"""Gemini model provider implementation."""

import base64
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Optional

if TYPE_CHECKING:
    from tools.models import ToolModelCategory

from google import genai
from google.genai import types

from utils import media_upload_cache
from utils.env import get_env
from utils.image_utils import validate_image
from utils.media import MediaKind

from .base import ModelProvider
from .registries.gemini import GeminiModelRegistry
from .registry_provider_mixin import RegistryBackedProviderMixin
from .shared import ModelCapabilities, ModelResponse, ProviderType

logger = logging.getLogger(__name__)


class GeminiModelProvider(RegistryBackedProviderMixin, ModelProvider):
    """First-party Gemini integration built on the official Google SDK.

    The provider advertises detailed thinking-mode budgets, handles optional
    custom endpoints, and performs image pre-processing before forwarding a
    request to the Gemini APIs.
    """

    REGISTRY_CLASS = GeminiModelRegistry
    MODEL_CAPABILITIES: ClassVar[dict[str, ModelCapabilities]] = {}

    # Thinking mode configurations - percentages of model's max_thinking_tokens
    # These percentages work across all models that support thinking
    THINKING_BUDGETS = {
        "minimal": 0.005,  # 0.5% of max - minimal thinking for fast responses
        "low": 0.08,  # 8% of max - light reasoning tasks
        "medium": 0.33,  # 33% of max - balanced reasoning (default)
        "high": 0.67,  # 67% of max - complex analysis
        "max": 1.0,  # 100% of max - full thinking budget
    }

    MEDIA_KINDS = frozenset(MediaKind)
    # Gemini caps a request at 100 MB; base64 inflates by 4/3 (60 MB -> 80 MB) and the prompt text and
    # inline images need the rest, so keep raw inline media under 60 MB and upload the rest to the Files API.
    INLINE_MEDIA_MAX_BYTES = 60_000_000
    UPLOAD_POLL_INTERVAL_S = 5
    UPLOAD_TIMEOUT_S = 600

    # Model-specific thinking token limits (fallback when registry omits max_thinking_tokens)
    MAX_THINKING_TOKENS = {
        "gemini-2.5-flash": 24576,  # Flash 2.5 thinking budget limit
        "gemini-2.5-pro": 32768,  # Pro 2.5 thinking budget limit
        "gemini-3.1-pro-preview": 32768,
        "gemini-3.5-flash": 32768,
        "gemini-3.5-flash-lite": 24576,
        "gemini-3.6-flash": 32768,
        "gemini-3.7-flash": 32768,
        "gemini-3.8-flash": 32768,
        "gemini-3-flash-preview": 32768,
    }

    def __init__(self, api_key: str, **kwargs):
        """Initialize Gemini provider with API key and optional base URL."""
        self._ensure_registry()
        super().__init__(api_key, **kwargs)
        self._client = None
        self._token_counters = {}  # Cache for token counting
        self._base_url = kwargs.get("base_url", None)  # Optional custom endpoint
        self._timeout_override = self._resolve_http_timeout()
        self._invalidate_capability_cache()

    # ------------------------------------------------------------------
    # Capability surface
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Client access
    # ------------------------------------------------------------------

    @property
    def client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            http_options_kwargs: dict[str, object] = {}
            if self._base_url:
                http_options_kwargs["base_url"] = self._base_url
            if self._timeout_override is not None:
                http_options_kwargs["timeout"] = self._timeout_override

            if http_options_kwargs:
                http_options = types.HttpOptions(**http_options_kwargs)
                logger.debug(
                    "Initializing Gemini client with options: base_url=%s timeout=%s",
                    http_options_kwargs.get("base_url"),
                    http_options_kwargs.get("timeout"),
                )
                self._client = genai.Client(api_key=self.api_key, http_options=http_options)
            else:
                self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _resolve_http_timeout(self) -> Optional[float]:
        """Compute timeout override from shared custom timeout environment variables."""

        timeouts: list[float] = []
        for env_var in [
            "CUSTOM_CONNECT_TIMEOUT",
            "CUSTOM_READ_TIMEOUT",
            "CUSTOM_WRITE_TIMEOUT",
            "CUSTOM_POOL_TIMEOUT",
        ]:
            raw_value = get_env(env_var)
            if raw_value:
                try:
                    timeouts.append(float(raw_value))
                except (TypeError, ValueError):
                    logger.warning("Invalid %s value '%s'; ignoring.", env_var, raw_value)

        if timeouts:
            # Use the largest timeout to best approximate long-running requests
            resolved = max(timeouts)
            logger.debug("Using custom Gemini HTTP timeout: %ss", resolved)
            return resolved

        return None

    # ------------------------------------------------------------------
    # Request execution
    # ------------------------------------------------------------------

    def generate_content(
        self,
        prompt: str,
        model_name: str,
        system_prompt: Optional[str] = None,
        temperature: float = 1.0,
        max_output_tokens: Optional[int] = None,
        thinking_mode: str = "medium",
        images: Optional[list[str]] = None,
        media: Optional[list] = None,
        **kwargs,
    ) -> ModelResponse:
        """
        Generate content using Gemini model.

        Args:
            prompt: The main user prompt/query to send to the model
            model_name: Canonical model name or its alias (e.g., "gemini-2.5-pro", "flash", "pro")
            system_prompt: Optional system instructions to prepend to the prompt for context/behavior
            temperature: Controls randomness in generation (0.0=deterministic, 1.0=creative), default 0.3
            max_output_tokens: Optional maximum number of tokens to generate in the response
            thinking_mode: Thinking budget level for models that support it ("minimal", "low", "medium", "high", "max"), default "medium"
            images: Optional list of image paths or data URLs to include with the prompt (for vision models)
            media: Optional list of utils.media.MediaAttachment (PDF, audio, video), sent as native parts
                before the prompt text; files that do not fit inline are uploaded to the Files API
            **kwargs: Additional keyword arguments (reserved for future use)

        Returns:
            ModelResponse: Contains the generated content, token usage stats, model metadata, and safety information
        """
        # Validate parameters and fetch capabilities
        self.validate_parameters(model_name, temperature)
        capabilities = self.get_capabilities(model_name)
        capability_map = self.get_all_model_capabilities()

        resolved_model_name = self._resolve_model_name(model_name)

        # Prepare content parts (text and potentially images)
        parts = []

        # Media first, then the prompt text. With media the system prompt goes to system_instruction
        # (a stable prefix); media-free requests keep today's layout byte for byte.
        media = list(media) if media else []  # read more than once below; an iterator would be used up
        media_attached: list[dict] = []
        if media:
            self.ensure_media_encodable(media)
            media_parts, media_attached = self._build_media_parts(media)
            parts.extend(media_parts)
            parts.append({"text": prompt})
        else:
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            parts.append({"text": full_prompt})

        # Add images if provided and model supports vision
        if images and capabilities.supports_images:
            for image_path in images:
                try:
                    image_part = self._process_image(image_path)
                    if image_part:
                        parts.append(image_part)
                except Exception as e:
                    logger.warning(f"Failed to process image {image_path}: {e}")
                    # Continue with other images and text
                    continue
        elif images and not capabilities.supports_images:
            logger.warning(f"Model {resolved_model_name} does not support images, ignoring {len(images)} image(s)")

        # Create contents structure
        contents = [{"parts": parts}]

        effective_thinking_mode = thinking_mode

        # Prepare generation config
        generation_config = types.GenerateContentConfig(
            temperature=temperature,
            candidate_count=1,
        )

        if media and system_prompt:
            generation_config.system_instruction = system_prompt

        # Add max output tokens if specified
        if max_output_tokens:
            generation_config.max_output_tokens = max_output_tokens

        # Add thinking configuration for models that support it
        if capabilities.supports_extended_thinking and effective_thinking_mode in self.THINKING_BUDGETS:
            # Get model's max thinking tokens and calculate actual budget
            model_config = capability_map.get(resolved_model_name)
            if model_config and model_config.max_thinking_tokens > 0:
                max_thinking_tokens = model_config.max_thinking_tokens
                actual_thinking_budget = int(max_thinking_tokens * self.THINKING_BUDGETS[effective_thinking_mode])
                generation_config.thinking_config = types.ThinkingConfig(thinking_budget=actual_thinking_budget)

        # Retry logic with progressive delays
        max_retries = 4  # Total of 4 attempts
        retry_delays = [1, 3, 5, 8]  # Progressive delays: 1s, 3s, 5s, 8s
        attempt_counter = {"value": 0}

        def _attempt() -> ModelResponse:
            attempt_counter["value"] += 1
            response = self.client.models.generate_content(
                model=resolved_model_name,
                contents=contents,
                config=generation_config,
            )

            usage = self._extract_usage(response)

            finish_reason_str = "UNKNOWN"
            is_blocked_by_safety = False
            safety_feedback_details = None

            if response.candidates:
                candidate = response.candidates[0]

                try:
                    finish_reason_enum = candidate.finish_reason
                    if finish_reason_enum:
                        try:
                            finish_reason_str = finish_reason_enum.name
                        except AttributeError:
                            finish_reason_str = str(finish_reason_enum)
                    else:
                        finish_reason_str = "STOP"
                except AttributeError:
                    finish_reason_str = "STOP"

                if not response.text:
                    try:
                        safety_ratings = candidate.safety_ratings
                        if safety_ratings:
                            for rating in safety_ratings:
                                try:
                                    if rating.blocked:
                                        is_blocked_by_safety = True
                                        category_name = "UNKNOWN"
                                        probability_name = "UNKNOWN"

                                        try:
                                            category_name = rating.category.name
                                        except (AttributeError, TypeError):
                                            pass

                                        try:
                                            probability_name = rating.probability.name
                                        except (AttributeError, TypeError):
                                            pass

                                        safety_feedback_details = (
                                            f"Category: {category_name}, Probability: {probability_name}"
                                        )
                                        break
                                except (AttributeError, TypeError):
                                    continue
                    except (AttributeError, TypeError):
                        pass

            elif response.candidates is not None and len(response.candidates) == 0:
                is_blocked_by_safety = True
                finish_reason_str = "SAFETY"
                safety_feedback_details = "Prompt blocked, reason unavailable"

                try:
                    prompt_feedback = response.prompt_feedback
                    if prompt_feedback and prompt_feedback.block_reason:
                        try:
                            block_reason_name = prompt_feedback.block_reason.name
                        except AttributeError:
                            block_reason_name = str(prompt_feedback.block_reason)
                        safety_feedback_details = f"Prompt blocked, reason: {block_reason_name}"
                except (AttributeError, TypeError):
                    pass

            return ModelResponse(
                content=response.text,
                usage=usage,
                model_name=resolved_model_name,
                friendly_name="Gemini",
                provider=ProviderType.GOOGLE,
                metadata={
                    "thinking_mode": effective_thinking_mode if capabilities.supports_extended_thinking else None,
                    "finish_reason": finish_reason_str,
                    "is_blocked_by_safety": is_blocked_by_safety,
                    "safety_feedback": safety_feedback_details,
                    "media_attached": media_attached,
                },
            )

        try:
            return self._run_with_retries(
                operation=_attempt,
                max_attempts=max_retries,
                delays=retry_delays,
                log_prefix=f"Gemini API ({resolved_model_name})",
            )
        except Exception as exc:
            attempts = max(attempt_counter["value"], 1)
            error_msg = (
                f"Gemini API error for model {resolved_model_name} after {attempts} attempt"
                f"{'s' if attempts > 1 else ''}: {exc}"
            )
            raise RuntimeError(error_msg) from exc

    def get_provider_type(self) -> ProviderType:
        """Get the provider type."""
        return ProviderType.GOOGLE

    def _extract_usage(self, response) -> dict[str, int]:
        """Extract token usage from Gemini response."""
        usage = {}

        # Try to extract usage metadata from response
        # Note: The actual structure depends on the SDK version and response format
        try:
            metadata = response.usage_metadata
            if metadata:
                # Extract token counts with explicit None checks
                input_tokens = None
                output_tokens = None

                try:
                    value = metadata.prompt_token_count
                    if value is not None:
                        input_tokens = value
                        usage["input_tokens"] = value
                except (AttributeError, TypeError):
                    pass

                try:
                    value = metadata.candidates_token_count
                    if value is not None:
                        output_tokens = value
                        usage["output_tokens"] = value
                except (AttributeError, TypeError):
                    pass

                # Calculate total only if both values are available and valid
                if input_tokens is not None and output_tokens is not None:
                    usage["total_tokens"] = input_tokens + output_tokens
        except (AttributeError, TypeError):
            # response doesn't have usage_metadata
            pass

        return usage

    def _is_error_retryable(self, error: Exception) -> bool:
        """Determine if an error should be retried based on structured error codes.

        Uses Gemini API error structure instead of text pattern matching for reliability.

        Args:
            error: Exception from Gemini API call

        Returns:
            True if error should be retried, False otherwise
        """
        error_str = str(error).lower()

        # Check for 429 errors first - these need special handling
        if "429" in error_str or "quota" in error_str or "resource_exhausted" in error_str:
            # For Gemini, check for specific non-retryable error indicators
            # These typically indicate permanent failures or quota/size limits
            non_retryable_indicators = [
                "quota exceeded",
                "resource exhausted",
                "context length",
                "token limit",
                "request too large",
                "invalid request",
                "quota_exceeded",
                "resource_exhausted",
            ]

            # Also check if this is a structured error from Gemini SDK
            try:
                # Try to access error details if available
                error_details = None
                try:
                    error_details = error.details
                except AttributeError:
                    try:
                        error_details = error.reason
                    except AttributeError:
                        pass

                if error_details:
                    error_details_str = str(error_details).lower()
                    # Check for non-retryable error codes/reasons
                    if any(indicator in error_details_str for indicator in non_retryable_indicators):
                        logger.debug(f"Non-retryable Gemini error: {error_details}")
                        return False
            except Exception:
                pass

            # Check main error string for non-retryable patterns
            if any(indicator in error_str for indicator in non_retryable_indicators):
                logger.debug(f"Non-retryable Gemini error based on message: {error_str[:200]}...")
                return False

            # If it's a 429/quota error but doesn't match non-retryable patterns, it might be retryable rate limiting
            logger.debug(f"Retryable Gemini rate limiting error: {error_str[:100]}...")
            return True

        # For non-429 errors, check if they're retryable
        retryable_indicators = [
            "timeout",
            "connection",
            "network",
            "temporary",
            "unavailable",
            "retry",
            "internal error",
            "408",  # Request timeout
            "500",  # Internal server error
            "502",  # Bad gateway
            "503",  # Service unavailable
            "504",  # Gateway timeout
            "ssl",  # SSL errors
            "handshake",  # Handshake failures
        ]

        return any(indicator in error_str for indicator in retryable_indicators)

    def _upload_media(self, attachment):
        """Upload one attachment to the Gemini Files API and wait until it is ACTIVE.

        zen never deletes uploads: Google deletes them after 48 hours. The Files API name is recorded
        in the response metadata (media_attached[*]["file_name"]) so a user can delete one sooner.
        Callers go through _remote_media, which reuses an earlier upload of the same bytes when it can.
        """
        try:
            uploaded = self.client.files.upload(
                file=attachment.source_path,
                config={"mime_type": attachment.mime_type, "display_name": attachment.name},
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini Files API upload of {attachment.name} failed: {exc}") from exc
        deadline = time.monotonic() + self.UPLOAD_TIMEOUT_S
        while uploaded.state is not None and uploaded.state.name == "PROCESSING":
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"Gemini Files API: {attachment.name} still PROCESSING after {self.UPLOAD_TIMEOUT_S}s "
                    f"(uploaded as {uploaded.name})"
                )
            time.sleep(self.UPLOAD_POLL_INTERVAL_S)
            uploaded = self.client.files.get(name=uploaded.name)
        if uploaded.state is not None and uploaded.state.name == "FAILED":
            detail = f": {uploaded.error.message}" if getattr(uploaded.error, "message", None) else ""
            raise RuntimeError(f"Gemini Files API upload of {attachment.name} ended in state FAILED{detail}")
        if not uploaded.uri:
            raise RuntimeError(f"Gemini Files API upload of {attachment.name} returned no URI ({uploaded.name})")
        return uploaded

    def _remote_media(self, attachment, this_request: dict[str, dict]) -> tuple[dict, str]:
        """Files API reference ``{"name", "uri", "mime_type"}`` for an attachment, and how it got there.

        Reused when possible ("cached"): an upload of the same bytes made earlier in this request, else one in the
        upload cache made with this API key and still ACTIVE on Google's side. Otherwise uploaded ("uploaded") and
        cached, so follow-ups, other consensus models and tool-level retries reuse it (utils.media_upload_cache).
        """
        try:
            key = media_upload_cache.content_key(attachment.source_path, attachment.mime_type)
        except OSError as exc:
            logger.warning("Upload cache skipped for %s: cannot read it (%s)", attachment.name, exc)
            key = None
        if key is not None and key in this_request:
            return this_request[key], "cached"

        fingerprint = media_upload_cache.api_key_fingerprint(self.api_key)
        if key is not None:
            cached = media_upload_cache.lookup(key, fingerprint)
            if cached is not None:
                if self._upload_still_usable(cached):
                    logger.info("Gemini Files API: reusing %s for %s", cached["file_name"], attachment.name)
                    remote = {"name": cached["file_name"], "uri": cached["file_uri"], "mime_type": cached["mime_type"]}
                    this_request[key] = remote
                    return remote, "cached"
                media_upload_cache.evict(key)

        uploaded = self._upload_media(attachment)
        remote = {"name": uploaded.name, "uri": uploaded.uri, "mime_type": uploaded.mime_type or attachment.mime_type}
        if key is not None:
            media_upload_cache.store(
                key,
                fingerprint,
                file_name=remote["name"],
                file_uri=remote["uri"],
                mime_type=remote["mime_type"],
                size_bytes=attachment.size_bytes,
            )
            this_request[key] = remote
        return remote, "uploaded"

    def _upload_still_usable(self, cached: dict) -> bool:
        """True when Google still has the cached upload, ACTIVE and at the same URI."""
        try:
            remote = self.client.files.get(name=cached["file_name"])
        except Exception as exc:  # 404 once Google has deleted it, 403 for another project's file, ...
            logger.info(
                "Gemini Files API: cached upload %s is unusable (%s); uploading again", cached["file_name"], exc
            )
            return False
        state = getattr(getattr(remote, "state", None), "name", None)
        if state == "ACTIVE" and getattr(remote, "uri", None) == cached["file_uri"]:
            return True
        logger.info("Gemini Files API: cached upload %s is %s; uploading again", cached["file_name"], state)
        return False

    def _build_media_parts(self, media) -> tuple[list[dict], list[dict]]:
        """Inline what fits under INLINE_MEDIA_MAX_BYTES (largest files upload first); keep input order.

        Uploads happen here, before the retry loop in generate_content, so a retried request reuses them; the
        upload cache lets later requests (follow-ups, consensus models, tool-level retries) reuse them too.
        """
        inline_total = sum(attachment.size_bytes for attachment in media)
        to_upload: set[int] = set()
        for index, attachment in sorted(enumerate(media), key=lambda item: item[1].size_bytes, reverse=True):
            if inline_total <= self.INLINE_MEDIA_MAX_BYTES:
                break
            to_upload.add(index)
            inline_total -= attachment.size_bytes

        parts: list[dict] = []
        attached: list[dict] = []
        this_request: dict[str, dict] = {}
        for index, attachment in enumerate(media):
            record = {"name": attachment.name, "kind": attachment.kind.value, "bytes": attachment.size_bytes}
            if index in to_upload:
                remote, transport = self._remote_media(attachment, this_request)
                parts.append({"file_data": {"file_uri": remote["uri"], "mime_type": remote["mime_type"]}})
                record.update(transport=transport, file_name=remote["name"])
            else:
                data = base64.b64encode(Path(attachment.source_path).read_bytes()).decode()
                parts.append({"inline_data": {"mime_type": attachment.mime_type, "data": data}})
                record["transport"] = "inline"
            attached.append(record)
        return parts, attached

    def _process_image(self, image_path: str) -> Optional[dict]:
        """Process an image for Gemini API."""
        try:
            # Use base class validation
            image_bytes, mime_type = validate_image(image_path)

            # For data URLs, extract the base64 data directly
            if image_path.startswith("data:"):
                # Extract base64 data from data URL
                _, data = image_path.split(",", 1)
                return {"inline_data": {"mime_type": mime_type, "data": data}}
            else:
                # For file paths, encode the bytes
                image_data = base64.b64encode(image_bytes).decode()
                return {"inline_data": {"mime_type": mime_type, "data": image_data}}

        except ValueError as e:
            logger.warning(str(e))
            return None
        except Exception as e:
            logger.error(f"Error processing image {image_path}: {e}")
            return None

    def get_preferred_model(self, category: "ToolModelCategory", allowed_models: list[str]) -> Optional[str]:
        """Get Gemini's preferred model for a given category from allowed models.

        Args:
            category: The tool category requiring a model
            allowed_models: Pre-filtered list of models allowed by restrictions

        Returns:
            Preferred model name or None
        """
        from tools.models import ToolModelCategory

        if not allowed_models:
            return None

        capability_map = self.get_all_model_capabilities()

        # Helper to find best model from candidates
        def find_best(candidates: list[str]) -> Optional[str]:
            """Return the canonical name of the highest-scored candidate; on a tie, the name that sorts last (newer).

            allowed_models mixes canonical names and aliases, so each candidate is resolved first: string
            order alone ranked gemini-3.5-flash-lite above gemini-3.5-flash. Callers resolve the returned
            name again, and a canonical name passes an alias-only allow-list.
            """
            scores: dict[str, int] = {}
            for candidate in candidates:
                canonical = self._resolve_model_name(candidate)
                if canonical in capability_map:
                    scores[canonical] = capability_map[canonical].intelligence_score
            return max(scores, key=lambda name: (scores[name], name)) if scores else None

        if category == ToolModelCategory.EXTENDED_REASONING:
            # For extended reasoning, prefer models with thinking support
            # Prefer Gemini 3.1 Pro Preview first (highest intelligence)
            if "gemini-3.1-pro-preview" in allowed_models:
                return "gemini-3.1-pro-preview"

            # Then try other Pro models that support thinking
            pro_thinking = [
                m
                for m in allowed_models
                if "pro" in m and m in capability_map and capability_map[m].supports_extended_thinking
            ]
            if pro_thinking:
                return find_best(pro_thinking)

            # Then any model that supports thinking
            any_thinking = [
                m for m in allowed_models if m in capability_map and capability_map[m].supports_extended_thinking
            ]
            if any_thinking:
                return find_best(any_thinking)

            # Finally, just prefer Pro models even without thinking
            pro_models = [m for m in allowed_models if "pro" in m]
            if pro_models:
                return find_best(pro_models)

        elif category == ToolModelCategory.FAST_RESPONSE:
            # Prefer latest Flash for speed/cost (3.8 > 3.7 > 3.6 > 3.5 > older)
            for preferred in (
                "gemini-3.8-flash",
                "gemini3.8-flash",
                "flash",
                "gemini-3.7-flash",
                "gemini3.7-flash",
                "gemini-3.6-flash",
                "gemini3.6-flash",
                "gemini-3.5-flash",
                "gemini3.5-flash",
            ):
                if preferred in allowed_models:
                    return preferred
            flash_models = [m for m in allowed_models if "flash" in m]
            if flash_models:
                return find_best(flash_models)

        # Default for BALANCED or as fallback
        # Prefer latest Pro model for balanced use (best overall capabilities)
        if "gemini-3.1-pro-preview" in allowed_models:
            return "gemini-3.1-pro-preview"

        # Then Flash for speed, then other Pro models, then anything
        flash_models = [m for m in allowed_models if "flash" in m]
        if flash_models:
            return find_best(flash_models)

        pro_models = [m for m in allowed_models if "pro" in m]
        if pro_models:
            return find_best(pro_models)

        # Ultimate fallback to best available model
        return find_best(allowed_models)


# Load registry data at import time for registry consumers
GeminiModelProvider._ensure_registry()
