# `src/` — Billion hackathon application

This directory holds the **installable Python package** [`billion_hackathon/`](billion_hackathon/) — the hackathon app that turns messy trip data into a **transactional graph** and **settlement math**.

## App idea (one paragraph)

Friends take a trip; money moves between people and shared costs. The product **collects** evidence (notes, photos, later bank lines), **ingests** it into structured **evidence**, **aggregates** that into instructions to **build a graph** (who paid whom, who should share each “good”), lets users **fix inconsistencies**, then runs a **deterministic computation** to say who owes whom. **LLM calls** live behind a small **llm** module so ingestion and aggregation can use the same HTTP/timeouts/keys without scattering `requests` across the codebase.

## How it maps to architecture

| Code area | Architecture doc |
|-----------|------------------|
| Pipeline overview | [`../../docs/architecture/overview.md`](../../docs/architecture/overview.md) |
| Event, graph, Context vs compute | [`../../docs/architecture/event-domain-and-graph.md`](../../docs/architecture/event-domain-and-graph.md) |
| Naming (Trip vs Event, Good, engines) | [`../../docs/architecture/vocabulary-map.md`](../../docs/architecture/vocabulary-map.md) |

## Package layout

```
billion_hackathon/
  main.py              # FastAPI + dev UI
  contracts/           # Pydantic schemas shared between modules
  modules/
    data_collection/   # uploads + notes
    data_ingestion/    # raw → evidence (stub or LLM-assisted)
    evidence_aggregation/  # evidence → graph blueprint (stub or LLM-assisted)
    graph_builder/     # blueprint → graph + inconsistency hints
    computation/       # balances + suggested transfers
    llm/               # single place for LLM HTTP / stubs / config
  web/                 # Jinja templates + static files (dev tabs UI)
```

Each **`modules/<name>/README.md`** describes that module’s responsibility and links to the right architecture sections.

## Run (from repo `hackathon/` folder)

Install **`uv`** (once): see [https://docs.astral.sh/uv/getting-started/installation/](https://docs.astral.sh/uv/getting-started/installation/)

```bash
cd hackathon
uv sync
uv run uvicorn billion_hackathon.main:app --reload --host 127.0.0.1 --port 8080
```

Open **http://127.0.0.1:8080** — the UI is **dev-oriented**: one **tab per module** so people can work and test **independently**.

Optional LLM env vars (when you wire a real provider inside `llm/client.py`):

- `BILLION_LLM_BASE_URL` — e.g. OpenAI-compatible API base  
- `BILLION_LLM_API_KEY` — secret (never commit)

## Tests

```bash
cd hackathon
PYTHONPATH=src uv run python -m unittest discover -s tests -p 'test_*.py' -v
```
