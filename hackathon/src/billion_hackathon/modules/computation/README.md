# Module: `computation`

## Responsibility

**Deterministic** settlement: from a graph snapshot (`person` / `good` nodes, `cash_flow`, `contribution` edges), compute **fair shares**, **per-person net**, and **suggested pairwise transfers**. **No LLM** here.

## Main idea

Implements the **Computational Engine** from architecture: per-good \(T_g\), contribution units, ceil rounding, then netting — same behaviour as [`demo-prototype`](../../../../../demo-prototype/README.md).

## Architecture links

- **Computational Engine** — [`event-domain-and-graph.md`](../../../../../docs/architecture/event-domain-and-graph.md) §6.
- **Split engine** naming — [`vocabulary-map.md`](../../../../../docs/architecture/vocabulary-map.md).

## Contract

Input: `dict` with `nodes`, `edges` (see [`examples/artifact_graph.json`](examples/artifact_graph.json)).  
Output: `compute()` result dict (`success`, `per_person`, `suggested_transfers`, …).

## Examples

[`examples/`](examples/) — `artifact_graph.json` → `expected_compute.json`.
