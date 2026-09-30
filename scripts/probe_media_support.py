#!/usr/bin/env python3
"""Probe which Gemini models read PDF/audio/video natively, using the fixtures in tests/fixtures/media.

Usage: GEMINI_API_KEY=... .zen_venv/bin/python scripts/probe_media_support.py [model ...]
Defaults to every model in conf/gemini_models.json. Prints a JSON matrix of verified kinds.
Cost: one short generateContent call per (model, kind) — a few cents in total.
"""

import json
import os
import re
import sys
from pathlib import Path

from google import genai

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "media"
PROBES = {
    "pdf": ("zebra.pdf", "application/pdf", "What code is written in this PDF? Reply with only the code."),
    "audio": ("pelican.wav", "audio/wav", "What code word and number are spoken? Reply with only them."),
    "video": ("otter.mp4", "video/mp4", "What text is shown in this video? Reply with only that text."),
}


def passed(kind: str, text: str) -> bool:
    normalized = re.sub(r"\s+", "", (text or "").upper())
    if kind == "pdf":
        return "ZEBRA-42" in normalized
    if kind == "audio":
        return "PELICAN" in normalized and ("7" in normalized or "SEVEN" in normalized)
    return "OTTER-9" in normalized


def main(models: list[str]) -> int:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    if not models:
        catalog = json.loads((ROOT / "conf" / "gemini_models.json").read_text())
        models = [entry["model_name"] for entry in catalog["models"]]
    results: dict[str, list[str]] = {}
    for model in models:
        verified = []
        for kind, (filename, mime, question) in PROBES.items():
            data = (FIXTURES / filename).read_bytes()
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[{"parts": [{"inline_data": {"mime_type": mime, "data": data}}, {"text": question}]}],
                )
                ok = passed(kind, response.text)
                print(f"{model:32} {kind:6} {'PASS' if ok else 'FAIL'}  {response.text!r:.60}", file=sys.stderr)
            except Exception as exc:  # report and keep probing the rest
                ok = False
                print(f"{model:32} {kind:6} ERROR {exc}", file=sys.stderr)
            if ok:
                verified.append(kind)
        results[model] = verified
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
