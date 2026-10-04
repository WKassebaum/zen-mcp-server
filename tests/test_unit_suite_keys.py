"""Unit tests must never see a real API key: an unmocked provider call would otherwise be a paid one.

Keys reach local runs from the shell, from the checkout's .env (utils.env) and from ~/.zen/.env (zen_cli.main).
tests/conftest.py replaces them for every test not marked integration. Only variable names are asserted on and
reported, so a failure can never print a key.
"""

import os

from tests.conftest import DUMMY_KEY, DUMMY_KEY_VARS, UNSET_KEY_VARS


def test_unit_tests_see_dummy_keys_only():
    not_dummy = [name for name in DUMMY_KEY_VARS if os.environ.get(name) != DUMMY_KEY]
    assert not not_dummy, f"variables not set to the dummy key: {not_dummy}"


def test_unit_tests_see_no_other_provider_keys():
    still_set = [name for name in UNSET_KEY_VARS if os.environ.get(name)]
    assert not still_set, f"provider key variables still set: {still_set}"
