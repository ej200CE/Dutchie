# Vocabulary map

This document **aligns terms** across product specs, use cases, and the implementation-oriented architecture so the team speaks one language while older docs stay readable.

**Authoritative model for code and graph math:** [`event-domain-and-graph.md`](event-domain-and-graph.md).  
**Product vision (legacy naming):** root [`summarise.md`](../../summarise.md), [`Summarise 2.0.md`](../../Summarise%202.0.md).  
**Behavioural / UX spec:** [`USE_CASE_FORMAL_EN.md`](../../USE_CASE_FORMAL_EN.md) (and `USE_CASE_FORMAL.md`).

---

## 1. Time-bounded work unit

| Primary term (use in code & graph docs) | Same idea elsewhere | Notes |
|----------------------------------------|---------------------|--------|
| **Event** | **Trip** (use case), “weekend”, “gathering” | UI may say “Trip”; code may use `SettlementPeriod`, `Gathering`, etc. to avoid clashing with calendar or event-sourcing “events”. |
| **Time window** (start / end) | Trip dates, “during the trip”, event range | Single **currency per Event** in v1. |
| **Sub-event** | Nested “dinner inside weekend” | Optional; **not** required for first prototype. |

---

## 2. People

| Primary term | Same idea elsewhere | Notes |
|--------------|---------------------|--------|
| **Person** (node) | Participant, actor, “user” in use case, member of the trip | Identified by **`id`** in the hackathon model. |
| **Main / organizer user** | App user who creates the trip | May coincide with one **Person**; product detail. |

“**User**” in older specs often means **bank-connected account holder**; in the graph, **Person** is whoever can appear in splits (may be the same people under different roles).

---

## 3. Costs and money shape

| Primary term | Same idea elsewhere | Notes |
|--------------|---------------------|--------|
| **Good** (node) | Expense, cost line, receipt line, “split bucket”, dish line in OCR flow | **Flat list** in v1; receipt **line items** ≈ multiple **Goods**. Not the same as a raw **bank transaction** row (see below). |
| **Bank / card transaction** | PSD2 line, payment record | **Ingested** and matched to one or more **Goods** (or triggers creation of Goods). |
| **`cash_flow` edge** | “Who paid”, payer → expense, transfer | **Person → Good** (funded this cost) or **Person → Person** (**P2P**: loan, reimbursement, off-receipt). |
| **`contribution` edge** | Share of split, “who should bear” cost, rule outcome “equal among present” | Scalar **per Person–Good**: e.g. `0`, `0.5`, `1`, `≥2`. **Not** normalized to sum 1; see Computational Engine. |
| **Fair share** (computed) | “Their part of the bill”, allocated amount | Derived: \(c_i \times T_g / \sum c\) per good (see event-domain doc). |

---

## 4. Engines and layers (process names)

| Primary term | Older / parallel names | Role |
|--------------|------------------------|------|
| **Transaction Ingestor** | Bank sync, FR “expense filtering” | Pulls **transactions**; feeds Context Engine. |
| **Context Engine** | “Smart rules” + ML part of use case §5–6 | Ingests **context** (bank, photos, OCR, etc.), proposes **graph** edges; may use LLM for **initial estimate** only. |
| **Graph Builder** | *(often unnamed in product copy)* | Validates / edits **nodes and edges**; enforces structural rules. |
| **Computational Engine** | **Split Engine** (Summarise), “distribution algorithm” (use case §16–17), FR “calculations” | **Deterministic** math: fair shares from **contributions** + netting vs **cash_flow** (including P2P). |
| **Ledger** | “Who owes whom”, settlement table, balances | In architecture: usually **output + stored state** after compute (not always a separate named module in v1). |
| **Settlement** | bunq transfers, “pay back”, extension §8.1 | **Executing** payments; separate from **computing** balances. |
| **Timeline / narrative service** | “Presence timeline”, story of the trip | **Not** the Context Engine; may consume graph + context for UX. |

---

## 5. Legacy data-model names (Summarise / old brief)

| Old term | Maps to now | Notes |
|----------|-------------|--------|
| **Group** | Participants of an **Event** + optional shared settings | “Group” in old docs ≈ social grouping; **Event** scopes one reconciliation episode. |
| **Transaction** (model) | External **payment record** | Becomes evidence for **Goods** and **cash_flow**. |
| **Context** (generated) | Output of inference: participants, confidence | Close to **draft graph** or **edge proposals**, not only a struct with `group_id`. |
| **Split** | Per-transaction shares map | Maps to **per-Good contributions** + **Computational Engine** output across all goods. |

---

## 6. Use-case wording (USE_CASE_FORMAL)

| Use-case phrase | Architectural hook |
|-----------------|---------------------|
| “New Trip” | Create **Event** + participants |
| “Expense” / “restaurant expense” | **Good** (or several) + linked **cash_flow** |
| “Distribute equally among all” | Rule sets **contribution** scalars equal (e.g. all `1`) |
| “Excluded from expense” / “wasn’t there” | **contribution = 0** for that Person–Good |
| “Edit participant list” / “dish assignment” | **Graph** edit via **Graph Builder** |
| “Final settlement” / “who owes whom” | **Computational Engine** output (+ optional **Ledger** persistence) |

---

## 7. Confusing pairs (disambiguation)

| Term A | Term B | Distinction |
|--------|--------|-------------|
| **Event** (domain) | **event** in analytics / ES | Use code name **SettlementPeriod** or **Gathering** if confusion persists. |
| **contribution** | **cash_flow** | Contribution = **share of splitting burden**; cash_flow = **who actually moved money** (to good or P2P). |
| **Good** | **goods** (English plural) | **Good** = node type; “goods” = informal plural of cost items. |
| **Context** (bundle) | **Context** (old generated struct) | Bundle = inputs; old struct = narrow legacy shape—prefer **graph + provenance**. |

---

## 8. When you add new terms

1. Add a row here (or a short ADR if the choice is non-obvious).  
2. Use **one** primary term in new code; put synonyms in comments or this file only.  
3. Link specs that still use old names to this map or to [`event-domain-and-graph.md`](event-domain-and-graph.md).
