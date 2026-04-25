# Module: `llm`

## Responsibility

**One place** for all large-model requests: chat completions (text + images), API keys, and timeouts. Ingestion and aggregation modules call into here; they do not embed HTTP clients. Retries/backoff can be centralized here when needed.

## Providers

| `BILLION_LLM_PROVIDER` | Client class | Notes |
|------------------------|-------------|-------|
| `stub` (default) | `StubLLMClient` | Deterministic echo. No network. Tests pass without a key. |
| `openai` | `OpenAICompatibleClient` | Any OpenAI-compatible endpoint: official API, OpenRouter, Together AI, Ollama, … |
| `anthropic` | `AnthropicClient` | Anthropic Messages API (native format). |

## Quick start

Copy `.env.example` → `.env` and set:

```
BILLION_LLM_PROVIDER=anthropic          # or openai
BILLION_LLM_API_KEY=sk-ant-…
BILLION_LLM_MODEL=claude-3-5-sonnet-20241022
```

Restart the server — `get_llm_client()` picks the right client automatically.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `BILLION_LLM_PROVIDER` | `stub` | Which provider to use |
| `BILLION_LLM_API_KEY` | *(empty)* | Auth token for the provider |
| `BILLION_LLM_MODEL` | `gpt-4o` / `claude-3-5-sonnet-20241022` | Model name |
| `BILLION_LLM_BASE_URL` | `https://api.openai.com/v1` | Override for openai-compatible endpoints only |

## Multimodal support

`ChatMessage.content` accepts either a plain `str` **or** a `list[ContentPart]`:

```python
from billion_hackathon.modules.llm.client import (
    ChatMessage, ImagePart, TextPart, get_llm_client,
)

client = get_llm_client()
response = client.complete([
    ChatMessage(role="system", content="Analyze this receipt."),
    ChatMessage(
        role="user",
        content=[
            TextPart(text="What is the total?"),
            ImagePart(data=base64_jpeg, media_type="image/jpeg"),
        ],
    ),
])
```

Both `OpenAICompatibleClient` and `AnthropicClient` translate `ImagePart` to the correct provider format. `StubLLMClient` ignores image parts and echoes the text.

## Contract

- Input: `list[ChatMessage]`
- Output: `LLMResponse(text, model, raw)`
- `LLMResponse.text` is always a plain string; callers parse JSON from it when needed.

## Architecture links

- **Context Engine** reasoning — [`event-domain-and-graph.md`](../../../../../docs/architecture/event-domain-and-graph.md) §3.
- LLM stays **upstream** of the Computational Engine; graph and balances are always deterministic.
- Provenance: callers set `source_item_ids` on EvidenceItems so every LLM inference is traceable.

## Examples

[`examples/`](examples/) — sample request + expected stub response used in contract tests.
