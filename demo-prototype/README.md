# Demo prototype (web)

Minimal **FastAPI** app that exercises repo fixtures: **event** → **stub ingestion** → **graph** (load sample or apply `GraphPatch`) → **computational engine** (balances + pairwise transfers).

## Requirements

- [uv](https://docs.astral.sh/uv/) installed
- Python **3.11+**
- Repo **`fixtures/demo/`** present (paths are resolved relative to this folder’s parent = repo root)

## Run

```bash
cd demo-prototype
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
```

Open **http://127.0.0.1:8765**

## Flow

1. **Load event** — `fixtures/demo/event-sample.json`
2. **Run stub ingestors** — reads `source-descriptors-bundle.json`, emits **evidence** (no LLM)
3. **Load graph** — either full `graph-sample.json` or **`GraphPatch`** from `graph-patch-sample.json`
4. **Compute** — deterministic engine in `app/compute_engine.py` (ceil per share, greedy transfers)

**Demo rule:** after a successful compute, the UI treats the run as **locked** (matches `user-flow-and-gaps.md`).

## Layout

| Path | Role |
|------|------|
| `app/main.py` | Routes, session |
| `app/demo_data.py` | Fixture paths + stub ingestion |
| `app/graph_service.py` | In-memory graph + patch apply |
| `app/compute_engine.py` | Nets + transfers |
| `templates/index.html` | Simple UI |

Architecture docs: [`../docs/architecture/overview.md`](../docs/architecture/overview.md).
