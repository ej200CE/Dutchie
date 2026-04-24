# Module: `evidence_aggregation`

## Responsibility

Merge **`EvidenceBundle`** into a **`GraphBlueprint`**: ordered **`add_node` / `add_edge`** operations that the **graph_builder** applies. Today this is **rule-based**; later it can use the **`llm`** module to propose operations from ambiguous evidence.

## Main idea

This is the **“instructions to build the graph”** step: it does not compute balances; it only proposes **structure** (people, goods, `cash_flow`, `contribution`) consistent with [`event-domain-and-graph.md`](../../../../../docs/architecture/event-domain-and-graph.md) §4.

## Architecture links

- **Graph Builder** (conceptual) — same doc §5.  
- **Contribution** vs **cash_flow** — §4.2.

## Contract

- Input: **`EvidenceBundle`**  
- Output: **`GraphBlueprint`** — [`../../contracts/graph_blueprint.py`](../../contracts/graph_blueprint.py)

## LLM

Use [`../llm/README.md`](../llm/README.md) for any model calls; keep the **blueprint schema** stable so tests and UI do not break.

## Examples

[`examples/`](examples/) — `artifact_evidence.json` → `expected_blueprint.json`.
