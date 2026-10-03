"""tests/live_keys.py: the environment first, then zen's config file, else None.

Every test points ZEN_ENV_FILE at tmp_path and uses a made-up variable name, so the real
~/.zen/.env and real keys are never read.
"""

import pytest

from tests import live_keys

NAME = "ZEN_LIVE_KEYS_TEST_KEY"


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    monkeypatch.setattr(live_keys, "ZEN_ENV_FILE", path)
    monkeypatch.delenv(NAME, raising=False)
    return path


def test_environment_wins_over_the_config_file(env_file, monkeypatch):
    env_file.write_text(f"{NAME}=from-file\n")
    monkeypatch.setenv(NAME, "from-env")
    assert live_keys.api_key(NAME) == "from-env"


def test_config_file_is_used_when_the_environment_lacks_the_key(env_file):
    env_file.write_text(f"OTHER=x\n{NAME}=from-file\n")
    assert live_keys.api_key(NAME) == "from-file"


def test_empty_environment_value_falls_back_to_the_config_file(env_file, monkeypatch):
    env_file.write_text(f"{NAME}=from-file\n")
    monkeypatch.setenv(NAME, "")
    assert live_keys.api_key(NAME) == "from-file"


@pytest.mark.parametrize("content", [None, "OTHER=x\n", f"{NAME}=\n", f"{NAME}\n"])
def test_missing_or_empty_everywhere_is_none(env_file, content):
    if content is not None:
        env_file.write_text(content)
    assert live_keys.api_key(NAME) is None
