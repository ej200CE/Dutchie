# Billion hackathon — app

Python **FastAPI** backend and minimal **web UI**, split into modules that mirror [`../docs/architecture/overview.md`](../docs/architecture/overview.md) and the event/graph pipeline in [`../docs/architecture/event-domain-and-graph.md`](../docs/architecture/event-domain-and-graph.md).

## Feasibility (short)

| Track | Verdict |
|-------|---------|
| Kirill: full use case + golden artifacts | **Strong** — JSON under each `examples/` folder scales with UC-001…UC-n. |
| Python monorepo, `uv`, one command to run | **Strong** — see below. |
| LLM ingestion + aggregation | **Feasible** — ship **stub** implementations first (deterministic), swap in OpenAI/etc. behind the same **Pydantic contracts**. |
| Graph editing + inconsistency UX | **Feasible** — start with **API + JSON** + simple HTML; polish UI iteratively. |
| Everyone parallel | **Strong** — each module exposes a **contract** + **examples**; tests fail if someone breaks the shape. |

**Risk:** scope creep on “full LLM” day one — keep stubs until collection + graph + compute path is green.

**App overview (product + layout):** [`src/README.md`](src/README.md)

## Install `uv` (if you don’t have it)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart your shell or `source $HOME/.local/bin/env` (installer prints the exact line). Verify: `uv --version`.

## Setup

With **[uv](https://docs.astral.sh/uv/)** (recommended):

```bash
cd hackathon
uv sync
uv run uvicorn billion_hackathon.main:app --reload --host 127.0.0.1 --port 8080
```

With **pip** (editable install from repo root of `hackathon/`):

```bash
cd hackathon
pip install -e ".[dev]"
PYTHONPATH=src uvicorn billion_hackathon.main:app --reload --host 127.0.0.1 --port 8080
```

Open **http://127.0.0.1:8080** — the UI uses **tabs** (one per module + full pipeline) for parallel dev work.

### LLM end-to-end check (Story/1 and Story/2)

With a real key in the **repository root** `.env` (`BILLION_LLM_PROVIDER=openai`, `BILLION_LLM_API_KEY`, optional `BILLION_LLM_MODEL`):

```bash
cd hackathon
uv run python scripts/assess_scenarios_llm.py          # both stories
uv run python scripts/assess_scenarios_llm.py --story 1  # bar / three friends
```

Artifacts land under `hackathon/.cache/assess_runs/` (`storyN_evidence.json`, `storyN_graph.json`, …). The script **refuses** `provider=stub` so you always measure real vision + aggregation. If OpenAI returns **429**, wait and re-run; aggregation may fall back to rules for that call.

### Tests (golden `examples/`)

Uses **stdlib `unittest`** so you can run without pytest:

```bash
cd hackathon
PYTHONPATH=src uv run python -m unittest discover -s tests -p 'test_*.py' -v
```

*(Or `python3` if you used `pip install -e .` instead of `uv`.)*

## Layout

| Path | Role |
|------|------|
| `src/billion_hackathon/contracts/` | Shared **Pydantic** schemas between modules |
| `src/billion_hackathon/modules/data_collection/` | Uploads + notes → `CollectedBundle` |
| `src/billion_hackathon/modules/data_ingestion/` | Raw bundle → structured **evidence** (LLM or stub) |
| `src/billion_hackathon/modules/evidence_aggregation/` | Evidence → **graph build instructions** |
| `src/billion_hackathon/modules/graph_builder/` | Apply instructions + **inconsistency** report |
| `src/billion_hackathon/modules/computation/` | Deterministic balances (same math as `demo-prototype`) |
| `src/billion_hackathon/modules/llm/` | **Single module** for model requests (`stub`, OpenAI-compatible, Anthropic) |
| `src/billion_hackathon/web/` | Jinja templates + static assets (dev tabs UI) |
| `tests/` | Contract tests driven by each module’s `examples/` |

## Module examples

Each module has an **`examples/`** directory: **artifact** (input) and **expected** (output).  
`tests/test_module_examples.py` loads them and asserts the pipeline matches — extend with Kirill’s fixtures as you add use cases.

## Team

- **Klift, Yehor, Cynthia** — own modules against shared **contracts**; swap **stub** ingesters/aggregators for real LLM calls when keys are ready (same JSON shapes).
- **Kirill** — richer `examples/` + formal use cases under `docs/use-cases/` (artifacts should match `contracts/`).

Suggested ownership: **Cynthia** — `data_collection` + bunq → evidence bridge · **Yehor** — `computation` + `graph_builder` · **Klift** — `data_ingestion` + `evidence_aggregation` + API/UI glue *(flexible)*.
