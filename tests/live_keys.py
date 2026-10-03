"""API keys for the live probe script (scripts/probe_media_support.py): the environment first, then zen's own
config file (~/.zen/.env).

Only the probe script uses this. Live tests (tests/test_media_live.py) read keys from the environment only, so
`pytest -m integration` never picks up a key the caller did not export.

The value is returned to the caller only. Never print, log or export it.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

ZEN_ENV_FILE = Path.home() / ".zen" / ".env"


def api_key(env_name: str) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value
    if ZEN_ENV_FILE.is_file():
        return dotenv_values(ZEN_ENV_FILE).get(env_name) or None
    return None
