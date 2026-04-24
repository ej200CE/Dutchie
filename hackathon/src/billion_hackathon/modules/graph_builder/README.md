# Module: `graph_builder`

## Responsibility

Apply a **`GraphBlueprint`** to produce a **graph snapshot** (`nodes`, `edges`), run **inconsistency checks**, and expose an interactive graph UI where users can inspect, correct, and extend the graph before running computation.

## Main idea

Encodes graph invariants from the architecture: valid edge kinds, deduplication by `edge_id`, and checks that align with what `computation` will reject or warn on. Inconsistencies are surfaced visually so the user can fix problems before computing settlements.

## Interactive graph UI (tab 4)

The graph tab renders the snapshot as a D3 force-directed diagram:

| Element | Visual |
|---------|--------|
| Person node | Circle, Gruvbox blue |
| Good node | Rectangle, Gruvbox yellow |
| `cash_flow` edge | Solid orange arrow, labelled with amount |
| `contribution` edge | Dashed aqua arrow, labelled with share value |
| Inconsistent node | Red ring |
| Inconsistent edge | Red stroke |

### Editing

- **Click a node** → side panel shows editable `display_name`, `stated_total_cents` (goods only), and a Delete button.
- **Click an edge** → side panel shows editable `amount_cents` (cash flow) or `value` (contribution), plus Delete.
- **Rename a node** — changing the ID in the edit panel rewrites all referencing edges automatically.
- **Toolbar**: `+ Person`, `+ Good`, `+ Cash flow`, `+ Contribution` — add new nodes/edges via inline forms.

Every edit immediately calls `POST /api/dev/graph/validate` so inconsistency highlights update live.

The edited graph is available to the Compute tab via `GraphView.getGraph()` — "Load session graph" in Compute prefers the live edited version.

## Inconsistency codes

| Code | Severity | Meaning |
|------|----------|---------|
| `PRICE_MISMATCH` | error | `stated_total_cents` on a good differs from actual cash inflow |
| `NO_CONTRIBUTION_UNITS` | error | Good has spend but zero contribution shares |
| `CONTRIBUTIONS_WITHOUT_SPEND` | warning | Contributions defined but no cash_flow into good |
| `UNKNOWN_PAYER` | error | `cash_flow.from_id` doesn't match any person node |
| `BLUEPRINT_ERROR` | error | Invalid operation in the blueprint |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/dev/graph` | Build graph from `GraphBlueprint`, return snapshot + inconsistencies |
| `POST` | `/api/dev/graph/validate` | Validate a raw `{nodes, edges}` graph, return inconsistencies only |

## Contract

- Input: **`GraphBlueprint`** (build) or raw graph dict (validate)
- Output: graph snapshot `dict` + `list[Inconsistency]` — [`../../contracts/inconsistency.py`](../../contracts/inconsistency.py)

## Files

| File | Purpose |
|------|---------|
| `service.py` | Applies blueprint ops, calls inconsistency checker |
| `state.py` | Mutable graph state, `apply_blueprint_ops`, `to_snapshot` |
| `inconsistency.py` | `find_inconsistencies(graph)` — returns `list[Inconsistency]` |

## Examples

[`examples/`](examples/) — blueprint → `expected_graph.json`.
