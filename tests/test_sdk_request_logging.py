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


SDK_LOGGERS = ("openai", "anthropic")


@pytest.fixture
def restore_sdk_logger_levels():
    saved = {name: logging.getLogger(name).level for name in SDK_LOGGERS}
    yield
    for name, level in saved.items():
        logging.getLogger(name).setLevel(level)


@pytest.mark.parametrize(
    "root_level,expected",
    [
        (logging.DEBUG, logging.INFO),  # zen at DEBUG: the SDKs must not log request bodies
        (logging.INFO, logging.INFO),
        (logging.WARNING, logging.WARNING),  # never louder than zen itself
    ],
)
def test_quiet_sdk_request_logging(restore_sdk_logger_levels, root_level, expected):
    from server import quiet_sdk_request_logging

    for name in SDK_LOGGERS:
        logging.getLogger(name).setLevel(logging.NOTSET)
    quiet_sdk_request_logging(root_level)
    assert [logging.getLogger(name).level for name in SDK_LOGGERS] == [expected, expected]
