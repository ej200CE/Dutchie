# Module: `computation`

## Responsibility

**Deterministic** settlement: given a graph snapshot (`person` / `good` nodes plus `cash_flow` and `contribution` edges), compute **per-person fair shares**, **net balances**, and **minimal pairwise transfers**. No LLM, no external calls.

## Algorithm

### 1. Per-good cost allocation

For each **Good** node *g*:

1. `T_g` = sum of all `cash_flow` edges whose `to_id == g.id` (actual money paid toward that good).
2. `contribs` = map of `person_id → value` from all `contribution` edges for that good.
3. `S_g` = sum of all contribution values.
4. If `S_g > 0` and `T_g > 0`: each person's **fair share** of *g* = `T_g × (c_i / S_g)`, rounded up to the nearest cent (ceiling).

Setting `contribution.value = 0` removes a person from the split without touching anyone else's values — the engine re-normalises automatically.

### 2. Net balance per person

```
net_cents = paid_out_cents − fair_share_owed_cents
```

- `paid_out_cents` = sum of all `cash_flow` edges where `from_id == person` (goods + P2P).
- `fair_share_owed_cents` = sum of fair shares across all goods with `contribution > 0`.
- Positive net → creditor (owed money). Negative net → debtor (owes money).

> **P2P note:** a `cash_flow` Person → Person increases the payer's `paid_out` but does not directly credit the recipient. P2P is treated as a forward payment (loan / reimbursement) whose full settlement impact is captured in the net balance — the recipient's share of goods they contributed to is unchanged.

### 3. Suggested transfers (greedy pairwise)

Sort debtors descending by amount owed, creditors descending by amount owed to them.  
Repeatedly match the largest debtor to the largest creditor, transferring `min(debtor_amount, creditor_amount)`.  
This minimises the number of transfers.

## Error codes

| Code | When |
|------|------|
| `PRICE_MISMATCH` | `good.stated_total_cents` ≠ sum of cash_flow into that good |
| `NO_CONTRIBUTION_UNITS` | Cash was paid into a good, but all contribution values are 0 |

Both errors abort computation — the result has `success: false` and `errors: [...]`.

## Output contract

```json
{
  "success": true,
  "errors": [],
  "per_person": [
    {
      "person_id": "alice",
      "display_name": "Alice",
      "paid_out_cents": 12000,
      "fair_share_owed_cents": 4000,
      "net_cents": 8000
    }
  ],
  "suggested_transfers": [
    { "from_person_id": "bob", "to_person_id": "alice", "amount_cents": 4000 }
  ],
  "diagnostics": []
}
```

## UI (Compute tab)

- **Run compute** uses the live graph from the Graph tab (`GraphView.getGraph()`) automatically, falling back to the override textarea, then to the session's last built graph.
- Results are displayed as **per-person cards** — name, paid / share / net, coloured green (creditor) or red (debtor).
- Below the cards: **Suggested transfers** list — "Bob → Alice €40.00".
- If `success: false`, error codes and messages are shown instead.

## Contract

Input: `dict` with `nodes` and `edges`.  
Output: result dict — see `examples/expected_compute.json`.

## Files

| File | Purpose |
|------|---------|
| `engine.py` | `compute(graph)` — deterministic settlement |

## Examples

[`examples/`](examples/) — `artifact_graph.json` → `expected_compute.json` (alice pays for groceries, bob + carol owe €40 each).
