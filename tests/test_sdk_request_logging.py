"""SDK request bodies (prompts, file contents, base64 media) stay out of zen's logs at LOG_LEVEL=DEBUG.

At DEBUG the openai and anthropic SDKs log every request's full options, so one PDF sent inline would
write megabytes of base64 into logs/mcp_server.log in a single line.
"""

import logging

import pytest


@pytest.mark.parametrize("name", ["openai", "anthropic"])
def test_sdk_loggers_stay_at_info_or_above(name):
    import server  # noqa: F401  (logging is configured when server is imported)

    assert logging.getLogger(name).getEffectiveLevel() >= logging.INFO
