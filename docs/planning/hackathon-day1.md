# Hackathon day 1 — kickoff (4 people)

Single place for **frozen decisions**, **parallel ownership**, and **test order** so nobody waits on a mythical “big bang” integration.

---

## 1) Decisions locked for the sprint

These complete open gaps from [`../architecture/event-domain-and-graph.md`](../architecture/event-domain-and-graph.md) §9 and align with what the **demo prototype** already implements.

| Topic | Decision | Rationale |
|--------|-----------|-----------|
| **Stack** | **Python 3.11+, FastAPI, Pydantic, Jinja** in [`demo-prototype/`](../../demo-prototype/README.md) | Code exists; changing stack burns the first day. |
| **MVP story vs full automation** | **Graph-in + compute-out** with user edits; ingestion can be **stub or bunq** | Architecture treats LLM/bank as upstream; USE_CASE_FORMAL describes full auto **as north star**, not day-1 scope. |
| **Domain name in code** | **`Event`** in JSON/fixtures; if “event” clashes in Python, use a type alias like `GatheringId` only where needed | Vocabulary map allows UI “Trip” + code synonym. |
| **Total cost \(T_g\)** | **Sum of `cash_flow` into the good** (cents). Optional `stated_total_cents` on the good must match or **`PRICE_MISMATCH`** | Matches [`compute_engine.py`](../../demo-prototype/app/compute_engine.py). |
| **`S_g = 0` with money in** | **Hard error `NO_CONTRIBUTION_UNITS`** (no silent fallback) | Matches current engine; UI shows correction. |
| **Contribution storage** | Edges with `kind: contribution`, `good_id`, `person_id`, `value` (float) | Matches prototype; not “weights summing to 1”. |
| **Rounding** | **`ceil` per person per good** on allocated cents | Characterization tests must lock this to avoid drift. |
| **P2P `cash_flow`** | **Allowed in the domain**; **verify** how `paid_out` counts person→person edges in the prototype and add tests for the **intended** semantics | May need a small fix; tests clarify first. |
| **Fixtures** | **`fixtures/demo/` at repo root** is canonical for the demo | Currently missing in some clones — **restore or add minimal JSON** on day 1. |
| **Secrets** | **`.env`** only; never commit | [`README`](../../README.md). |
| **Language** | **English** for formal use-case + architecture; team chat RU/EN as you prefer | [`docs/README`](../README.md). |

**Still optional (post-MVP):** timeline narrative service, sub-events, multi-currency, real LLM receipt flow.

---

## 2) Four people — tasks (minimal blocking)

Names below match [`README`](../../README.md) and [`tasks.md`](tasks.md) (**Cynthia** = integrations).

| Person | Day-1 focus | Definition of done |
|--------|-------------|---------------------|
| **Kirill** | **Scope + story**: lock hackathon MVP bullets; add **UC-001** (e.g. restaurant equal split) under [`docs/use-cases/`](../use-cases/README.md); 5-slide / demo script outline | Judges can repeat the story without reading code |
| **Klift** | **Coordination + integration**: restore **`fixtures/demo/*.json`**; own **API contract** (response shapes for load/compute); unblock bunq spike with env checklist | `uv run uvicorn …` works end-to-end from fresh clone |
| **Yehor** | **Core correctness**: **`pytest`** for `compute_engine` + `graph_service` with golden graphs (equal split, someone at 0 contribution, PRICE_MISMATCH, NO_CONTRIBUTION_UNITS) | CI-ready test module; no HTTP required |
| **Cynthia** | **External I/O**: bunq **sandbox spike** (auth + list payments); sketch **normalizer** from bunq row → internal “evidence” dict (no merge to graph until shape agreed) | Doc or module with sample output JSON |

**Sync points (short):** (1) After **1–2h** — JSON field names for graph + evidence. (2) Before EOD — demo path runs with real or stub ingest.

Pairing is fine; **default split** above avoids two people editing the same file on hour zero.

---

## 3) Test roadmap (parallel-friendly)

Order is **dependency**, not time: several layers run **in parallel** once Layer 0 is done.

```text
Layer 0 — Contract (whole team, ≤30 min)
   └─ Sample Event + Graph JSON committed under fixtures/demo/

Layer 1 — Pure unit (Owner: Yehor)          │  Layer 2 — HTTP API (Owner: Klift)
   └─ compute_engine.compute(graph)           │     └─ TestClient: load fixture → POST compute
   └─ graph patch apply / invariants          │     └─ Assert status + shape (not exact copy)

Layer 3 — Ingest / bunq (Owner: Cynthia)     │  Layer 4 — Acceptance (Owner: Kirill + any)
   └─ Mock HTTP or sandbox smoke              │     └─ UC-001 steps → expected balances
   └─ Normalizer output matches fixture schema │     └─ “Locked run” behaviour per demo README
```

**Anti-blocking rules**

- **No waiting for bunq** to write Layer 1 tests — use static JSON only.
- **No waiting for UI** to test the engine — call `compute()` directly.
- **API tests** use committed fixtures, not live sandbox.

**Suggested pytest layout (when added)**

```text
demo-prototype/tests/
  test_compute_engine.py    # golden files in tests/fixtures/*.json
  test_graph_service.py
  test_api_compute.py       # optional: httpx AsyncClient / TestClient
```

Add **`pytest`** (and **`httpx`** if testing FastAPI) to `[tool.uv]` dev-dependencies when Yehor/Klift wire this up.

---

## 4) Checklist before “we’re coding”

- [x] Fourth person (**Cynthia**) in [`tasks.md`](tasks.md) and [`README`](../../README.md)
- [ ] `fixtures/demo/` present with at least **event-sample**, **graph-sample** (or equivalent names wired in `demo_data.py`)
- [ ] `.env.example` has every key the bunq spike needs
- [ ] One **ADR** or a paragraph in [`../architecture/overview.md`](../architecture/overview.md) listing stack + `T_g` + rounding (can be 15 minutes)

---

## References

- Graph math & pipeline: [`../architecture/event-domain-and-graph.md`](../architecture/event-domain-and-graph.md)
- Terms: [`../architecture/vocabulary-map.md`](../architecture/vocabulary-map.md)
- Formal behaviour ideas: [`../USE_CASE_FORMAL_EN.md`](../USE_CASE_FORMAL_EN.md)
- Running demo: [`../../demo-prototype/README.md`](../../demo-prototype/README.md)
