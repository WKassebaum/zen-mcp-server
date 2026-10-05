"""Dataclass used to normalise provider SDK responses."""

from dataclasses import dataclass, field
from typing import Any, Optional

from .provider_type import ProviderType

__all__ = ["ModelResponse", "usage_count"]


def usage_count(value: Any) -> Optional[int]:
    """``value`` when it is a real token count (a non-negative int, not a bool), else None.

    Usage fields an endpoint does not report are None, and tests often build usage from Mock objects whose
    attributes are mocks: neither is a count, so the caller leaves the key out instead of inventing a 0.
    """
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


@dataclass
class ModelResponse:
    """Portable representation of a provider completion.

    ``usage`` holds ``input_tokens``, ``output_tokens`` and ``total_tokens``, plus ``cached_input_tokens`` (input
    served from the provider's prompt cache) and, for Claude, ``cache_write_input_tokens`` when the endpoint reports
    them. A count the endpoint does not report is absent, never 0.
    """

    content: str
    usage: dict[str, int] = field(default_factory=dict)
    model_name: str = ""
    friendly_name: str = ""
    provider: ProviderType = ProviderType.GOOGLE
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        """Return the total token count if the provider reported usage data."""

        return self.usage.get("total_tokens", 0)
