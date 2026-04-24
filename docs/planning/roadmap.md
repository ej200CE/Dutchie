# Roadmap

Use **phases** for order; keep **tasks** detailed in [`tasks.md`](tasks.md).

**Day 1 (parallel):** see [`hackathon-day1.md`](hackathon-day1.md) — frozen decisions, four owners, test layers.

## Phase 0 — Repo & alignment

- [x] Structure agreed, secrets via `.env`, docs in `docs/`
- [ ] Roles: Kirill (vision), Yehor & Klift & fourth dev (ingest/integration)
- [ ] `fixtures/demo/` committed; demo runs from clean clone

## Phase 1 — Spike / integration

- [ ] Run minimal bunq sandbox flow *(parallel to core tests — not blocking)*
- [ ] One happy-path transaction → normalized evidence JSON
- [ ] Pytest golden tests for `compute_engine` *(no bunq needed)*

## Phase 2 — MVP slice

- [ ] UC-001 documented; demo tells the same story
- [ ] Load event + graph (stub or bunq) → compute → suggested transfers in UI
- [ ] Correction path: graph patch still recomputes deterministically

## Phase 3 — Demo hardening

- [ ] Happy path reliable, fallback story if API fails
- [ ] Pitch + screenshots / script

---

**Review cadence:** Short sync after 1–2h (graph/evidence JSON); EOD demo dry-run.
