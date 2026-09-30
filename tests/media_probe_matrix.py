"""Media kinds verified per (provider, model) by a live probe.

Source of truth for the catalog guard test: a catalog may only set supports_pdf/audio/video
for kinds listed here. Update this file and the catalog together, citing the probe run.

gemini: scripts/probe_media_support.py, run 2026-09-30 (google-genai 1.46, inline_data).
Audio FAILED in that run for gemini-2.5-flash ("Pelican", no number) and gemini-2.5-flash-lite
("Pelican 5"); a one-off recheck of both passed, so their audio is flaky and stays unflagged.
"""

PROBED: dict[tuple[str, str], frozenset[str]] = {
    ("google", "gemini-3.1-pro-preview"): frozenset({"pdf", "audio", "video"}),
    ("google", "gemini-3.8-flash"): frozenset({"pdf", "audio", "video"}),
    ("google", "gemini-3.7-flash"): frozenset({"pdf", "audio", "video"}),
    ("google", "gemini-3.6-flash"): frozenset({"pdf", "audio", "video"}),
    ("google", "gemini-3.5-flash"): frozenset({"pdf", "audio", "video"}),
    ("google", "gemini-3.5-flash-lite"): frozenset({"pdf", "audio", "video"}),
    ("google", "gemini-3-flash-preview"): frozenset({"pdf", "audio", "video"}),
    ("google", "gemini-2.5-pro"): frozenset({"pdf", "audio", "video"}),
    ("google", "gemini-2.5-flash-lite"): frozenset({"pdf", "video"}),
    ("google", "gemini-2.5-flash"): frozenset({"pdf", "video"}),
}
