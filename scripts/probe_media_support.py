#!/usr/bin/env python3
"""Probe which Gemini models read PDF/audio/video natively, using the fixtures in tests/fixtures/media.

Usage: GEMINI_API_KEY=... .zen_venv/bin/python scripts/probe_media_support.py [--repeat N] [--kinds pdf,audio,video] [model ...]
Defaults to every model in conf/gemini_models.json, every kind, one try each. Prints a JSON matrix of
verified kinds on stdout; per-try lines and a hits/N summary per (model, kind) go to stderr.

A kind is verified only if every repeat answers correctly. A wrong answer is a miss; an exception from
the API (quota, transport, unknown model) is an error, counted apart from misses, and makes the script
exit 1 because the run did not finish. Cost: one short generateContent call per (model, kind, repeat).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
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


@dataclass
class Tally:
    hits: int = 0
    misses: int = 0
    errors: int = 0

    @property
    def tries(self) -> int:
        return self.hits + self.misses + self.errors

    @property
    def verified(self) -> bool:
        return self.tries > 0 and self.hits == self.tries


def _kinds(value: str) -> list[str]:
    kinds = [kind.strip() for kind in value.split(",") if kind.strip()]
    unknown = [kind for kind in kinds if kind not in PROBES]
    if not kinds or unknown:
        raise argparse.ArgumentTypeError(f"choose from {','.join(PROBES)} (got {value!r})")
    return [kind for kind in PROBES if kind in kinds]  # probe in the usual order, without duplicates


def _repeat(value: str) -> int:
    count = int(value)
    if count < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return count


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("models", nargs="*", help="models to probe (default: every model in the Gemini catalog)")
    parser.add_argument("--repeat", type=_repeat, default=1, help="tries per (model, kind); all must pass")
    parser.add_argument("--kinds", type=_kinds, default=list(PROBES), help="comma-separated: pdf,audio,video")
    return parser.parse_args(argv)


def probe_one(client, model: str, kind: str) -> tuple[bool, str]:
    """One try. Returns (correct, answer); API and transport exceptions propagate to the caller."""
    filename, mime, question = PROBES[kind]
    data = (FIXTURES / filename).read_bytes()
    response = client.models.generate_content(
        model=model,
        contents=[{"parts": [{"inline_data": {"mime_type": mime, "data": data}}, {"text": question}]}],
    )
    return passed(kind, response.text), response.text


def main(argv: list[str] | None = None, client=None) -> int:
    args = parse_args(argv)
    if client is None:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    models = args.models
    if not models:
        catalog = json.loads((ROOT / "conf" / "gemini_models.json").read_text())
        models = [entry["model_name"] for entry in catalog["models"]]

    tallies: dict[str, dict[str, Tally]] = {}
    for model in models:
        tallies[model] = {}
        for kind in args.kinds:
            tally = tallies[model][kind] = Tally()
            for attempt in range(1, args.repeat + 1):
                label = f"{model:32} {kind:6} {attempt}/{args.repeat}"
                try:
                    ok, text = probe_one(client, model, kind)
                except Exception as exc:  # an API or transport failure is not an answer: record it apart
                    tally.errors += 1
                    print(f"{label} ERROR {exc}", file=sys.stderr)
                    continue
                if ok:
                    tally.hits += 1
                else:
                    tally.misses += 1
                print(f"{label} {'PASS' if ok else 'MISS'}  {text!r:.60}", file=sys.stderr)

    print("\nSummary (verified only if every try passed):", file=sys.stderr)
    for model, by_kind in tallies.items():
        for kind, tally in by_kind.items():
            verdict = "verified" if tally.verified else ("INCOMPLETE" if tally.errors else "not verified")
            print(
                f"{model:32} {kind:6} hits {tally.hits}/{tally.tries}  misses {tally.misses}  "
                f"errors {tally.errors}  -> {verdict}",
                file=sys.stderr,
            )

    print(
        json.dumps(
            {model: [k for k, t in by_kind.items() if t.verified] for model, by_kind in tallies.items()}, indent=2
        )
    )
    errors = sum(tally.errors for by_kind in tallies.values() for tally in by_kind.values())
    if errors:
        print(f"\n{errors} probe(s) ended in an API error; rerun them before reading the matrix.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
