# Module: `llm`

## Responsibility

**One place** for all **large-model requests**: chat/completions, shared **timeouts**, **API keys**, logging, and future **retry** logic. **Ingestion** and **evidence_aggregation** should call into here instead of embedding HTTP clients.

## Main idea

The architecture keeps **LLM upstream** of the **Computational Engine** ([`event-domain-and-graph.md`](../../../../../docs/architecture/event-domain-and-graph.md) §3, §6). This package does **not** build graphs or balances — it only returns **text** (or later: JSON you parse into **`EvidenceBundle`** / **`GraphBlueprint`** in the caller).

## Architecture links

- **Context Engine** — reasoning / initial estimates — [`event-domain-and-graph.md`](../../../../../docs/architecture/event-domain-and-graph.md) §3.  
- **Provenance** — keep `source_item_ids` on evidence produced with LLM help.

## Configuration

| Env var | Purpose |
|---------|---------|
| `BILLION_LLM_BASE_URL` | OpenAI-compatible API base (optional) |
| `BILLION_LLM_API_KEY` | Secret (optional) |

When both are set, extend [`client.py`](client.py) to use **`httpx`**; until then **`get_llm_client()`** returns **`StubLLMClient`**.

## Contract

- Input: `list[ChatMessage]` (`role`, `content`)  
- Output: **`LLMResponse`** (`text`, `model`, `raw`)

## Examples

[`examples/`](examples/) — sample request/response JSON for docs and tests.
