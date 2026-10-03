"""The paid live test for Claude/OpenAI reads keys from the environment only and runs -pro models only on request.

Every provider class is replaced by one that refuses to be built, so nothing here can reach an API.
"""

import pytest

import tests.test_media_live as live

ANTHROPIC = next(entry for entry in live.INLINE if entry[0] == "anthropic")
PRO = [entry for entry in live.INLINE if live.is_pro_model(entry[1])]
NOT_PRO = next(entry for entry in live.INLINE if entry[0] == "openai" and not live.is_pro_model(entry[1]))


class _RefuseToCall:
    """Stands in for a provider class: building one means the live test would have made a paid call."""

    PDF_TOKENS_PER_PAGE = 3_000

    def __init__(self, *args, **kwargs):
        raise AssertionError("the live test would have called a real API")


@pytest.fixture(autouse=True)
def no_real_providers(monkeypatch):
    monkeypatch.setattr(
        live, "INLINE_PROVIDERS", {name: (_RefuseToCall, env) for name, (_cls, env) in live.INLINE_PROVIDERS.items()}
    )
    monkeypatch.delenv("ZEN_LIVE_PRO", raising=False)


def test_a_key_only_in_the_zen_env_file_is_not_used(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=from-file\n")
    monkeypatch.setattr("tests.live_keys.ZEN_ENV_FILE", env_file)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(pytest.skip.Exception, match="needs ANTHROPIC_API_KEY"):
        live.test_inline_provider_reads_media(*ANTHROPIC)


def test_the_three_openai_pro_models_are_the_pro_entries():
    assert sorted(model for _provider, model, _kind in PRO) == ["gpt-5.2-pro", "gpt-5.4-pro", "gpt-5.5-pro"]


@pytest.mark.parametrize("provider_name,model,kind", PRO)
def test_pro_models_skip_unless_opted_in(monkeypatch, provider_name, model, kind):
    monkeypatch.setenv(live.INLINE_PROVIDERS[provider_name][1], "test-key")
    with pytest.raises(pytest.skip.Exception, match="ZEN_LIVE_PRO=1"):
        live.test_inline_provider_reads_media(provider_name, model, kind)


def test_pro_models_run_with_the_opt_in(monkeypatch):
    provider_name, model, kind = PRO[0]
    monkeypatch.setenv(live.INLINE_PROVIDERS[provider_name][1], "test-key")
    monkeypatch.setenv("ZEN_LIVE_PRO", "1")
    with pytest.raises(AssertionError, match="would have called a real API"):
        live.test_inline_provider_reads_media(provider_name, model, kind)


def test_other_models_run_with_an_environment_key(monkeypatch):
    provider_name, model, kind = NOT_PRO
    monkeypatch.setenv(live.INLINE_PROVIDERS[provider_name][1], "test-key")
    with pytest.raises(AssertionError, match="would have called a real API"):
        live.test_inline_provider_reads_media(provider_name, model, kind)
