# Config-driven providers

Tau lets you add custom model providers without modifying source code.
Providers are defined in ``~/.tau/catalog.toml`` using the same TOML schema
as the built-in catalog.

## Quick start

**Via the TUI** — run ``/login`` in Tau and select a built-in provider, or
run ``/login custom`` (or ``/login add``) to add any OpenAI-compatible or
Anthropic-compatible provider interactively.

**Via the CLI** — run ``tau providers add`` from the terminal (no TUI needed):

```bash
tau providers add
```

You will be prompted for:

1. **Provider name** — short identifier, e.g. ``nebius``
2. **Display name** — human-readable name shown in the UI
3. **Provider kind** — the API protocol:
   - ``openai-compatible`` (default) — OpenAI Chat Completions API
   - ``anthropic`` — Anthropic Messages API
   - ``openai-codex`` — OpenAI Codex subscription (OAuth, needs TUI)
   - ``google-generative-ai`` — Google Gemini API
   - ``mistral-conversations`` — Mistral API
4. **Base URL** — the API endpoint
5. **API key env var** — environment variable that holds the API key
6. **Model IDs** — comma-separated list of model identifiers
7. **Default model** — must be one of the model IDs listed above
8. **API key** — optionally store it in Tau's credential store

## Manual config (``~/.tau/catalog.toml``)

You can also edit ``~/.tau/catalog.toml`` directly:

```toml
schema_version = 1

[[providers]]
name = "nebius"
display_name = "Nebius AI Studio"
kind = "openai-compatible"
base_url = "https://api.studio.nebius.ai/v1"
api_key_env = "NEBIUS_API_KEY"
credential_name = "nebius"
models = ["deepseek-ai/DeepSeek-V4-Pro", "Qwen/Qwen3-Coder-480B-A35B-Instruct"]
default_model = "deepseek-ai/DeepSeek-V4-Pro"
docs_url = "https://studio.nebius.ai/docs"

[providers.context_windows]
"deepseek-ai/DeepSeek-V4-Pro" = 163840
```

## Provider kinds and API mapping

| kind | Default API | Provider class |
|------|------------|---------------|
| ``openai-compatible`` | ``openai-completions`` | ``OpenAICompatibleProvider`` |
| ``anthropic`` | ``anthropic-messages`` | ``AnthropicProvider`` |
| ``openai-codex`` | ``openai-codex-responses`` | ``OpenAICodexProvider`` |
| ``google-generative-ai`` | ``google-generative-ai`` | ``GoogleGenerativeAIProvider`` |
| ``mistral-conversations`` | ``mistral-conversations`` | ``MistralConversationsProvider`` |

## Architecture

- ``src/tau_coding/catalog_loader.py`` — loads and validates TOML catalog files
- ``src/tau_coding/provider_catalog.py`` — typed catalog entry definitions
- ``src/tau_coding/provider_config.py`` — converts catalog entries to runtime configs
- ``src/tau_coding/provider_add.py`` — CLI interactive command
- ``src/tau_coding/credentials.py`` — API key storage
- ``src/tau_coding/tui/app.py`` — ``CustomProviderLoginScreen``

The loading order is:

1. Built-in catalog (``src/tau_coding/data/catalog.toml``)
2. User catalog merged on top (``~/.tau/catalog.toml``)

User providers override built-in providers with the same name.

## OpenCode providers

This fork adds four OpenCode subscription providers to the built-in catalog:

| Provider | Type | Base URL | Models |
|----------|------|----------|--------|
| ``opencode-zen`` | openai-compatible | ``https://opencode.ai/zen/v1`` | GPT-5.5, GPT-5.4, DeepSeek V4, Kimi, GLM, free models |
| ``opencode-zen-anthropic`` | anthropic (bearer auth) | ``https://opencode.ai/zen/v1`` | Claude Fable 5, Opus 4.8, Sonnet 4.6, Haiku 4.5 |
| ``opencode-go`` | openai-compatible | ``https://opencode.ai/zen/go/v1`` | DeepSeek V4 Flash, GLM-5.2, Kimi K2.7 |
| ``opencode-go-anthropic`` | anthropic (bearer auth) | ``https://opencode.ai/zen/go/v1`` | MiniMax M3, Qwen3.7 Max |

Login with ``/login opencode-zen`` in the TUI and paste your API key.

## New CLI commands

```bash
tau providers add            # interactive: add a custom provider via CLI
tau --harness <name>         # use a specific harness
tau --list-harnesses         # list available harnesses
```
