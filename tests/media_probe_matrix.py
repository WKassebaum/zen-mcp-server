"""Media kinds verified per (provider, model) by a live probe.

Source of truth for the catalog guard test: a catalog may only set supports_pdf/audio/video
for kinds listed here. Update this file and the catalog together, citing the probe run.

gemini: scripts/probe_media_support.py, run 2026-09-30 (google-genai 1.46, inline_data).
Audio FAILED in that run for gemini-2.5-flash ("Pelican", no number) and gemini-2.5-flash-lite
("Pelican 5"); a one-off recheck of both passed, so their audio is flaky and stays unflagged.
Audio re-probed 2026-10-01 with `--repeat 3 --kinds audio` on the eight audio-flagged models: 3/3 each.

anthropic, openai: scripts/probe_media_support.py --provider anthropic|openai, run 2026-10-03 through zen's own
encoders (Anthropic document blocks; OpenAI file parts on Chat Completions, input_file on the Responses API).
PDF only (their encoders take no audio or video). All 13 Claude and all 20 OpenAI catalog models read zebra.pdf
on the first try, the three -pro models included. An image-only PDF (marker drawn as pixels, no text layer)
was also read by gpt-6-luna, gpt-6-astra, gpt-5.5 and claude-sonnet-5-5, so both OpenAI endpoints send page
images, not only extracted text.
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
    ("anthropic", "claude-fable-5-1"): frozenset({"pdf"}),
    ("anthropic", "claude-opus-5-5"): frozenset({"pdf"}),
    ("anthropic", "claude-opus-5"): frozenset({"pdf"}),
    ("anthropic", "claude-fable-5"): frozenset({"pdf"}),
    ("anthropic", "claude-opus-4-8"): frozenset({"pdf"}),
    ("anthropic", "claude-opus-4-7"): frozenset({"pdf"}),
    ("anthropic", "claude-opus-4-6"): frozenset({"pdf"}),
    ("anthropic", "claude-opus-4-5-20251101"): frozenset({"pdf"}),
    ("anthropic", "claude-sonnet-5-5"): frozenset({"pdf"}),
    ("anthropic", "claude-sonnet-5"): frozenset({"pdf"}),
    ("anthropic", "claude-sonnet-4-6"): frozenset({"pdf"}),
    ("anthropic", "claude-sonnet-4-5-20250929"): frozenset({"pdf"}),
    ("anthropic", "claude-haiku-4-5-20251001"): frozenset({"pdf"}),
    ("openai", "gpt-6-astra"): frozenset({"pdf"}),
    ("openai", "gpt-6-sol"): frozenset({"pdf"}),
    ("openai", "gpt-6-luna"): frozenset({"pdf"}),
    ("openai", "gpt-5.6-sol"): frozenset({"pdf"}),
    ("openai", "gpt-5.6-terra"): frozenset({"pdf"}),
    ("openai", "gpt-5.6-luna"): frozenset({"pdf"}),
    ("openai", "gpt-5.5-pro"): frozenset({"pdf"}),
    ("openai", "gpt-5.5"): frozenset({"pdf"}),
    ("openai", "gpt-5.4-pro"): frozenset({"pdf"}),
    ("openai", "gpt-5.4"): frozenset({"pdf"}),
    ("openai", "gpt-5"): frozenset({"pdf"}),
    ("openai", "gpt-5.2-pro"): frozenset({"pdf"}),
    ("openai", "gpt-5-mini"): frozenset({"pdf"}),
    ("openai", "gpt-5-nano"): frozenset({"pdf"}),
    ("openai", "gpt-5.1"): frozenset({"pdf"}),
    ("openai", "o3"): frozenset({"pdf"}),
    ("openai", "o3-mini"): frozenset({"pdf"}),
    ("openai", "o4-mini"): frozenset({"pdf"}),
    ("openai", "gpt-4.1"): frozenset({"pdf"}),
    ("openai", "gpt-5.2"): frozenset({"pdf"}),
}
