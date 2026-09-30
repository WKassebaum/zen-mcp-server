"""Every media flag in a catalog must be backed by a recorded live probe."""

import json
from pathlib import Path

from tests.media_probe_matrix import PROBED

CONF = Path(__file__).resolve().parent.parent / "conf"
FLAGS = {"supports_pdf": "pdf", "supports_audio": "audio", "supports_video": "video"}
PROVIDER_FOR_FILE = {
    "gemini_models.json": "google",
    "anthropic_models.json": "anthropic",
    "openai_models.json": "openai",
    "xai_models.json": "xai",
    "openrouter_models.json": "openrouter",
}


def test_media_flags_are_probed():
    unverified = []
    for filename, provider in PROVIDER_FOR_FILE.items():
        for entry in json.loads((CONF / filename).read_text())["models"]:
            claimed = {kind for flag, kind in FLAGS.items() if entry.get(flag)}
            verified = PROBED.get((provider, entry["model_name"]), frozenset())
            if claimed - verified:
                unverified.append(f"{provider}/{entry['model_name']}: {sorted(claimed - verified)}")
    assert not unverified, "Media flags without a live probe: " + "; ".join(unverified)


def test_probed_models_are_flagged():
    """The reverse: a passing probe that the catalog forgot to flag is also a mismatch."""
    for (provider, model), kinds in PROBED.items():
        filename = next(name for name, prov in PROVIDER_FOR_FILE.items() if prov == provider)
        entry = next(e for e in json.loads((CONF / filename).read_text())["models"] if e["model_name"] == model)
        claimed = {kind for flag, kind in FLAGS.items() if entry.get(flag)}
        assert claimed == set(kinds), f"{provider}/{model}: catalog {sorted(claimed)} vs probe {sorted(kinds)}"
