# Mobile UI — Design Document

A mobile-first web UI for zero-input expense splitting. The backend pipeline already exists; this UI is the human face on top of it.

---

## Design principles

- **One action per screen.** Never show two heavy choices at once on a small screen.
- **Progressive disclosure.** Show the happy path first; reveal editing controls only when needed.
- **Optimistic feedback.** Respond immediately to taps; confirm with the server in the background.
- **Session-backed state.** The server holds pipeline state in a session cookie — screens don't need to pass data to each other manually.

---

## Tech stack

**Primary: HTMX + Tailwind CSS**
- Extend the existing FastAPI + Jinja2 backend — no new language, no build step.
- HTMX handles server-driven partial page updates (swap in result fragments without a full reload).
- Tailwind provides mobile-first utility classes (`sm:`, `md:` breakpoints, touch-friendly tap targets).

**Backup: React + Tailwind (Vite SPA)**
- Separate frontend talking to FastAPI via REST.
- Better for the D3 graph editor on mobile (touch event handling, complex state).
- Adds JS toolchain overhead — only worthwhile if graph editing is a demo centrepiece.

---

## Screen flow

```
[1. Create event]
      │
      ▼
[2. Add evidence]  ←──────────────────────────────┐
      │                                            │ add more
      ▼                                            │
[3. Processing]  (spinner, POST /api/pipeline/run) │
      │                                            │
      ├── errors/low-confidence ──► [fix evidence]─┘
      │
      ▼
[4. Review graph]  (edit persons, goods, connections)
      │
      ├── edits made ──► [re-run compute, notify others]
      │
      ▼
[5. Confirm]  (each person confirms their share)
      │
      ▼
[6. Final bill]  (settlement summary + payment links)
```

---

## Screen 1 — Create event

**Purpose:** Name the outing and set who's involved.

**Fields:**
- Event name (text input, e.g. "Amsterdam dinner", "Weekend trip")
- Participants — freetext names, one per line, or a chip-based tag input

**UX notes:**
- Keep it short: just name + people. Date/location are extracted from evidence later (EXIF, LLM).
- "Who's in this?" is the minimum viable input.

**API:** No dedicated endpoint yet. Store name + participant list in session or extend `POST /api/collect/note` with a structured note like `EVENT: Amsterdam dinner\nPEOPLE: Alice, Bob, Cynthia`.

---

## Screen 2 — Add evidence

**Purpose:** Collect all raw material for the split.

### Evidence types

**1. Photos** (primary path)
- Receipt / bill → LLM reads items + prices
- Group photo → LLM identifies faces/names, infers who was present
- Screenshot of a bank transaction → parsed as a payment record

Tap-to-upload or camera capture. Show a thumbnail grid as items land.
Each thumbnail shows: file type icon, EXIF timestamp if found, GPS pin if found.

**API:** `POST /api/collect/upload` (multipart)  
Returns updated `CollectedBundle`; re-render the thumbnail grid via HTMX swap.

**2. Text note**
White textarea. User types free context: "Alice paid for the taxi, Bob covered dessert".
Structured shorthand also works: `EXPENSE: taxi 24.50 Alice`.

**API:** `POST /api/collect/note`  
Returns updated bundle.

**3. Voice** *(not yet wired to backend — future)*
Record → transcribe → treat as a text note.
Until the transcription endpoint exists, show this as greyed-out / coming soon.

### Bottom action
- **"Analyse"** button — large, full-width, triggers processing.
- **"Add more"** always accessible so users can keep adding before running.
- Item count badge ("3 items ready") gives confidence before submitting.

---

## Screen 3 — Processing

**Purpose:** Run the full pipeline; keep the user informed.

Tap "Analyse" → `POST /api/pipeline/run` (server uses session `collected`).

**What happens server-side:**
1. `data_ingestion` — vision LLM reads each photo/note (~2–5 s per item, concurrent)
2. `evidence_aggregation` — merges evidence, resolves identity
3. `graph_builder` — applies operations, checks invariants
4. `computation` — calculates balances and suggested transfers

**UI:**
- Full-screen loading state with a progress label ("Reading receipts…", "Building graph…").
- On success → navigate to Review screen.
- On `inconsistencies` returned → show a warning banner ("We found some issues — you can fix them below") but still proceed to Review.
- On hard error (e.g. no evidence, all confidence=0) → return to evidence screen with error message and a hint.

**Response shape:**
```json
{
  "last_graph": { "nodes": [...], "edges": [...] },
  "inconsistencies": [{ "code": "PRICE_MISMATCH", "message": "..." }],
  "compute": {
    "success": true,
    "per_person": [{ "person_id", "display_name", "net_cents" }],
    "suggested_transfers": [{ "from_person_id", "to_person_id", "amount_cents" }]
  }
}
```

---

## Screen 4 — Review graph

**Purpose:** Let users verify and correct what the AI inferred.

### Graph elements

| Element | Visual | Editable |
|---|---|---|
| **Person** node | Circle + name | Rename, delete, merge |
| **Good** node | Rounded rect + name + total | Rename, change total, delete |
| **Cash flow** edge | Solid arrow → person paid for good | Change amount, delete |
| **Contribution** edge | Dashed arrow → person consumed good | Change weight (default 1), delete |

### Layout on mobile

D3 force-directed layout works on desktop but is heavy and fiddly on touch screens. Recommended alternative:

**Two-panel list view (simpler, more mobile-friendly):**
- **People tab:** List of person cards. Tap to rename or remove.
- **Goods tab:** List of goods cards. Each shows: name, total, payers, contributors. Tap a card to expand and edit connections.
- **Connections tab** (or inline): Swipe-to-delete on each edge row.

If D3 graph is kept, must handle:
- Touch drag (not mouse drag) — `d3.drag()` + pointer events
- No hover tooltips → use tap-to-select + bottom sheet for edit panel
- Pinch-to-zoom on the SVG canvas

### Inconsistency banners

Show above the graph. Each inconsistency has a code and a fix hint:

| Code | Meaning | User action |
|---|---|---|
| `PRICE_MISMATCH` | Cash flows don't add up to good's stated total | Edit total or add/remove a cash flow |
| `NO_CONTRIBUTION_UNITS` | A good has payers but no one is recorded as having consumed it | Add contribution edges |

Tap a banner → highlight the relevant node/edge in the graph.

### Bottom action
- **"Looks right"** → advance to Confirm.
- **"Re-run maths"** → `POST /api/dev/compute` with current graph (no re-ingestion needed).

**API:** `POST /api/dev/graph/validate` on any edit → returns updated `inconsistencies`.  
**API:** `POST /api/dev/compute` with `{ graph }` → returns fresh compute result.

---

## Screen 5 — Confirm

**Purpose:** Each participant agrees to their share before money moves.

### Single-device flow (MVP)

Show each person's card in sequence, like a "pass the phone" flow:
- "Alice, does this look right?" → shows Alice's net balance and which transfers she owes/receives.
- Tap **"Yes, looks right"** or **"No, go back and edit"**.
- If anyone rejects → return to Review; all confirmations reset.

### Multi-device flow (future)

Share a link. Each person opens it on their own phone and confirms individually.
When all confirm → trigger Final bill.

**State tracking:**
```
confirmations: { alice: pending | confirmed | rejected, bob: pending, ... }
```

Store in session. Show a "waiting for Bob…" state if using multi-device.

---

## Screen 6 — Final bill

**Purpose:** Clear summary of who pays whom, with payment shortcuts.

### Layout

**Header:** Event name + date.

**Per-person summary cards:**
- Name + avatar initial
- Net balance: green if owed money, red if owes money, grey if settled
- Breakdown: paid out / fair share

**Transfers table:**
```
Alice  →  Bob    €12.50   [Pay]
Alice  →  Cynthia  €8.00  [Pay]
```

The [Pay] button deep-links to:
- bunq payment (when integrated): `bunq://pay?to=Bob&amount=12.50&desc=Amsterdam dinner`
- Generic fallback: copy to clipboard prompt

**"All settled" state:** Confetti or a checkmark if no transfers needed (everyone paid exactly their share).

**Share:** Export as an image or plaintext summary ("Bob owes Alice €12.50 for Amsterdam dinner").

---

## API reference (pipeline endpoints)

| Screen | Method + Path | Body | Response |
|---|---|---|---|
| Add evidence — file | `POST /api/collect/upload` | multipart file | `{ bundle }` |
| Add evidence — note | `POST /api/collect/note` | `text=...` | `{ bundle }` |
| Clear evidence | `POST /api/collect/clear` | — | `{ bundle }` |
| Load demo scenario | `POST /api/collect/scenario1` or `scenario2` | — | `{ bundle }` |
| Run full pipeline | `POST /api/pipeline/run` | `{}` | `{ last_graph, inconsistencies, compute }` |
| Validate graph edits | `POST /api/dev/graph/validate` | `{ graph }` | `{ inconsistencies }` |
| Re-run compute | `POST /api/dev/compute` | `{ graph }` | `{ compute }` |
| Read session state | `GET /api/dev/session` | — | `{ collected, last_graph, last_blueprint, last_evidence }` |

---

## Key differences from the dev UI

The existing dev UI (`web/`) is a diagnostic tool — every pipeline step is exposed, JSON is visible, and there are override inputs everywhere. The mobile UI hides all of that:

| Dev UI | Mobile UI |
|---|---|
| 6 tabs (one per module) | 6 screens (linear flow) |
| JSON textareas everywhere | No raw JSON exposed |
| Manual step-by-step control | One-tap full pipeline |
| Scenario loader for testing | Camera / gallery upload |
| D3 graph with draggable nodes | List-based editor (or simplified touch graph) |
| All inconsistencies as text | Inline banners with fix hints |

The session state contract is identical — the mobile UI is just a different view on the same backend.

---

## Open questions

1. **Multi-user confirmation** — single device "pass the phone" for the hackathon demo, or invest in link sharing?
2. **Graph editor depth** — full D3 touch interaction, or a simpler list-based editor that covers 90% of edits?
3. **Voice input** — defer entirely, or wire up browser `MediaRecorder` → transcribe → note endpoint?
4. **bunq payment deep-link** — what's the sandbox URL scheme for payment initiation?
