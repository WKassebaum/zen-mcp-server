"""The CLI loads ~/.zen/.env at import unless ZEN_NO_USER_ENV opts out (tests/conftest.py sets it).

The import-time cases import zen_cli.main in a fresh interpreter whose HOME is a temporary directory, so the load
runs for real and the developer's own ~/.zen/.env is never read. The child gets no API keys.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from zen_cli.main import _user_env_opted_out

ROOT = Path(__file__).resolve().parent.parent
MARKER = "ZEN_TEST_USER_ENV_MARKER"


def _marker_after_import(home: Path, opt_out: str | None) -> str:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        # This checkout's CLI, ahead of any editable install that points at another checkout
        "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT)]),
    }
    if opt_out is not None:
        env["ZEN_NO_USER_ENV"] = opt_out
    code = f"import os, zen_cli.main; print(os.environ.get({MARKER!r}))"
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1]


@pytest.fixture
def home(tmp_path):
    (tmp_path / ".zen").mkdir()
    (tmp_path / ".zen" / ".env").write_text(f"{MARKER}=from-user-env\n")
    return tmp_path


def test_user_env_is_loaded_at_import_by_default(home):
    assert _marker_after_import(home, None) == "from-user-env"


def test_zen_no_user_env_skips_the_load_at_import(home):
    assert _marker_after_import(home, "1") == "None"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", " yes "])
def test_truthy_values_opt_out(monkeypatch, value):
    monkeypatch.setenv("ZEN_NO_USER_ENV", value)
    assert _user_env_opted_out()


@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "2"])
def test_other_values_keep_the_load(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ZEN_NO_USER_ENV", raising=False)
    else:
        monkeypatch.setenv("ZEN_NO_USER_ENV", value)
    assert not _user_env_opted_out()


def test_unit_tests_run_with_the_opt_out_set():
    # tests/conftest.py sets it before anything imports zen_cli, so no test sees the developer's ~/.zen/.env
    opt_out = os.environ.get("ZEN_NO_USER_ENV")  # a local, so a failure shows only this value, not the environment
    assert opt_out == "1"
