# Event, context, and transactional graph

This document describes the **domain model** and **processing pipeline** for resolving shared expenses inside a **time-bounded situation** (trip, weekend, festival, flat share period, etc.). It is the conceptual backbone for later API and module design.

Related: product vision in [`../../summarise.md`](../../summarise.md); high-level module list in [`overview.md`](overview.md).

---

## 1. Problem in one sentence

Users need to answer, for a **defined slice of time and group**: who was involved, who paid for which costs, how each person **contributes** to each cost, and **what net amounts** each person owes or should receive—so the group can settle up (including via bank tools later).

---

## 2. Event (time-bound container)

An **Event** is the container that bounds **transactions and situational context** relevant to that resolution.

| Property | Description |
|----------|-------------|
| **Time window** | **Start** and **end** timestamps, supplied by the primary app user. All automated context collection is anchored to this window (and possibly a small configurable margin). |
| **Participants** | A list of **people** who are party to the transactional relationships for this event. Each person is identified by a stable **id** in the hackathon model (no cross-source identity resolution required initially). They are the actors in the graph (see below). |
| **Currency** | **One currency per event** for the prototype (no multi-currency in v1). |
| **Context bundle** | Evidence assembled to infer *who was present*, *what was bought*, and *how costs should be split*. Sources include: bank/PSD2 transaction history, photos, call logs, geolocation traces, screenshots, receipt images, images of people, timestamps, and any other signals the product chooses to ingest. |
| **Transactional graph** | A structured model (nodes and edges) representing **money flows** (including **P2P**) and **per-person contribution** to each good. Built automatically, then **editable** by users when the model is wrong. |

**Intuition:** the Event is not “a payment” but a **scenario**—the lens through which raw data becomes a fair split story.

### Naming in code and docs (alternatives to “Event”)

The word **event** is overloaded (calendar, event sourcing, analytics). For implementation and APIs, pick one domain term and use it consistently. Candidates:

| Name | Connotation |
|------|-------------|
| **Settlement period** | Emphasizes reconciliation and money outcome. |
| **Gathering** | Social trip / group context. |
| **Trip** | Travel-heavy scenarios (too narrow if you want flatmates). |
| **Spend session** | Time-bounded spending episode. |
| **Reconciliation window** | Formal; matches “who owes whom.” |
| **Group spend** | Product-flavoured; may collide with “group” entity. |
| **Occasion** | Neutral; short. |

Internal code might use `SettlementPeriod` or `Gathering` while the UI still says “Event” if that reads better for users.

### Sub-events (optional, later)

**Sub-events** (nested windows, e.g. “dinner” inside “weekend”) are **not required** for the first prototype. With ~**24 hours** for a hackathon build, keep a **flat** event + goods list; add nesting only if it clearly simplifies the demo.

---

## 3. Context and the Context Engine

**Context** answers: *whom, when, and paid for what* (and optionally *who was physically or socially present*).

- **Ingestion:** For each participant (and possibly the organizer’s device), pull or reference data **restricted to the event window** where possible: e.g. transactions in range, photos with EXIF in range, location history samples, etc.
- **Heterogeneous signals:** Different modalities (tabular finance vs images vs text) require **normalization** into a common internal representation before graph construction.
- **Reasoning:** Some situations are too messy for pure rules. An **LLM-assisted** layer produces an **initial estimate** only: attributions (e.g. sub-periods by who appears in photos), mapping receipt text to candidate goods, participant subsets for a charge. Output is always revisable; reliability limits are expected, which is why **graph editing** is first-class.

The **Context Engine** is responsible for:

1. Ingesting context of supported **types** (extensible pipeline).
2. Producing or updating a **draft graph** via a **Graph Builder** (see below).
3. Attaching **context references** (see §4.2) so edges and goods can be traced back to source material.
4. Exposing **confidence** where useful so the UI can explain “why” and users can correct confidently.

**Output:** The Context Engine produces the **graph** only. A **timeline narrative** (human-readable story of the event) can be built by **another service or layer** from the same inputs or from the graph—out of scope for the Context Engine itself.

**Example (informal):** Photos suggest two people on day 1 and three on day 2. The engine may scope **transaction analysis** to the relevant people per sub-period, reducing cross-noise between subgroups.

---

## 4. Graph model

### 4.1 Nodes (two kinds)

1. **Person nodes**  
   Represent participants (including “self” vs others if the product distinguishes the main user). Each person has a stable **id** (and display name as needed). They participate in **cash flows** and **contribution** relationships.

2. **Good / item / service nodes** (working name: **Good**)  
   Represent concrete or abstract costs: beer, rent for one night, groceries, a shared taxi, etc. For the prototype, use a **flat list** of goods (KISS); optional `parent_id` or grouping can be added later without breaking the core model.

*Naming note:* “Transaction agent” in brainstorming maps to **person** in this graph; if you need a separate node for “merchant” or “external payer,” that is a future extension and would need extra rules.

### 4.2 Edges (two types)

**A. Cash-flow edge** (`cash_flow`)

- **Person → Good:** Money moved from a **person** toward paying for a **good** (who funded that cost).
- **Person → Person (P2P):** **Allowed.** Direct transfers (loans, reimbursements, off-receipt payments) that should affect balances without going through a good. **Attributes:** directed flow, **amount**, currency, optional metadata (payment id, timestamp).
- **Role:** Encodes *who actually paid* how much, toward a good **or** to another person.

**B. Contribution edge** (`contribution`)

- **Meaning:** How much this **person** should count toward **splitting** the cost of that **good**—not necessarily normalized; this is the key to “pay for everyone,” “only two people,” “I’m out,” etc.
- **Only** between **Person** and **Good** (no Person–Person contribution edges).
- **Value (scalar per person–good):**
  - **`1`** — normal contribution (one “unit” in the split).
  - **`0.5`** — half a unit (e.g. child share, half portion).
  - **`0`** — **no** contribution: this person does not participate in splitting that good’s cost (and when someone removes themselves, their contribution becomes **0**; the Computational Engine recomputes everyone else’s fair shares from the remaining contributions—**no** manual redistribution of “weights that sum to 1” required).
  - **`2` or higher** — counts as multiple units (e.g. one person represents or pays for the share of two or more people in the split).

**There is no “sum to 1” invariant** on contributions. Sums can be arbitrary positive totals; the **Computational Engine** turns contributions into money shares (see §6).

**Optional UX:** Users may still edit **explicit monetary amounts** per person on a good in the UI; the Graph Builder can translate those into equivalent contribution values **or** store amounts as auxiliary fields—pick one path in the schema and stick to it for the prototype.

**Provenance:** Store a **`context_id`** (or list of ids) on **contribution** and **cash_flow** edges and/or on the **good**, pointing to the ingested context blob (bank line, photo id, manual entry, etc.) so you can audit *why* an edge exists.

**Direction convention:** Pick one (e.g. **Good → Person** with scalar `contribution`, or **Person → Good**). Stay consistent in code and in the Computational Engine.

### 4.3 What this can express

| Situation | How it appears in the graph |
|-----------|-------------------------------|
| A paid for food split among self and three others equally | `cash_flow`: A → Food. `contribution`: four people × **1** (sum = 4). |
| A paid but did not eat | `cash_flow`: A → Food. A’s `contribution` = **0**; others carry the split among themselves. |
| A treats everyone (others owe nothing for that good) | Others’ `contribution` = **0**; A’s `contribution` > 0 **or** handle via cash_flow vs fair share netting (see §6). Using **contribution** alone: if only A should bear the cost, set A as the only person with positive contribution **or** encode “gift” in policy—team choice for edge cases. |
| Loan / P2P not tied to a good | `cash_flow`: Person → Person. |

The graph stays **flexible**; corner cases (e.g. all contributions **0** but money was paid) need an explicit rule in the Computational Engine (warning, fallback, or block save).

### 4.4 Granularity: subgoods and edits

- **Flat list of goods** for the hackathon; **subgoods** can be separate rows in that list (line items) if needed—avoid deep trees until necessary.
- **Removing oneself:** set **`contribution` = 0** on that Person–Good edge; the Computational Engine allocates cost only across people with **contribution > 0** (per good).
- If the UI previously used **amounts** instead of scalars, map edits back into **contribution** or keep amounts as the source of truth and derive fair shares in one place.

---

## 5. Graph Builder

A **Graph Builder** module maintains the graph and **enforces invariants**, for example:

- **Contribution** edges only **Person–Good**; **cash_flow** may be **Person–Good** or **Person–Person**.
- No **Good–Good** edges in v1 (ordering of flat goods is a list concern, not a graph edge).
- **Cash_flow** amounts non-negative (unless you allow explicit negatives for reversals—define in an ADR).
- **`context_id`** present when you want strict traceability (optional for the very first spike).

It supports **add/remove node**, **add/remove/update edge**, and validation hooks for UI. **Manual correction** covers gaps where bank APIs have no record (e.g. cash): users add or adjust **cash_flow** edges directly.

---

## 5.1 Hackathon scope

For this project we **assume** participants agree to the demo’s data and consent story; detailed privacy and compliance work is **out of scope** for now. The architecture keeps **editability** of the graph so LLM mistakes, missing bank lines, and edge cases are handled by **user modification**, not only by automatic inference.

---

## 6. Computational Engine

The **Computational Engine** is **deterministic**: given the same graph and policy (rounding, gifts, ignored cents), outputs are reproducible. **LLMs stay upstream** (Context Engine only).

### Per-good allocation from contributions

For each **Good** \(g\):

1. Determine **total cost** \(T_g\) — typically from the sum of **cash_flow** into that good, or from a **price** field on the good if you store it explicitly (align with your schema).
2. Let \(c_i\) be person \(i\)’s **contribution** to \(g\) (missing edge or zero means \(c_i = 0\)).
3. Let \(S_g = \sum_i c_i\).
4. If \(S_g > 0\), define **cost per contribution unit**: \(\text{cpu}_g = T_g / S_g\). Person \(i\)’s **fair share** of that good’s cost is \(c_i \times \text{cpu}_g\).

This single rule covers **equal splits** (all \(c_i = 1\)), **weighted splits** (mix of 0.5, 1, 2, …), **“I’m out”** (\(c_i = 0\)), and **paying for multiple people’s share** (\(c_i \geq 2\)) in one framework.

### Netting across goods and P2P

- Sum **cash out** per person (to goods + P2P) vs **sum of fair shares** of goods (and any P2P semantics you define).
- Produce **per-person net balance** and **suggested settlements** (e.g. pairwise minimal transfers).

**Gifts / “I pay for everyone”:** Often show up as **others’ contributions = 0** while one person funded the good; netting then leaves others owing that person, **unless** you zero out reimbursement via policy. **Contribution values encode intent** for how split burden is shared; edge cases where both **\(S_g = 0\)** and **\(T_g > 0\)** need a defined behaviour (error, assign 100% to payer, etc.).

### Why this model works (design note)

Using **unbounded positive contributions** instead of **weights summing to 1** avoids awkward rescaling when someone drops out: **set contribution to 0** and recompute. The formula is easy to explain in the UI (“units” of split). Remaining risk: **\(S_g = 0\)** with non-zero cost—handle explicitly in product logic.

---

## 7. End-to-end flow

```text
Create Event (window + participants, single currency)
    → Load context (transactions, media, location, …)
    → Context Engine proposes graph (Graph Builder + LLM assist where needed)
    → User reviews and edits graph (contributions, cash_flow, P2P)
    → Computational Engine outputs balances / settlement suggestions
```

Optional: **Timeline narrative** service runs beside or after, not inside the Context Engine.

---

## 8. Resolved decisions (quick reference)

| Topic | Decision |
|-------|----------|
| P2P | **Allowed:** `cash_flow` **Person → Person**. |
| Gifts / uneven splits | Encoded via **contribution** scalars (e.g. others 0, one person bears the split; exact gift semantics + netting policy as needed). |
| Currency | **One currency per event** for now. |
| Sub-events | **Optional later**; **flat event** for ~24h prototype. |
| “Good total vs cash_flow” (old Q5) | *Meant:* should money paid into a good always match a stored price? For the hackathon, **keep it simple:** e.g. **\(T_g\)** = sum of **cash_flow** into the good, **or** a single price on the good if you don’t model partial payments—document the chosen rule in the schema. |
| Provenance | **`context_id`** on edges and/or goods to link to ingested context. |
| Context Engine output | **Graph only**; timeline narrative = **separate** concern. |
| Person–Good split edge | Named **contribution** (see §4.2). |
| Subgoods schema | **Flat list**; extensible later. |
| Someone removes themselves | **contribution → 0**; Computational Engine **recalculates** without requiring weights that sum to 1. |

---

## 9. Next steps (when you are ready)

- Freeze **edge directions**, **\(T_g\)** definition (price field vs sum of flows), and **\(S_g = 0\)** behaviour in an ADR.
- Define **minimal** JSON/schema for `Event`, `Person`, `Good`, `Edge` (`cash_flow` | `contribution`) for the hackathon MVP.
- Sketch **Computational Engine** on 2–3 toy graphs (including P2P and contribution 0).

This document should evolve; major changes deserve a dated note or an ADR reference.
