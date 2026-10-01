"""scripts/probe_media_support.py: repeats, kind filter, and API errors kept apart from wrong answers."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "probe_media_support.py"
_spec = importlib.util.spec_from_file_location("probe_media_support", SCRIPT)
probe = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = probe  # dataclasses look the module up while it executes
_spec.loader.exec_module(probe)

RIGHT = {"application/pdf": "ZEBRA-42", "audio/wav": "Pelican 7", "video/mp4": "OTTER-9"}


class FakeClient:
    """Answers each probe correctly unless a scripted answer (text or exception) is queued for its mime type."""

    def __init__(self, scripted=None):
        self.scripted = {mime: list(answers) for mime, answers in (scripted or {}).items()}
        self.calls = []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, model, contents):
        mime = contents[0]["parts"][0]["inline_data"]["mime_type"]
        self.calls.append((model, mime))
        queued = self.scripted.get(mime)
        answer = queued.pop(0) if queued else RIGHT[mime]
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(text=answer)


def _run(capsys, argv, client):
    code = probe.main(argv, client=client)
    out, err = capsys.readouterr()
    return code, json.loads(out), err


def test_default_probes_every_kind_once(capsys):
    client = FakeClient()
    code, matrix, _ = _run(capsys, ["m1"], client)
    assert code == 0
    assert matrix == {"m1": ["pdf", "audio", "video"]}
    assert [mime for _, mime in client.calls] == ["application/pdf", "audio/wav", "video/mp4"]


def test_a_kind_counts_only_if_every_repeat_passes(capsys):
    client = FakeClient({"audio/wav": ["Pelican 7", "Pelican", "Pelican seven"]})
    code, matrix, err = _run(capsys, ["--repeat", "3", "--kinds", "audio", "m1"], client)
    assert code == 0  # a wrong answer is a result, not an error
    assert matrix == {"m1": []}
    assert len(client.calls) == 3
    assert "audio  hits 2/3" in err and "misses 1" in err and "errors 0" in err


def test_kinds_filter_limits_the_probes(capsys):
    client = FakeClient()
    code, matrix, _ = _run(capsys, ["--kinds", "pdf,video", "m1", "m2"], client)
    assert code == 0
    assert matrix == {"m1": ["pdf", "video"], "m2": ["pdf", "video"]}
    assert {mime for _, mime in client.calls} == {"application/pdf", "video/mp4"}


def test_api_errors_are_recorded_apart_from_misses_and_fail_the_run(capsys):
    client = FakeClient({"audio/wav": [RuntimeError("503 UNAVAILABLE"), "Pelican 7"]})
    code, matrix, err = _run(capsys, ["--repeat", "2", "--kinds", "audio,pdf", "m1"], client)
    assert code == 1
    assert matrix == {"m1": ["pdf"]}  # an errored repeat leaves the kind unverified
    assert "ERROR 503 UNAVAILABLE" in err
    assert "audio  hits 1/2  misses 0  errors 1" in err
    assert "pdf    hits 2/2  misses 0  errors 0" in err


@pytest.mark.parametrize("argv", [["--kinds", "pdf,image"], ["--repeat", "0"], ["--kinds", ""]])
def test_bad_arguments_are_rejected(argv):
    with pytest.raises(SystemExit) as excinfo:
        probe.main(argv, client=FakeClient())
    assert excinfo.value.code == 2
