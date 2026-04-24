# Module: `graph_builder`

## Responsibility

Apply a **`GraphBlueprint`** to produce a **graph snapshot** (`nodes`, `edges`) and run **inconsistency checks** (e.g. price vs inflow, missing contribution units) for **dev UI highlighting** and future “fix me” flows.

## Main idea

Encodes **Graph Builder** invariants from architecture: valid edge kinds, deduplication by `edge_id`, and checks that align with what **`computation`** will reject or warn on.

## Architecture links

- **Graph Builder** — [`event-domain-and-graph.md`](../../../../../docs/architecture/event-domain-and-graph.md) §5.  
- **Inconsistencies** / user edits — §4.4, §5.1.

## Contract

- Input: **`GraphBlueprint`**  
- Output: `dict` snapshot + `list[Inconsistency]` — [`../../contracts/inconsistency.py`](../../contracts/inconsistency.py)

## Examples

[`examples/`](examples/) — blueprint → `expected_graph.json`.
