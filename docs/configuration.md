# Configuration Guide

This guide covers all configuration options for the Zen MCP Server. The server is configured through environment variables defined in your `.env` file.

## Quick Start Configuration

**Auto Mode (Recommended):** Set `DEFAULT_MODEL=auto` and let Claude intelligently select the best model for each task:

```env
# Basic configuration
DEFAULT_MODEL=auto
GEMINI_API_KEY=your-gemini-key
OPENAI_API_KEY=your-openai-key
```

## Complete Configuration Reference

### Required Configuration

**Workspace Root:**
```env

### API Keys (At least one required)

**Important:** Use EITHER OpenRouter OR native APIs, not both! Having both creates ambiguity about which provider serves each model.

**Option 1: Native APIs (Recommended for direct access)**
```env
# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key_here
# Get from: https://makersuite.google.com/app/apikey

# OpenAI API  
OPENAI_API_KEY=your_openai_api_key_here
# Get from: https://platform.openai.com/api-keys

# X.AI GROK API
XAI_API_KEY=your_xai_api_key_here
# Get from: https://console.x.ai/
```

**Option 2: OpenRouter (Access multiple models through one API)**
```env
# OpenRouter for unified model access
OPENROUTER_API_KEY=your_openrouter_api_key_here
# Get from: https://openrouter.ai/
# If using OpenRouter, comment out native API keys above
```

**Option 3: Custom API Endpoints (Local models)**
```env
# For Ollama, vLLM, LM Studio, etc.
CUSTOM_API_URL=http://localhost:11434/v1  # Ollama example
CUSTOM_API_KEY=                                      # Empty for Ollama
CUSTOM_MODEL_NAME=llama3.2                          # Default model
```

**Local Model Connection:**
- Use standard localhost URLs since the server runs natively
- Example: `http://localhost:11434/v1` for Ollama

### Model Configuration

**Default Model Selection:**
```env
# Options: 'auto', 'pro', 'flash', 'sol', 'luna', 'gpt5.2', 'o3', 'o3-mini', 'o4-mini', etc.
DEFAULT_MODEL=auto  # Claude picks best model for each task (recommended)
```

- **Per call:** a tool call's `model` (or the CLI's `--model`) can also be an intent word, `frontier`, `balanced` or `fast`; see [Choosing a model](#choosing-a-model).

- **Available Models:** The canonical capability data for native providers lives in JSON manifests under `conf/`:
  - `conf/openai_models.json` – OpenAI catalogue (can be overridden with `OPENAI_MODELS_CONFIG_PATH`)
  - `conf/gemini_models.json` – Gemini catalogue (`GEMINI_MODELS_CONFIG_PATH`)
  - `conf/xai_models.json` – X.AI / GROK catalogue (`XAI_MODELS_CONFIG_PATH`)
  - `conf/openrouter_models.json` – OpenRouter catalogue (`OPENROUTER_MODELS_CONFIG_PATH`)
  - `conf/dial_models.json` – DIAL aggregation catalogue (`DIAL_MODELS_CONFIG_PATH`)
  - `conf/custom_models.json` – Custom/OpenAI-compatible endpoints (`CUSTOM_MODELS_CONFIG_PATH`)

  Each JSON file documents the allowed fields via its `_README` block and controls model aliases, capability limits, and feature flags (including `allow_code_generation`). Edit these files (or point the matching `*_MODELS_CONFIG_PATH` variable to your own copy) when you want to adjust context windows, enable JSON mode, enable structured code generation, or expose additional aliases without touching Python code.

  The shipped defaults cover:

  | Provider | Canonical Models | Notable Aliases |
  |----------|-----------------|-----------------|
  | OpenAI | `gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5-pro`, `gpt-5.5`, `gpt-5.2`, `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-4.1`, `o3`, `o3-mini`, `o4-mini` | `gpt-6`, `astra`, `sol`, `luna`, `terra`, `codex`, `gpt5.2`, `mini`, `nano`, `o3mini`, `o4mini` |
  | Gemini | `gemini-3.1-pro-preview`, `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-2.5-pro`, `gemini-2.5-flash` | `pro`, `gemini-pro`, `flash`, `flashlite`, `flash-2.5` |
  | X.AI | `grok-4.7`, `grok-4.6`, `grok-4.5`, `grok-4.3`, `grok-4.20-0309-reasoning`, `grok-build-0.1` | `grok`, `grok4`, `grok-code`, `grokbuild` |
  | OpenRouter | See `conf/openrouter_models.json` for the continually evolving catalogue | e.g., `opus`, `sonnet`, `flash`, `pro`, `mistral` |
  | Custom | User-managed entries such as `llama3.2` | Define your own aliases per entry |

  The GPT-6 entries (`gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna`) expose 1.05M-token contexts and are called through the Responses API (`use_openai_response_api`). The older GPT-5.2 entries (`gpt-5.2`, `gpt-5.2-pro`) expose 400K-token contexts; `gpt-5.2-pro` is Responses-only with streaming disabled, while the base `gpt-5.2` supports streaming along with full code-generation flags. OpenAI shut down the native `gpt-5-codex`, `gpt-5.1-codex` and `gpt-5.1-codex-mini` models on 2026-07-23, so they are no longer in `conf/openai_models.json`; the `codex` alias now resolves to `gpt-5.6-sol`, and `openai/gpt-5.1-codex(-mini)` remain available through OpenRouter. Update your manifests if you run custom deployments so these capability bits stay accurate.

  > **Tip:** Copy the JSON file you need, customise it, and point the corresponding `*_MODELS_CONFIG_PATH` environment variable to your version. This lets you enable or disable capabilities (JSON mode, function calling, temperature support, code generation) without editing Python.

### Choosing a model

- **A named model is always used exactly as named.** Any value other than the words below, a canonical name or an alias such as `flash` or `sol`, goes to the provider that serves it. zen never swaps it for another model. If the model is not available with your keys and allow-lists, or cannot read the attached media, the call fails with that error.
- **`auto`** picks per tool. Each tool has a category (extended reasoning, balanced or fast response), and the first configured provider in priority order (xAI, Gemini, Anthropic, OpenAI, Azure, DIAL, Custom, OpenRouter) picks for that category.
- **Intent words** pick by purpose, whatever the tool. They are case-insensitive, and no model name or alias uses them.
  - `frontier`: the highest-ranked model across every configured provider, premium models included. A tie goes to the higher-priority provider.
  - `balanced`: the pick `auto` makes for a balanced tool.
  - `fast`: the pick `auto` makes for a fast-response tool, such as `chat`.

  Like `auto`, they respect `*_ALLOWED_MODELS` and the attached media (they never send media to Grok). A follow-up that names one resolves it again instead of reusing the previous turn's model.
- **Consensus panel:** `consensus` with no models, or with an entry `frontier`, consults the top model of each configured provider, up to 4, one per vendor. OpenRouter adds one model for each vendor not already on the panel. The entries `fast`, `balanced` and `auto` resolve to one model each. At least two models must remain. `zen consensus` uses the panel when `--models` is not given, and consults every model.

### Code Generation Capability

**`allow_code_generation` Flag:**

The `allow_code_generation` capability enables models to generate complete, production-ready implementations in a structured format. When enabled, the `chat` tool will inject special instructions for substantial code generation tasks.

```json
{
  "model_name": "gpt-5",
  "allow_code_generation": true,
  ...
}
```

**When to Enable:**

- **Enable for**: Models MORE capable than your primary CLI's model (e.g., GPT-6 Astra, GPT-5.2 Pro, GPT-5.2 when using Claude Code with Sonnet 4.5)
- **Purpose**: Get complete implementations from a more powerful reasoning model that your primary CLI can then review and apply
- **Use case**: Large-scale implementations, major refactoring, complete module creation

**Important Guidelines:**

1. Only enable for models significantly more capable than your primary CLI to ensure high-quality generated code
2. The capability triggers structured code output (`<GENERATED-CODE>` blocks) for substantial implementation requests
3. Minor code changes still use inline code blocks regardless of this setting
4. Generated code is saved to `zen_generated.code` in the user's working directory
5. Your CLI receives instructions to review and apply the generated code systematically

**Example Configuration:**

```json
// OpenAI models configuration (conf/openai_models.json)
{
  "models": [
    {
      "model_name": "gpt-5",
      "allow_code_generation": true,
      "intelligence_score": 18,
      ...
    },
    {
      "model_name": "gpt-5.2-pro",
      "allow_code_generation": true,
      "intelligence_score": 19,
      ...
    }
  ]
}
```

**Typical Workflow:**
1. You ask your AI agent to implement a complex new feature using `chat` with a higher-reasoning model such as **gpt-5.2-pro**
2. GPT-5.2-Pro generates structured implementation and shares the complete implementation with ZEN
3. ZEN saves the code to `zen_generated.code` and asks AI agent to implement the plan
4. AI agent continues from the previous context, reads the file, applies the implementation

### Thinking Mode Configuration

**Default Thinking Mode for ThinkDeep:**
```env
# Only applies to models supporting extended thinking (e.g., Gemini 3.1 Pro)
# Starting with Gemini 3 Pro, `thinking level` should stick to `high`

DEFAULT_THINKING_MODE_THINKDEEP=high

# Available modes and token consumption:
#   minimal: 128 tokens   - Quick analysis, fastest response
#   low:     2,048 tokens - Light reasoning tasks  
#   medium:  8,192 tokens - Balanced reasoning
#   high:    16,384 tokens - Complex analysis (recommended for thinkdeep)
#   max:     32,768 tokens - Maximum reasoning depth
```

### Model Usage Restrictions

Control which models can be used from each provider for cost control, compliance, or standardization:

```env
# Format: Comma-separated list (case-insensitive, whitespace tolerant)
# Empty or unset = all models allowed (default)

# OpenAI model restrictions
OPENAI_ALLOWED_MODELS=gpt-6-luna,gpt-5-mini,o3-mini,o4-mini,mini

# Gemini model restrictions  
GOOGLE_ALLOWED_MODELS=flash,pro

# Native Anthropic (Claude) model restrictions (models from conf/anthropic_models.json)
ANTHROPIC_ALLOWED_MODELS=sonnet,haiku

# X.AI GROK model restrictions
XAI_ALLOWED_MODELS=grok-4,grok-4.20-0309-non-reasoning

# OpenRouter model restrictions (affects models via custom provider)
OPENROUTER_ALLOWED_MODELS=opus,sonnet,mistral
```

**Supported Model Names:** The names/aliases listed in the JSON manifests above are the authoritative source. Keep in mind:

- Aliases are case-insensitive and defined per entry (for example, `mini` maps to `gpt-5-mini` by default, while `flash` maps to `gemini-3.8-flash`).
- When you override the manifest files you can add or remove aliases as needed; restriction policies (`*_ALLOWED_MODELS`) automatically pick up those changes.
- Models omitted from a manifest fall back to generic capability detection (where supported) and may have limited feature metadata.

**Example Configurations:**
```env
# Cost control - only cheap models
OPENAI_ALLOWED_MODELS=o4-mini
GOOGLE_ALLOWED_MODELS=flash

# High-performance setup
OPENAI_ALLOWED_MODELS=gpt-6-astra,gpt-6-sol
GOOGLE_ALLOWED_MODELS=pro

# Single model standardization
OPENAI_ALLOWED_MODELS=o4-mini
GOOGLE_ALLOWED_MODELS=pro

# Balanced selection
GOOGLE_ALLOWED_MODELS=flash,pro
OPENAI_ALLOWED_MODELS=gpt-6-luna,gpt-5-mini,o4-mini
XAI_ALLOWED_MODELS=grok,grok-4.20-0309-non-reasoning
```

### Media Input (PDF, Audio, Video)

PDF, audio and video files passed to a tool (`-f` on the CLI, `absolute_file_paths` or `relevant_files` over MCP) reach the model as native input, not as text. A model takes a kind only when its `supports_pdf` / `supports_audio` / `supports_video` flag in `conf/*_models.json` is set, and those flags are set only after a recorded live probe (`tests/media_probe_matrix.py`):

- **Gemini** (`GEMINI_API_KEY`): PDF, audio and video.
- **Claude** (`ANTHROPIC_API_KEY`) and **OpenAI** (`OPENAI_API_KEY`): PDF.
- **Grok** (`XAI_API_KEY`): PDF, only when you name a Grok model, for example `zen chat "Summarize this" --model grok-4.7 -f report.pdf`. For audio, video or a subscription login instead of an API key, run xAI's Grok Build CLI through clink (`zen clink --cli-name grok`), which reads the files itself: see [Grok Build via clink](tools/clink.md#grok-build-via-clink).
- **OpenRouter** (`OPENROUTER_API_KEY`): PDF, audio and video, each only on the models whose live probe passed (their flags in `conf/openrouter_models.json`). No Grok (`x-ai/*`) model takes media through OpenRouter; use `XAI_API_KEY` and name a Grok model instead.

OpenRouter only passes files to models that read them natively:
- zen asks for OpenRouter's native PDF engine. If OpenRouter parses or OCRs a file into text instead (its `file-parser` plugin, `mistral-ocr` by default), zen refuses the answer with an error rather than answer from the extracted text. It does not retry, and never resends the prompt without the file.
- Requests are not pinned to one upstream provider, so a model stays available through every provider OpenRouter routes it to.
- Auto mode uses OpenRouter for media only when no higher-priority provider (Gemini, Claude, OpenAI) has a model that takes every attached kind.
- One OpenRouter request takes at most 32 MB of media once base64-encoded, about 24 MB of raw files.
- Models that zen calls through the Responses API (`use_openai_response_api` in the catalog) take audio as MP3 or WAV only.

In auto mode, zen picks a model that takes every attached kind. It never routes a PDF to Grok, even when `XAI_API_KEY` is set and xAI comes first in provider priority: Gemini, Claude and OpenAI read every page, while xAI may read an attached document through a server-side search tool (`attachment_search`). In zen's probes on 2026-10-03, the grok-4.20 models searched even a one-page PDF, and the other Grok models read four pages without searching. That tool is billed at $5 per 1,000 calls plus the tokens of each search pass, and it may read a long document only in part. zen sends Grok PDF requests with `store=false`; xAI's default, `store=true`, keeps them for 30 days. A Grok request takes at most 50 MB of PDF once base64-encoded, about 37.5 MB of raw files.

What counts as naming a Grok model:
- `--model` or the `model` argument on the call that carries the PDF.
- `DEFAULT_MODEL` set to a Grok model.

Conversation follow-ups with Grok:
- **Without `model`:** a follow-up whose conversation carries a PDF (attached now, or on any earlier turn) goes through auto routing, even if an earlier turn ran on Grok. Grok is not reused for it.
- **Naming Grok:** the earlier turns' PDFs are sent again, and xAI's search may run, and be billed, again.

A named model that cannot take the media a call attaches itself is refused before any API call, with a list of models available with your current keys that can.

**Follow-ups re-attach earlier media.** A follow-up (`continuation_id` over MCP, any tool) sends the media that earlier turns of the conversation attached along with its own, each file once, without naming the files again. First-turn text files still come back as before.
- **What travels:** each turn records the media its own model call attached (the request's files for simple tools, the expert call's for workflow tools, the proposal's for consensus). Workflow tools also keep sending their earlier steps' files.
- **What is left out:** an earlier file is skipped, and the prompt says so, when it no longer exists (`[omitted: earlier report.pdf — file no longer exists]`), when the model cannot take its kind (`[omitted: earlier clip.mp4 — o3 does not take video]`), or when the token budget or the provider's request size runs out, oldest first (`[omitted: older recording.mp4 — over budget]`). The call proceeds. Media the call names itself is never left out: a model that cannot take it is refused, as above.
- **Routing:** auto mode counts the earlier media too, so it picks a model that takes it, and it never hands earlier PDFs to Grok.
- **Uploads:** a large Gemini file is re-sent through the upload cache below, not uploaded again.
- The CLI's workflow commands resend their own files on every `--session/--continue` step. `zen chat` has no follow-ups.

**Prompt caching.** Media requests keep a stable prefix: the system prompt, then the media in the order the conversation first attached it, then the changing text (history and the new request). Each follow-up's request therefore starts with the same bytes as the previous one, so providers' prompt caches can serve that part.
- OpenAI, xAI, Gemini and OpenRouter cache matching prefixes on their own.
- Claude caches only up to a marker: zen puts `cache_control` on the last PDF block of a media request, and, for `anthropic/*` models on OpenRouter, on a short fixed text part right after the last file. Media-free requests carry no marker.
- Providers cache only prefixes above a model-dependent minimum length (512 to 4,096 tokens on Claude models), so a short request may show no cache use.
- **`cached_input_tokens`:** the input tokens a provider served from its cache, in each response's usage and in the output metadata next to `media_attached`. It is read from `prompt_tokens_details.cached_tokens` (Chat Completions), `input_tokens_details.cached_tokens` (Responses API), `cached_content_token_count` (Gemini) and `cache_read_input_tokens` (Claude, which also reports cache writes as `cache_write_input_tokens` in the usage). It is absent when the provider reports nothing, and Claude's `input_tokens` excludes both.

When xAI runs server-side search calls, zen logs a warning ("xAI ran N server-side search call(s) for <model>; billed separately ($5 per 1,000)") and adds the same line to the output as `media_notice`, next to the count in `server_side_tool_calls`.

**What was attached.** Each response lists its media in the output metadata (MCP output and the CLI's `--json`) as `media_attached`: name, kind, bytes, and `transport` (`inline`, `uploaded` or `cached`), plus the Files API name (`file_name`) for an upload. Simple tools put it next to `model_used`; workflow tools in the expert analysis block's `metadata`; consensus in each model's response `metadata`. The CLI's normal output prints the `media_notice` line after the answer.

**Large files on Gemini (upload cache).** Media that does not fit inline (60 MB of raw files per request; the largest files are uploaded first) goes through the Gemini Files API.
- **Privacy:** media above Gemini's inline cap is stored on Google's servers, in your API key's project, for up to 48 hours.
- **Reuse:** zen records each upload in `~/.zen/media_uploads.json` (set `ZEN_MEDIA_UPLOAD_CACHE` to move it), keyed by the file's content hash and type, and reuses it for 47 hours, an hour before Google deletes it. Follow-ups (including re-attached earlier media), each consensus model and retries then send the same file without uploading it again (`transport: cached`). Before reusing an upload, zen checks with Google that it is still there.
- **The cache file** is created with mode 0600 and stores a 12-character fingerprint of the API key, never the key; another key's uploads are not reused. Several zen processes can share it.
- **Deleting:** zen never deletes uploads; Google deletes them after 48 hours. The output names each upload ("Uploaded to the Gemini Files API: files/abc (clip.mp4); Google deletes uploads after 48 h."), so you can delete one sooner through the Gemini API.

### Advanced Configuration

**Custom Model Configuration & Manifest Overrides:**
```env
# Override default location of built-in catalogues
OPENAI_MODELS_CONFIG_PATH=/path/to/openai_models.json
GEMINI_MODELS_CONFIG_PATH=/path/to/gemini_models.json
XAI_MODELS_CONFIG_PATH=/path/to/xai_models.json
OPENROUTER_MODELS_CONFIG_PATH=/path/to/openrouter_models.json
DIAL_MODELS_CONFIG_PATH=/path/to/dial_models.json
CUSTOM_MODELS_CONFIG_PATH=/path/to/custom_models.json
```

**Conversation Settings:**
```env
# How long AI-to-AI conversation threads persist in memory (hours)
# Conversations are auto-purged when claude closes its MCP connection or 
# when a session is quit / re-launched 
CONVERSATION_TIMEOUT_HOURS=5

# Maximum conversation turns (each exchange = 2 turns)
MAX_CONVERSATION_TURNS=20
```

**Logging Configuration:**
```env
# Logging level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=DEBUG  # Default: shows detailed operational messages
```

## Configuration Examples

### Development Setup
```env
# Development with multiple providers
DEFAULT_MODEL=auto
GEMINI_API_KEY=your-gemini-key
OPENAI_API_KEY=your-openai-key
GOOGLE_ALLOWED_MODELS=flash,pro
OPENAI_ALLOWED_MODELS=gpt-6-luna,gpt-5-mini,o4-mini
XAI_API_KEY=your-xai-key
LOG_LEVEL=DEBUG
CONVERSATION_TIMEOUT_HOURS=1
```

### Production Setup
```env
# Production with cost controls
DEFAULT_MODEL=auto
GEMINI_API_KEY=your-gemini-key
OPENAI_API_KEY=your-openai-key
GOOGLE_ALLOWED_MODELS=flash
OPENAI_ALLOWED_MODELS=gpt-6-luna,o4-mini
LOG_LEVEL=INFO
CONVERSATION_TIMEOUT_HOURS=3
```

### Local Development
```env
# Local models only
DEFAULT_MODEL=llama3.2
CUSTOM_API_URL=http://localhost:11434/v1
CUSTOM_API_KEY=
CUSTOM_MODEL_NAME=llama3.2
LOG_LEVEL=DEBUG
```

### OpenRouter Only
```env
# Single API for multiple models
DEFAULT_MODEL=auto
OPENROUTER_API_KEY=your-openrouter-key
OPENROUTER_ALLOWED_MODELS=opus,sonnet,gpt-4
LOG_LEVEL=INFO
```

## Important Notes

**Local Networking:**
- Use standard localhost URLs for local models
- The server runs as a native Python process

**API Key Priority:**
- Native APIs take priority over OpenRouter when both are configured
- Avoid configuring both native and OpenRouter for the same models

**Model Restrictions:**
- Apply to all usage including auto mode
- Empty/unset = all models allowed
- Invalid model names are warned about at startup

**Configuration Changes:**
- Restart the server with `./run-server.sh` after changing `.env`
- Configuration is loaded once at startup

## Related Documentation

- **[Advanced Usage Guide](advanced-usage.md)** - Advanced model usage patterns, thinking modes, and power user workflows
- **[Context Revival Guide](context-revival.md)** - Conversation persistence and context revival across sessions
- **[AI-to-AI Collaboration Guide](ai-collaboration.md)** - Multi-model coordination and conversation threading
