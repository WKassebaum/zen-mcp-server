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
gpt-5-mini and gpt-5-nano passed the first probe but then mostly answered "I can't access the PDF" with the
PDF attached (241 input tokens, like every other Chat model): 1/3 and 1/3 without a system prompt, 1/3 and 0/3
with one. They stay unflagged. Every other non-pro OpenAI model and every Claude model also passed the live
test (tests/test_media_live.py) on 2026-10-03; the three -pro models were probed once.
o3-mini read zebra.pdf twice but has no vision: on the image-only letter-size PDF it answered "HERON" for
"HERON-5" twice (260 input tokens; vision models 323-2,902), so it sees only a text layer and stays unflagged
(OpenAI's file-inputs guide: page images need a vision model). Every other flagged non-pro OpenAI model read
that scanned page on 2026-10-03.

xai: scripts/probe_media_support.py --provider xai --repeat 2, run 2026-10-03 through XAIModelProvider (input_file on
/v1/responses; Chat Completions refuses file parts). PDF only. All 7 models read zebra.pdf 2/2. Through the same provider
with zen's chat system prompt, every model also read an image-only letter page and an image-only four-page PDF (all four
markers, in order). xAI's server-side attachment_search ran unpredictably: 0 calls on most models (about 500-600 input
tokens per page), 2-3 calls on the grok-4.20 models even for one page (up to 8,889 input tokens). Grok gets PDFs only
when the user names a Grok model (XAIModelProvider.MEDIA_AUTO_ROUTING is False).

openrouter: candidates are the kinds a model's architecture.input_modalities lists in
OpenRouter's public models list (scripts/probe_media_support.py --provider openrouter --candidates). A flag needs a
probe through OpenRouterProvider (--provider openrouter), which asks for OpenRouter's native PDF engine and refuses a
response OpenRouter parsed into text (file annotations, or a parser stage in openrouter_metadata), so a model only
passes when it read the file itself.
Run 2026-10-04 through OpenRouterProvider (file parts with the
native PDF engine pinned; zen refuses an answer OpenRouter parsed). PDF: every candidate read zebra.pdf 2/2 (the four
-pro models 1/1). Every one also read zebra.pdf and an image-only letter page through zen's chat system prompt, except
openai/o3-mini and o3-mini-high, which read only the text layer (as natively) and stay unflagged. Audio (pelican.wav)
and video (otter.mp4): 2/2 on the 8 Gemini candidates and kimi-k3 (video). Left unflagged though they passed:
openai/gpt-5-mini and gpt-5-nano (flaky natively across days), google/gemini-2.5-flash audio (flaky natively).
mistralai/mistral-large-2512 got upstream 429s on most tries and is unverified. x-ai/* models are never flagged:
xAI reads files through a paid search tool, and Grok takes media only through the native provider, by name.
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
    ("openai", "gpt-5.1"): frozenset({"pdf"}),
    ("openai", "o3"): frozenset({"pdf"}),
    ("openai", "o4-mini"): frozenset({"pdf"}),
    ("openai", "gpt-4.1"): frozenset({"pdf"}),
    ("openai", "gpt-5.2"): frozenset({"pdf"}),
    ("xai", "grok-4.7"): frozenset({"pdf"}),
    ("xai", "grok-4.6"): frozenset({"pdf"}),
    ("xai", "grok-4.5"): frozenset({"pdf"}),
    ("xai", "grok-4.3"): frozenset({"pdf"}),
    ("xai", "grok-4.20-0309-reasoning"): frozenset({"pdf"}),
    ("xai", "grok-4.20-0309-non-reasoning"): frozenset({"pdf"}),
    ("xai", "grok-build-0.1"): frozenset({"pdf"}),
    ("openrouter", "anthropic/claude-fable-5.1"): frozenset({"pdf"}),
    ("openrouter", "anthropic/claude-opus-5.5"): frozenset({"pdf"}),
    ("openrouter", "anthropic/claude-opus-5"): frozenset({"pdf"}),
    ("openrouter", "anthropic/claude-fable-5"): frozenset({"pdf"}),
    ("openrouter", "anthropic/claude-sonnet-5.5"): frozenset({"pdf"}),
    ("openrouter", "anthropic/claude-sonnet-5"): frozenset({"pdf"}),
    ("openrouter", "anthropic/claude-sonnet-4.5"): frozenset({"pdf"}),
    ("openrouter", "anthropic/claude-opus-4.5"): frozenset({"pdf"}),
    ("openrouter", "anthropic/claude-haiku-4.5"): frozenset({"pdf"}),
    ("openrouter", "anthropic/claude-opus-4.1"): frozenset({"pdf"}),
    ("openrouter", "google/gemini-3.1-pro-preview"): frozenset({"pdf", "audio", "video"}),
    ("openrouter", "google/gemini-3.8-flash"): frozenset({"pdf", "audio", "video"}),
    ("openrouter", "google/gemini-3.7-flash"): frozenset({"pdf", "audio", "video"}),
    ("openrouter", "google/gemini-3.6-flash"): frozenset({"pdf", "audio", "video"}),
    ("openrouter", "google/gemini-3.5-flash"): frozenset({"pdf", "audio", "video"}),
    ("openrouter", "google/gemini-3.5-flash-lite"): frozenset({"pdf", "audio", "video"}),
    ("openrouter", "google/gemini-2.5-pro"): frozenset({"pdf", "audio", "video"}),
    ("openrouter", "google/gemini-2.5-flash"): frozenset({"pdf", "video"}),
    ("openrouter", "mistralai/devstral-2512"): frozenset({"pdf"}),
    ("openrouter", "openai/o3"): frozenset({"pdf"}),
    ("openrouter", "openai/o3-pro"): frozenset({"pdf"}),
    ("openrouter", "openai/o4-mini"): frozenset({"pdf"}),
    ("openrouter", "openai/gpt-6-astra"): frozenset({"pdf"}),
    ("openrouter", "openai/gpt-6-sol"): frozenset({"pdf"}),
    ("openrouter", "openai/gpt-6-luna"): frozenset({"pdf"}),
    ("openrouter", "openai/gpt-5.6-sol"): frozenset({"pdf"}),
    ("openrouter", "openai/gpt-5.6-terra"): frozenset({"pdf"}),
    ("openrouter", "openai/gpt-5.6-luna"): frozenset({"pdf"}),
    ("openrouter", "openai/gpt-5.5-pro"): frozenset({"pdf"}),
    ("openrouter", "openai/gpt-5.5"): frozenset({"pdf"}),
    ("openrouter", "openai/gpt-5"): frozenset({"pdf"}),
    ("openrouter", "openai/gpt-5-pro"): frozenset({"pdf"}),
    ("openrouter", "openai/gpt-5.2-pro"): frozenset({"pdf"}),
    ("openrouter", "openai/gpt-5.2"): frozenset({"pdf"}),
    ("openrouter", "moonshotai/kimi-k3"): frozenset({"video"}),
}
