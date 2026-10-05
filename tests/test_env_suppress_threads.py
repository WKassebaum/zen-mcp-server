"""suppress_env_vars edits os.environ, and model calls (and so client creation) now run in worker threads.

Two overlapping suppressions must not undo each other: inside each block the variable stays absent.
"""

import os
import threading
import time

from utils.env import suppress_env_vars

NAME = "ZEN_TEST_SUPPRESSED_PROXY"


def test_overlapping_suppressions_each_see_the_variable_absent(monkeypatch):
    monkeypatch.setenv(NAME, "http://proxy.invalid")
    seen_inside_second = []

    def first():
        with suppress_env_vars(NAME):
            time.sleep(0.3)  # the second block starts meanwhile; this one then exits and restores the variable

    def second():
        time.sleep(0.1)
        with suppress_env_vars(NAME):
            for _ in range(6):
                seen_inside_second.append(NAME in os.environ)
                time.sleep(0.1)

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert seen_inside_second and not any(seen_inside_second)
    assert os.environ.get(NAME) == "http://proxy.invalid"  # restored once both are done


def test_nested_suppression_in_one_thread_still_works(monkeypatch):
    monkeypatch.setenv(NAME, "x")
    with suppress_env_vars(NAME):
        with suppress_env_vars(NAME):
            assert NAME not in os.environ
        assert NAME not in os.environ
    assert os.environ[NAME] == "x"
