"""Every media flag in a catalog must be backed by a recorded live probe, and every probe by a flag.

Each check collects every problem and asserts once, so one run reports all of them.
"""

import json
from pathlib import Path

from providers.shared import ProviderType
from tests.media_probe_matrix import PROBED

CONF = Path(__file__).resolve().parent.parent / "conf"
CATALOG_GLOB = "*_models.json"
FLAGS = {"supports_pdf": "pdf", "supports_audio": "audio", "supports_video": "video"}
PROVIDER_FOR_FILE = {
    "gemini_models.json": "google",
    "anthropic_models.json": "anthropic",
    "openai_models.json": "openai",
    "xai_models.json": "xai",
    "openrouter_models.json": "openrouter",
    "custom_models.json": "custom",
    "dial_models.json": "dial",
    "azure_models.json": "azure",
}


def _entries(filename: str) -> list[dict]:
    """The model entries of a catalog: its top-level "models" list (azure's "_example_models" is never loaded)."""
    data = json.loads((CONF / filename).read_text())
    models = data.get("models") if isinstance(data, dict) else None
    assert isinstance(models, list), f"conf/{filename}: expected a top-level 'models' list"
    return models


def _catalog_claims() -> dict[tuple[str, str], set[str]]:
    """(provider, model_name) -> media kinds its catalog entry flags, across every mapped catalog."""
    return {
        (provider, entry["model_name"]): {kind for flag, kind in FLAGS.items() if entry.get(flag)}
        for filename, provider in PROVIDER_FOR_FILE.items()
        for entry in _entries(filename)
    }


def unprobed_flags(claims: dict, probed: dict) -> list[str]:
    """Catalog flags that no live probe verified."""
    problems = []
    for (provider, model), claimed in sorted(claims.items()):
        missing = claimed - set(probed.get((provider, model), frozenset()))
        if missing:
            problems.append(f"{provider}/{model}: flagged {sorted(missing)} without a live probe")
    return problems


def unflagged_probes(claims: dict, probed: dict) -> list[str]:
    """Probe entries that name no catalog model (stale or misspelled), or whose kinds the catalog does not flag."""
    file_for_provider = {provider: filename for filename, provider in PROVIDER_FOR_FILE.items()}
    problems = []
    for (provider, model), kinds in sorted(probed.items()):
        if provider not in file_for_provider:
            problems.append(f"PROBED entry {provider}/{model}: no catalog is mapped to provider '{provider}'")
        elif (provider, model) not in claims:
            problems.append(
                f"PROBED entry {provider}/{model}: no model named '{model}' in conf/{file_for_provider[provider]}"
                " (stale or misspelled; use the canonical model_name, not an alias)"
            )
        elif claims[(provider, model)] != set(kinds):
            problems.append(f"{provider}/{model}: catalog {sorted(claims[(provider, model)])} vs probe {sorted(kinds)}")
    return problems


def test_every_catalog_is_mapped():
    """A new conf/*_models.json must be added to PROVIDER_FOR_FILE, or its media flags go unchecked."""
    on_disk = {path.name for path in CONF.glob(CATALOG_GLOB)}
    problems = [f"conf/{name} is not in PROVIDER_FOR_FILE" for name in sorted(on_disk - set(PROVIDER_FOR_FILE))]
    problems += [
        f"PROVIDER_FOR_FILE maps conf/{name}, which does not exist" for name in sorted(set(PROVIDER_FOR_FILE) - on_disk)
    ]
    known = {provider_type.value for provider_type in ProviderType}
    problems += [
        f"PROVIDER_FOR_FILE maps conf/{name} to '{provider}', which is not a ProviderType value"
        for name, provider in sorted(PROVIDER_FOR_FILE.items())
        if provider not in known
    ]
    assert not problems, "Catalog mapping problems: " + "; ".join(problems)


def test_media_flags_are_probed():
    problems = unprobed_flags(_catalog_claims(), PROBED)
    assert not problems, "Media flags without a live probe: " + "; ".join(problems)


def test_probed_models_are_flagged():
    """The reverse: a passing probe that the catalog forgot to flag is also a mismatch."""
    problems = unflagged_probes(_catalog_claims(), PROBED)
    assert not problems, "Probe matrix and catalogs disagree: " + "; ".join(problems)


def test_stale_probe_entries_are_named_together():
    """A misspelled model or provider in PROBED is reported by name, every one in the same run."""
    probed = {
        ("google", "gemini-3.8-flahs"): frozenset({"pdf"}),
        ("gooogle", "gemini-3.8-flash"): frozenset({"pdf"}),
    }
    problems = unflagged_probes(_catalog_claims(), probed)
    assert len(problems) == 2
    assert "google/gemini-3.8-flahs" in problems[0] and "conf/gemini_models.json" in problems[0]
    assert "gooogle/gemini-3.8-flash" in problems[1] and "'gooogle'" in problems[1]


def test_every_unprobed_flag_is_reported():
    claims = {("google", "a"): {"pdf", "audio"}, ("google", "b"): {"video"}}
    problems = unprobed_flags(claims, {("google", "a"): frozenset({"pdf"})})
    assert problems == [
        "google/a: flagged ['audio'] without a live probe",
        "google/b: flagged ['video'] without a live probe",
    ]
