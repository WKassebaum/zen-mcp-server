"""Tests for the Grok Build CLI JSON parser."""

import pytest

from clink.parsers.base import ParserError
from clink.parsers.grok import GrokJSONParser


def _build_success_payload() -> str:
    return (
        '{"text":"OK","stopReason":"EndTurn","sessionId":"019f5836-cd2a-7cc0","requestId":"b854400e",'
        '"thought":"Simple instruction.","usage":{"input_tokens":40056,"output_tokens":37,"total_tokens":42397},'
        '"num_turns":1,"modelUsage":{"grok-4.5":{"inputTokens":40056,"outputTokens":37,"modelCalls":1}}}'
    )


def test_grok_parser_extracts_text_and_metadata():
    parser = GrokJSONParser()

    parsed = parser.parse(stdout=_build_success_payload(), stderr="")

    assert parsed.content == "OK"
    assert parsed.metadata["stop_reason"] == "EndTurn"
    assert parsed.metadata["session_id"] == "019f5836-cd2a-7cc0"
    assert parsed.metadata["request_id"] == "b854400e"
    assert parsed.metadata["usage"]["output_tokens"] == 37
    assert parsed.metadata["model_used"] == "grok-4.5"
    assert parsed.metadata["num_turns"] == 1


def test_grok_parser_falls_back_to_stderr_when_text_missing():
    parser = GrokJSONParser()

    parsed = parser.parse(stdout='{"stopReason":"Error"}', stderr="something went wrong")

    assert "no textual output" in parsed.content
    assert parsed.metadata["stop_reason"] == "Error"
    assert parsed.metadata["stderr"] == "something went wrong"


def test_grok_parser_requires_output():
    parser = GrokJSONParser()

    with pytest.raises(ParserError):
        parser.parse(stdout="", stderr="")


def test_grok_parser_rejects_non_object_payload():
    parser = GrokJSONParser()

    with pytest.raises(ParserError):
        parser.parse(stdout='["not","a","dict"]', stderr="")


def test_grok_parser_rejects_text_free_payload_without_stderr():
    parser = GrokJSONParser()

    with pytest.raises(ParserError):
        parser.parse(stdout='{"stopReason":"EndTurn"}', stderr="")
