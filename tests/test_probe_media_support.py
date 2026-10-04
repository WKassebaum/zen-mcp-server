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


# --- Anthropic, OpenAI and xAI: probing goes through zen's provider classes ----------------------------------

from providers.anthropic import AnthropicProvider  # noqa: E402
from providers.shared import ModelResponse  # noqa: E402
from tests import live_keys  # noqa: E402
from utils.media import MediaKind  # noqa: E402

CATALOG = Path(__file__).resolve().parent.parent / "conf"


class FakeProvider:
    """Stands in for AnthropicProvider / OpenAIModelProvider / XAIModelProvider. Answers ZEBRA-42 with 1,600 input tokens unless
    an answer is queued for the model: (text, input_tokens) or an exception."""

    MEDIA_KINDS = AnthropicProvider.MEDIA_KINDS

    def __init__(self, scripted=None, api_key=None):
        self.scripted = {model: list(answers) for model, answers in (scripted or {}).items()}
        self.api_key = api_key
        self.calls = []

    def generate_content(self, prompt, model_name, media=None, **kwargs):
        self.calls.append((model_name, prompt, media, kwargs))
        queued = self.scripted.get(model_name)
        answer = queued.pop(0) if queued else ("ZEBRA-42", 1_600)
        if isinstance(answer, Exception):
            raise answer
        text, input_tokens = answer
        usage = {"input_tokens": input_tokens, "output_tokens": 6, "total_tokens": input_tokens + 6}
        return ModelResponse(content=text, usage=usage, model_name=model_name)


def _run_provider(capsys, argv, provider):
    code = probe.main(argv, provider_factory=lambda: provider)
    out, err = capsys.readouterr()
    return code, json.loads(out), err


def _never_called():
    raise AssertionError("no provider may be built for a rejected run")


def test_anthropic_run_prints_pass_and_miss_with_input_tokens(capsys):
    provider = FakeProvider({"claude-a": [("ZEBRA-42", 1_620)], "claude-b": [("I see a zebra.", 1_580)]})
    code, matrix, err = _run_provider(capsys, ["--provider", "anthropic", "claude-a", "claude-b"], provider)
    assert code == 0  # a wrong answer is a result, not an error
    assert matrix == {"claude-a": ["pdf"], "claude-b": []}
    assert "claude-a" in err and "pdf    1/1 PASS  input_tokens 1620" in err
    assert "pdf    1/1 MISS  input_tokens 1580" in err
    assert "hits 1/1  misses 0  errors 0  max input_tokens 1620  -> verified" in err
    assert "hits 0/1  misses 1  errors 0  max input_tokens 1580  -> not verified" in err


def test_each_try_sends_the_fixture_through_the_provider_encoder(capsys):
    provider = FakeProvider()
    _run_provider(capsys, ["--provider", "openai", "gpt-x"], provider)
    [(model, prompt, media, kwargs)] = provider.calls  # default kinds: the provider's MEDIA_KINDS (PDF only)
    assert model == "gpt-x"
    assert prompt == probe.PROBES["pdf"][2]
    assert kwargs == {}
    [attachment] = media
    assert attachment.kind == MediaKind.PDF and attachment.mime_type == "application/pdf"
    assert Path(attachment.source_path) == (probe.FIXTURES / "zebra.pdf").resolve()


def test_summary_keeps_the_largest_input_tokens_over_repeats(capsys):
    provider = FakeProvider({"claude-a": [("ZEBRA-42", 1_600), ("ZEBRA-42", 1_650), ("ZEBRA-42", 1_610)]})
    code, matrix, err = _run_provider(capsys, ["--provider", "anthropic", "--repeat", "3", "claude-a"], provider)
    assert code == 0
    assert matrix == {"claude-a": ["pdf"]}
    assert "hits 3/3  misses 0  errors 0  max input_tokens 1650  -> verified" in err


def test_provider_exception_is_an_error_and_fails_the_run(capsys):
    provider = FakeProvider({"gpt-x": [RuntimeError("400 file input not supported")]})
    code, matrix, err = _run_provider(capsys, ["--provider", "openai", "gpt-x", "gpt-y"], provider)
    assert code == 1
    assert matrix == {"gpt-x": [], "gpt-y": ["pdf"]}
    assert "ERROR 400 file input not supported" in err
    assert "hits 0/1  misses 0  errors 1  max input_tokens -  -> INCOMPLETE" in err


@pytest.mark.parametrize(
    "name, catalog",
    [("anthropic", "anthropic_models.json"), ("openai", "openai_models.json"), ("xai", "xai_models.json")],
)
def test_default_models_are_every_model_in_the_provider_catalog(capsys, name, catalog):
    expected = [entry["model_name"] for entry in json.loads((CATALOG / catalog).read_text())["models"]]
    provider = FakeProvider()
    code, matrix, _ = _run_provider(capsys, ["--provider", name], provider)
    assert code == 0
    assert [model for model, *_ in provider.calls] == expected
    assert list(matrix) == expected


@pytest.mark.parametrize("name", ["anthropic", "openai", "xai"])
@pytest.mark.parametrize("kinds", ["audio", "video", "pdf,audio"])
def test_kinds_the_provider_encoder_lacks_are_rejected(name, kinds):
    with pytest.raises(SystemExit) as excinfo:
        probe.main(["--provider", name, "--kinds", kinds, "m1"], provider_factory=_never_called)
    assert excinfo.value.code == 2


def test_xai_probes_pdf_only():
    assert probe.sendable_kinds("xai") == ["pdf"]


def test_unknown_provider_is_rejected():
    with pytest.raises(SystemExit) as excinfo:
        probe.main(["--provider", "openrouter", "m1"], provider_factory=_never_called)
    assert excinfo.value.code == 2


@pytest.mark.parametrize(
    "name, env_name", [("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY"), ("xai", "XAI_API_KEY")]
)
def test_missing_key_stops_the_run_naming_only_the_variable(capsys, monkeypatch, tmp_path, name, env_name):
    monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setattr(live_keys, "ZEN_ENV_FILE", tmp_path / "absent.env")

    class Exploding(FakeProvider):
        def __init__(self, api_key):
            raise AssertionError("no provider may be built without a key")

    monkeypatch.setitem(probe.PROVIDERS, name, probe.ProviderSpec(env_name, Exploding))
    code = probe.main(["--provider", name, "m1"])
    out, err = capsys.readouterr()
    assert code == 2
    assert out == ""
    assert err.strip() == f"{env_name} is not set and not in ~/.zen/.env"


def test_key_from_zen_config_reaches_the_provider_and_is_never_printed(capsys, monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=fake-key-from-zen-config\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(live_keys, "ZEN_ENV_FILE", env_file)
    built = []

    class Recording(FakeProvider):
        def __init__(self, api_key):
            super().__init__(api_key=api_key)
            built.append(self)

    monkeypatch.setitem(probe.PROVIDERS, "anthropic", probe.ProviderSpec("ANTHROPIC_API_KEY", Recording))
    code = probe.main(["--provider", "anthropic", "claude-a"])
    out, err = capsys.readouterr()
    assert code == 0
    assert [provider.api_key for provider in built] == ["fake-key-from-zen-config"]
    assert "fake-key-from-zen-config" not in out + err


def test_real_provider_classes_back_the_probe():
    from providers.openai import OpenAIModelProvider
    from providers.xai import XAIModelProvider

    assert probe.PROVIDERS["anthropic"] == probe.ProviderSpec("ANTHROPIC_API_KEY", AnthropicProvider)
    assert probe.PROVIDERS["openai"] == probe.ProviderSpec("OPENAI_API_KEY", OpenAIModelProvider)
    assert probe.PROVIDERS["xai"] == probe.ProviderSpec("XAI_API_KEY", XAIModelProvider)
