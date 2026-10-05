"""conf/<name>.local.json adds or overrides models, unless ZEN_NO_LOCAL_MODELS opts out (tests/conftest.py sets it)."""

import json
import os
from unittest.mock import patch

import pytest

import providers.registries.base as registry_base
from providers.registries.custom import CustomEndpointModelRegistry


def _model(name: str, score: int) -> dict:
    return {"model_name": name, "context_window": 32_768, "max_output_tokens": 4_096, "intelligence_score": score}


@pytest.fixture
def config_path(tmp_path):
    (tmp_path / "custom_models.json").write_text(json.dumps({"models": [_model("llama3.2", 6)]}))
    local = {"models": [_model("nvidia/nemotron-3-nano-4b", 5), _model("llama3.2", 9)]}
    (tmp_path / "custom_models.local.json").write_text(json.dumps(local))
    return str(tmp_path / "custom_models.json")


def test_local_file_adds_and_overrides_models(config_path, monkeypatch):
    monkeypatch.setattr(registry_base, "SKIP_LOCAL_OVERRIDES", False)
    registry = CustomEndpointModelRegistry(config_path=config_path)
    assert set(registry.list_models()) == {"llama3.2", "nvidia/nemotron-3-nano-4b"}
    assert registry.get_capabilities("llama3.2").intelligence_score == 9


def test_opt_out_skips_the_local_file(config_path, monkeypatch):
    monkeypatch.setattr(registry_base, "SKIP_LOCAL_OVERRIDES", True)
    registry = CustomEndpointModelRegistry(config_path=config_path)
    assert registry.list_models() == ["llama3.2"]
    assert registry.get_capabilities("llama3.2").intelligence_score == 6


@pytest.mark.parametrize("value", ["1", "true", "YES"])
def test_opt_out_values(monkeypatch, value):
    monkeypatch.setenv("ZEN_NO_LOCAL_MODELS", value)
    assert registry_base._local_overrides_opted_out()


@pytest.mark.parametrize("value", [None, "", "0", "false"])
def test_local_files_load_by_default(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ZEN_NO_LOCAL_MODELS", raising=False)
    else:
        monkeypatch.setenv("ZEN_NO_LOCAL_MODELS", value)
    assert not registry_base._local_overrides_opted_out()


def test_unit_tests_skip_local_files_even_with_a_cleared_environment(config_path):
    # Several tests patch os.environ with clear=True; the opt-out must outlive that.
    with patch.dict(os.environ, {}, clear=True):
        registry = CustomEndpointModelRegistry(config_path=config_path)
    assert registry.list_models() == ["llama3.2"]
