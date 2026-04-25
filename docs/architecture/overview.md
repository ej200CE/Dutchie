# Architecture overview

Hackathon scope: a local FastAPI web app that turns raw trip evidence (photos, notes) into a settled expense graph. One tab per module in the dev UI; LLM calls go through a single shared client with a stub fallback.

## Pipeline

```
Uploads / notes
    │
    ▼
data_collection       → CollectedBundle   (EXIF, GPS, file storage)
    │
    ▼
data_ingestion        → EvidenceBundle    (LLM vision/text → evidence items)
    │                                      concurrent: one LLM call per item
    │                                      then deterministic post-process: payer/group merge,
    │                                      inferred-photographer drop, receipt-line consolidation
    ▼
evidence_aggregation  → GraphBlueprint    (LLM or rule-based → graph ops)
    │
    ▼
graph_builder         → graph snapshot    (apply ops, inconsistency checks)
    │   ↕ user edits (interactive graph UI — D3, click to edit)
    ▼
computation           → per-person net + suggested transfers   (deterministic)
```

## Modules

| Module | Status | Responsibility |
|--------|--------|---------------|
| `data_collection` | ✅ complete | Accept uploads & notes; extract EXIF (timestamp, GPS); produce `CollectedBundle`. No LLM. |
| `data_ingestion` | ✅ complete | Vision/text LLM → `EvidenceBundle`. Concurrent per-item calls (`aingest`). Stub fallback. Post-process fixes (group payer alignment, single-total receipt collapse for exploded menu lines). |
| `evidence_aggregation` | ✅ complete | Merge evidence, resolve persons/goods, build `GraphBlueprint`. LLM-assisted with rule fallback. |
| `graph_builder` | ✅ complete | Apply blueprint ops; inconsistency checks; interactive D3 graph UI with live editing. |
| `computation` | ✅ complete | Deterministic fair-share allocation + greedy pairwise transfers. No LLM. |
| `llm` | ✅ complete | Shared HTTP client for OpenAI-compatible, Anthropic, and stub providers. |

## Boundaries

**In scope (hackathon):**
- Photo/note ingestion → LLM evidence extraction → graph → settlement math
- Interactive graph correction (user edits nodes, edges, amounts)
- Stub mode when no API key configured

**Deferred:**
- Bank PSD2 / transaction ingestor (architecture defined; not yet wired)
- Multi-currency (one currency per event)
- Sub-events / nested goods
- Production auth, persistence, privacy/compliance

## Where things live

| Concern | Location |
|---------|----------|
| API endpoints | `main.py` |
| Session state | `main.py` `HackathonSession` (in-memory) |
| Scenario cache | `var/scenario_cache.json` |
| Uploaded files | `var/uploads/` |
| LLM config | `.env` (`BILLION_LLM_PROVIDER`, `BILLION_LLM_API_KEY`, `BILLION_LLM_MODEL`) |
| Contracts (Pydantic) | `contracts/` |

## Domain model

For the **transactional graph** — Person nodes, Good nodes, `cash_flow` and `contribution` edges, the Graph Builder invariants, and the Computational Engine formula — see [`event-domain-and-graph.md`](event-domain-and-graph.md).
