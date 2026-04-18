# Architecture overview

*Draft — align with [`summarise.md`](../../summarise.md). Update as the implementation appears.*

## System context

Hackathon scope: *(one sentence: e.g. web app + bunq sandbox + local ledger).*

## Modules (responsibilities)

| Module | Responsibility | Notes |
|--------|-----------------|-------|
| Transaction ingestor | Pull/normalize transactions | Sources, refresh, errors |
| Context engine | Participants + group + confidence | Core product logic |
| Split engine | Shares and rules | Declarative rules, rounding |
| Ledger | Balances / who owes whom | Persistence, idempotency |
| Settlement | Optional auto-pay / netting | MVP may be manual-only |
| UI | Confirm / fix / explain | Thresholds drive UX |

## Boundaries

- What is **in scope** for the demo vs **deferred**.
- Where **PII** and **tokens** live; how config flows from `.env`.

## Data flow (sketch)

```text
Bank / API → Ingestor → Context engine → Split engine → Ledger → UI
```

Replace with a diagram or sequence when stable.

## Domain-centric pipeline (event + graph)

For the **time-bounded event** model—**transactional graph** (people, goods, cash-flow vs **contribution** edges), **Graph Builder**, **Context Engine**, and **Computational Engine**—see [`event-domain-and-graph.md`](event-domain-and-graph.md). That doc is the reference for how an Event scopes context and how balances are derived from the graph.
