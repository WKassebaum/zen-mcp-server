"""Parser for Grok Build CLI JSON output."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseParser, ParsedCLIResponse, ParserError


class GrokJSONParser(BaseParser):
    """Parse stdout produced by `grok --output-format json`."""

    name = "grok_json"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        if not stdout.strip():
            raise ParserError("Grok CLI returned empty stdout while JSON output was expected")

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive logging
            raise ParserError(f"Failed to decode Grok CLI JSON output: {exc}") from exc

        if not isinstance(payload, dict):
            raise ParserError("Grok CLI returned unexpected JSON payload")

        metadata = self._build_metadata(payload, stderr)

        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            return ParsedCLIResponse(content=text.strip(), metadata=metadata)

        stderr_text = stderr.strip()
        if stderr_text:
            metadata.setdefault("stderr", stderr_text)
            return ParsedCLIResponse(
                content="Grok CLI returned no textual output. Raw stderr was preserved for troubleshooting.",
                metadata=metadata,
            )

        raise ParserError("Grok CLI response did not contain a textual result")

    def _build_metadata(self, payload: dict[str, Any], stderr: str) -> dict[str, Any]:
        metadata: dict[str, Any] = {"raw": payload}

        stop_reason = payload.get("stopReason")
        if isinstance(stop_reason, str) and stop_reason:
            metadata["stop_reason"] = stop_reason

        session_id = payload.get("sessionId")
        if isinstance(session_id, str) and session_id:
            metadata["session_id"] = session_id

        request_id = payload.get("requestId")
        if isinstance(request_id, str) and request_id:
            metadata["request_id"] = request_id

        usage = payload.get("usage")
        if isinstance(usage, dict):
            metadata["usage"] = usage

        model_usage = payload.get("modelUsage")
        if isinstance(model_usage, dict) and model_usage:
            metadata["model_usage"] = model_usage
            metadata["model_used"] = next(iter(model_usage.keys()))

        num_turns = payload.get("num_turns")
        if isinstance(num_turns, int):
            metadata["num_turns"] = num_turns

        stderr_text = stderr.strip()
        if stderr_text:
            metadata.setdefault("stderr", stderr_text)

        return metadata
