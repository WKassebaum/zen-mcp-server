#!/usr/bin/env python3
"""Probe which models read PDF/audio/video natively, using the fixtures in tests/fixtures/media.

Usage: .zen_venv/bin/python scripts/probe_media_support.py [--provider google|anthropic|openai|xai]
           [--repeat N] [--kinds pdf,audio,video] [model ...]
Defaults to the Gemini provider, every model in its conf/<provider>_models.json catalog, every kind the
provider can send, one try each. Prints a JSON matrix of verified kinds on stdout; per-try lines and a
hits/N summary per (model, kind) go to stderr.

google calls the SDK directly with GEMINI_API_KEY from the environment. anthropic, openai and xai go through
zen's own provider classes (AnthropicProvider, OpenAIModelProvider, XAIModelProvider), so the probe exercises
the shipped encoders; their key comes from the environment or ~/.zen/.env (tests/live_keys.py) and is never
printed. Those runs also print each response's input_tokens, and the summary keeps the largest per (model, kind).

A kind is verified only if every repeat answers correctly. A wrong answer is a miss; an exception from
the API (quota, transport, unknown model) is an error, counted apart from misses, and makes the script
exit 1 because the run did not finish. Cost: one short request per (model, kind, repeat).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # providers, utils and tests.live_keys live at the repo root

from google import genai  # noqa: E402

from providers.anthropic import AnthropicProvider  # noqa: E402
from providers.openai import OpenAIModelProvider  # noqa: E402
from providers.xai import XAIModelProvider  # noqa: E402
from tests.live_keys import api_key  # noqa: E402
from utils.media import classify_media  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "media"
PROBES = {
    "pdf": ("zebra.pdf", "application/pdf", "What code is written in this PDF? Reply with only the code."),
    "audio": ("pelican.wav", "audio/wav", "What code word and number are spoken? Reply with only them."),
    "video": ("otter.mp4", "video/mp4", "What text is shown in this video? Reply with only that text."),
}
CATALOGS = {
    "google": "gemini_models.json",
    "anthropic": "anthropic_models.json",
    "openai": "openai_models.json",
    "xai": "xai_models.json",
}


@dataclass(frozen=True)
class ProviderSpec:
    env_name: str
    cls: type


PROVIDERS = {
    "anthropic": ProviderSpec("ANTHROPIC_API_KEY", AnthropicProvider),
    "openai": ProviderSpec("OPENAI_API_KEY", OpenAIModelProvider),
    "xai": ProviderSpec("XAI_API_KEY", XAIModelProvider),
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
    max_input_tokens: int | None = None  # provider runs only: the largest usage["input_tokens"] seen

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


def sendable_kinds(provider: str) -> list[str]:
    """Kinds the provider can send: all of them for the Gemini SDK, else the provider class's MEDIA_KINDS."""
    if provider == "google":
        return list(PROBES)
    encodable = {kind.value for kind in PROVIDERS[provider].cls.MEDIA_KINDS}
    return [kind for kind in PROBES if kind in encodable]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("models", nargs="*", help="models to probe (default: every model in the provider's catalog)")
    parser.add_argument("--provider", choices=list(CATALOGS), default="google", help="default: google")
    parser.add_argument("--repeat", type=_repeat, default=1, help="tries per (model, kind); all must pass")
    parser.add_argument(
        "--kinds", type=_kinds, default=None, help="comma-separated: pdf,audio,video (default: all the provider sends)"
    )
    args = parser.parse_args(argv)
    sendable = sendable_kinds(args.provider)
    if args.kinds is None:
        args.kinds = sendable
    elif unsendable := [kind for kind in args.kinds if kind not in sendable]:
        parser.error(f"--provider {args.provider} sends only {','.join(sendable)} (got {','.join(unsendable)})")
    return args


def probe_one(client, model: str, kind: str) -> tuple[bool, str]:
    """One Gemini try. Returns (correct, answer); API and transport exceptions propagate to the caller."""
    filename, mime, question = PROBES[kind]
    data = (FIXTURES / filename).read_bytes()
    response = client.models.generate_content(
        model=model,
        contents=[{"parts": [{"inline_data": {"mime_type": mime, "data": data}}, {"text": question}]}],
    )
    return passed(kind, response.text), response.text


def probe_with_provider(provider, model: str, kind: str) -> tuple[bool, str, int | None]:
    """One try through a zen provider. Returns (correct, answer, input_tokens); exceptions propagate."""
    filename, _mime, question = PROBES[kind]
    fixture = str(FIXTURES / filename)
    _text_paths, media = classify_media([fixture])
    if [attachment.kind.value for attachment in media] != [kind]:  # never send the question without the file
        raise RuntimeError(f"{fixture} was not classified as {kind} media")
    response = provider.generate_content(question, model, media=media)
    return passed(kind, response.content), response.content, (response.usage or {}).get("input_tokens")


def main(argv: list[str] | None = None, client=None, provider_factory=None) -> int:
    """Run the probes. Tests inject ``client`` (google) or ``provider_factory`` (a no-argument callable
    returning an object with generate_content, for anthropic/openai/xai) so no real API is reached."""
    args = parse_args(argv)
    show_tokens = args.provider != "google"
    if args.provider == "google":
        if client is None:
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

        def try_once(model, kind):
            return (*probe_one(client, model, kind), None)

    else:
        if provider_factory is None:
            spec = PROVIDERS[args.provider]
            key = api_key(spec.env_name)
            if not key:
                print(f"{spec.env_name} is not set and not in ~/.zen/.env", file=sys.stderr)
                return 2
            provider = spec.cls(api_key=key)
        else:
            provider = provider_factory()

        def try_once(model, kind):
            return probe_with_provider(provider, model, kind)

    models = args.models
    if not models:
        catalog = json.loads((ROOT / "conf" / CATALOGS[args.provider]).read_text())
        models = [entry["model_name"] for entry in catalog["models"]]

    tallies: dict[str, dict[str, Tally]] = {}
    for model in models:
        tallies[model] = {}
        for kind in args.kinds:
            tally = tallies[model][kind] = Tally()
            for attempt in range(1, args.repeat + 1):
                label = f"{model:32} {kind:6} {attempt}/{args.repeat}"
                try:
                    ok, text, input_tokens = try_once(model, kind)
                except Exception as exc:  # an API or transport failure is not an answer: record it apart
                    tally.errors += 1
                    print(f"{label} ERROR {exc}", file=sys.stderr)
                    continue
                if ok:
                    tally.hits += 1
                else:
                    tally.misses += 1
                tokens = ""
                if show_tokens:
                    tokens = f"input_tokens {input_tokens if input_tokens is not None else '-'}  "
                    if input_tokens is not None:
                        tally.max_input_tokens = max(tally.max_input_tokens or 0, input_tokens)
                print(f"{label} {'PASS' if ok else 'MISS'}  {tokens}{text!r:.60}", file=sys.stderr)

    print("\nSummary (verified only if every try passed):", file=sys.stderr)
    for model, by_kind in tallies.items():
        for kind, tally in by_kind.items():
            verdict = "verified" if tally.verified else ("INCOMPLETE" if tally.errors else "not verified")
            tokens = ""
            if show_tokens:
                tokens = f"max input_tokens {tally.max_input_tokens if tally.max_input_tokens is not None else '-'}  "
            print(
                f"{model:32} {kind:6} hits {tally.hits}/{tally.tries}  misses {tally.misses}  "
                f"errors {tally.errors}  {tokens}-> {verdict}",
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
