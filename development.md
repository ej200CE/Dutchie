# Billion Idea — bunq Hackathon 2026

Automated group expense splitting. Upload photos, receipts, and notes from a shared outing; get back a minimal set of bank transfers to settle everyone's tab — with 80–95% of the work done automatically.

## How it works

Raw evidence (photos, receipts, text notes) flows through a six-stage pipeline:

```
Uploads + notes
    │
    ▼
data_collection      → CollectedBundle      (EXIF parsing, file storage)
    │
    ▼
data_ingestion       → EvidenceBundle       (vision/text LLM → structured evidence)
    │
    ▼
evidence_aggregation → GraphBlueprint       (merge evidence, resolve identity)
    │
    ▼
graph_builder        → Graph snapshot       (apply ops, flag inconsistencies)
    │
    ▼
computation          → Balances + transfers (deterministic fair-share maths)
```

The LLM only touches the ingestion stage. Everything downstream — graph building, balance calculation, transfer minimisation — is deterministic and fully testable without an API key.

## Quick start

**Requirements:** Python 3.11+, [`uv`](https://docs.astral.sh/uv/)

```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and configure
git clone <repo>
cd billion_idea
cp .env.example .env        # fill in secrets (file is gitignored)

# Run the app
cd hackathon
uv sync
uv run uvicorn billion_hackathon.main:app --reload --host 127.0.0.1 --port 8080
```

Open **http://127.0.0.1:8080** — the UI has a tab per module for isolated testing, plus a full end-to-end pipeline tab.

### Without uv (pip)

```bash
cd hackathon
pip install -e ".[dev]"
PYTHONPATH=src uvicorn billion_hackathon.main:app --reload --host 127.0.0.1 --port 8080
```

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Default | Purpose |
|---|---|---|
| `BILLION_LLM_PROVIDER` | `stub` | `stub`, `openai`, or `anthropic` |
| `BILLION_LLM_API_KEY` | — | API key for your chosen provider |
| `BILLION_LLM_MODEL` | auto | Model name (defaults: `gpt-4o` / `claude-3-5-sonnet`) |
| `BILLION_LLM_BASE_URL` | — | Override for OpenAI-compatible endpoints |
| `BUNQ_API_KEY` | — | bunq sandbox key (future) |
| `BUNQ_ENV` | `sandbox` | `sandbox` or `production` |

`stub` mode is the default — the full pipeline runs offline with deterministic outputs, no API key needed.

## Running tests

Tests are golden-fixture driven: each module ships `examples/` pairs (artifact → expected output), and the test suite asserts the pipeline matches.

```bash
cd hackathon
PYTHONPATH=src uv run python -m unittest discover -s tests -p 'test_*.py' -v
```

### End-to-end LLM assessment (real key required)

```bash
cd hackathon
uv run python scripts/assess_scenarios_llm.py            # both stories
uv run python scripts/assess_scenarios_llm.py --story 1  # bar / three friends
uv run python scripts/assess_scenarios_llm.py --story 2  # restaurant / four people
```

Results land in `hackathon/.cache/assess_runs/`. The script refuses `provider=stub` so you always measure real vision accuracy.

## Repository layout

```
billion_idea/
├── hackathon/                        # Main app
│   ├── src/billion_hackathon/
│   │   ├── contracts/                # Shared Pydantic schemas
│   │   ├── modules/
│   │   │   ├── data_collection/      # Uploads + notes → CollectedBundle
│   │   │   ├── data_ingestion/       # LLM vision/text → EvidenceBundle
│   │   │   ├── evidence_aggregation/ # Evidence → GraphBlueprint
│   │   │   ├── graph_builder/        # Blueprint → graph + inconsistencies
│   │   │   ├── computation/          # Deterministic balances + transfers
│   │   │   └── llm/                  # Unified LLM client (stub/OpenAI/Anthropic)
│   │   └── web/                      # Jinja templates + static assets
│   └── tests/                        # Golden fixture tests
├── docs/
│   ├── architecture/                 # Domain model, pipeline, ADRs
│   ├── planning/                     # Hackathon day-1 plan, roadmap
│   └── use-cases/                    # Formal user scenarios (UC-001…)
├── Story/
│   ├── 1/                            # Bar scenario: 3 friends, receipt + selfie
│   └── 2/                            # Restaurant: 4 people, 1 payer
├── demo-prototype/                   # Earlier standalone implementation
├── scripts/                          # Setup and automation (bunq auth, etc.)
└── .env.example                      # Config template
```

## Graph model

Expense relationships are modelled as a bipartite graph.

**Nodes:**
- **Person** — a participant (`alice`, `group_pos_2`, `inferred_photographer_1`)
- **Good** — a shared cost (`carbonara`, `shared_taxi`, `groceries`)

**Edges:**
- `cash_flow` — who paid (Person → Good, or Person → Person for direct payments)
- `contribution` — who shares a cost (Person → Good, value = relative units)

**Invariants checked at build time:**
- Each Good must have at least one contribution (`NO_CONTRIBUTION_UNITS`)
- Cash flows into a Good must match its stated total (`PRICE_MISMATCH`)

Inconsistencies surface in the UI for user correction before computation runs.

## Adding a new use case

1. Add an `artifact_<type>.json` + `expected_<type>.json` pair under the relevant module's `examples/` directory.
2. Run the test suite — it auto-discovers all fixture pairs.
3. No code changes needed unless you're introducing a new evidence kind.

## Team

| Person | Focus |
|---|---|
| **Kirill** | Product vision, use cases, golden artifacts |
| **Yehor** | `computation`, `graph_builder` |
| **Klift** | `data_ingestion`, `evidence_aggregation`, API/UI glue |

Full architecture: [`docs/architecture/overview.md`](docs/architecture/overview.md)  
Domain model: [`docs/architecture/event-domain-and-graph.md`](docs/architecture/event-domain-and-graph.md)  
Product brief: [`summarise.md`](summarise.md)
