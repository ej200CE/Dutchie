# Mobile UI — Developer Guide

## How to run

**Requirements:** Python 3.11+, [`uv`](https://docs.astral.sh/uv/)

```bash
# From the repo root
cd hackathon
uv sync
uv run uvicorn billion_hackathon.main:app --reload --host 127.0.0.1 --port 8080
```

Open **http://127.0.0.1:8080/mobile** in your browser.

To simulate a phone screen, open Chrome/Safari DevTools → toggle device toolbar → pick any mobile preset (375px wide is a good baseline).

The existing developer diagnostic UI is still at **http://127.0.0.1:8080** — both UIs share the same FastAPI process and session cookie, so you can use the dev tabs to inspect intermediate pipeline state while testing the mobile flow.

---

## File map

```
mobile_ui/
├── README.MD               Design document (screens, API map, open questions)
├── DEVELOPMENT.md          This file
├── templates/
│   └── mobile.html         Single-page HTML — all 6 screen divs + 4 modals
└── static/
    ├── mobile.js           All app logic (~700 lines, vanilla JS)
    └── mobile.css          Custom styles (Tailwind handles the rest)
```

These files are wired into the main FastAPI app in `main.py`:

```python
MOBILE_UI = PKG / "mobile_ui"
mobile_templates = Jinja2Templates(directory=str(MOBILE_UI / "templates"))
app.mount("/mobile/static", StaticFiles(directory=str(MOBILE_UI / "static")), name="mobile_static")

@app.get("/mobile")
async def mobile_home(request: Request):
    return mobile_templates.TemplateResponse(request, "mobile.html", ...)
```

No new API endpoints were added. The mobile UI calls the same `/api/*` routes as the dev UI.

---

## How the UI works

### Tech stack

- **Tailwind CSS** loaded via CDN — no build step, no `npm`.
- **Vanilla JS** — no framework. State lives in a single `const S` object in `mobile.js`.
- **Session cookie** — the backend sets `session_id` on every response. The browser sends it automatically on subsequent requests (`credentials: 'same-origin'`), so pipeline state persists across screens without any extra wiring.

### Screen model

All 6 screens are `<section>` divs present in the DOM at all times. The `show(id)` function hides every screen then reveals the target one:

```js
function show(id) {
  document.querySelectorAll('.screen').forEach(el => el.classList.add('hidden'));
  document.getElementById(id).classList.remove('hidden');
  window.scrollTo(0, 0);
}
```

Screens, in order:

| Section id | Screen | Navigates to |
|---|---|---|
| `#s-create` | Event name + participants | `#s-evidence` |
| `#s-evidence` | Upload photos, add note | `#s-processing` (on Analyse) |
| `#s-processing` | Spinner while pipeline runs | `#s-review` (on success) |
| `#s-review` | List editor for graph | `#s-confirm` |
| `#s-confirm` | Pass-the-phone confirmation | `#s-bill` (when all confirmed) |
| `#s-bill` | Final transfers + share | `#s-create` (Start over) |

### State object

`mobile.js` has one top-level state object `S`:

```js
const S = {
  eventName: '',        // string — from screen 1
  participants: [],     // string[] — from screen 1
  sessionId: null,      // not actively used; session managed by cookie
  itemCount: 0,         // number of items in the collected bundle
  graph: null,          // { event_id, nodes: Node[], edges: Edge[] }
  compute: null,        // { success, per_person: [], suggested_transfers: [] }
  confirmations: {},    // { [personId]: true | null }
  confirmIdx: 0,        // which person is currently confirming
};
```

`S.graph` and `S.compute` are populated from the `POST /api/pipeline/run` response and updated by subsequent graph edits + recompute calls.

### API calls

All network requests go through a single wrapper:

```js
async function apiFetch(method, path, body) { ... }
```

It sets `credentials: 'same-origin'` on every request, handles `FormData` vs JSON bodies automatically, and throws on non-OK responses.

Key calls and when they happen:

| Call | Trigger |
|---|---|
| `POST /api/collect/upload` | File input `change` event |
| `POST /api/collect/note` | "Add note" button |
| `POST /api/collect/clear` | "Clear all" / "Start over" |
| `POST /api/pipeline/run` | "Analyse" button |
| `POST /api/dev/graph/validate` | Any graph edit (node save/delete, edge delete/add) |
| `POST /api/dev/compute` | "Re-run maths" button + after every graph edit |

---

## mobile.html structure

The file has three sections:

1. **Screens** (`<section id="s-*">`) — one per step in the flow. Each is initially `hidden` except `#s-create` which has the `active` class.
2. **Modals** (`<div id="modal-*">`) — four bottom-sheet dialogs for adding people, goods, cash flows, and contributions. They sit at the bottom of the body with `position: fixed`.
3. **Script tag** — loads `mobile.js` at the end of `<body>`.

Tailwind is configured inline with a custom palette matching the Gruvbox dark theme used by the dev UI:

```html
<script>
  tailwind.config = {
    theme: {
      extend: {
        colors: {
          bg: '#282828', bg1: '#3c3836', bg2: '#504945',
          fg: '#ebdbb2', accent: '#fe8019', green: '#b8bb26',
          red: '#fb4934', yellow: '#fabd2f', blue: '#83a598',
        }
      }
    }
  }
</script>
```

---

## mobile.css

Tailwind handles layout, spacing, and colours. `mobile.css` only adds things Tailwind can't do via utility classes:

| Rule | Purpose |
|---|---|
| `.screen` fade-in | Smooth transition when switching screens |
| `.spinner` rotation | CSS `@keyframes spin` on the processing screen |
| `.thumb-grid` | CSS Grid for uploaded image thumbnails |
| `.review-tab::after` | Orange underline indicator on the active tab |
| `.edit-panel` slide-down | Expand animation when tapping "edit" on a card |
| `select` background arrow | Custom dropdown chevron (Tailwind doesn't style `<select>`) |
| `.modal > div` slide-up | Bottom-sheet entry animation |
| `.pt-safe` / `.pb-safe` | `env(safe-area-inset-*)` for notch/home-bar devices |

---

## Graph editing

The Review screen (`#s-review`) is a list-based editor — no D3, no SVG.

The graph is kept in `S.graph` as plain JSON matching the backend's graph schema:

```
nodes: [{ id, kind: "person"|"good", display_name, stated_total_cents? }]
edges: [
  { edge_id, kind: "cash_flow", from_id, to_id, amount_cents },
  { edge_id, kind: "contribution", person_id, good_id, value },
]
```

**Editing a node:** Tapping "edit" on a card calls `toggleEditNode(id)`, which reveals an inline `<div class="edit-panel">` inside the same card. Saving calls `saveNode(id)` which mutates `S.graph.nodes` in place, closes the panel, re-renders the list, then calls `validateAndRecompute()`.

**Deleting a node:** `deleteNode(id)` removes it from `S.graph.nodes` and also removes all edges that reference it (by `from_id`, `to_id`, `person_id`, or `good_id`).

**Adding nodes/edges:** Bottom-sheet modals collect the required fields, push a new object to `S.graph.nodes` or `S.graph.edges`, close the modal, re-render, and call `validateAndRecompute()`.

**`validateAndRecompute()`** fires two API calls in sequence after every edit:
1. `POST /api/dev/graph/validate` — updates the inconsistency banners above the tabs.
2. `POST /api/dev/compute` — refreshes `S.compute` so the Confirm and Bill screens reflect the latest graph.

Errors from these calls are silently swallowed (the graph state is still valid locally; the user can keep editing).

---

## Confirm flow

Screen 5 cycles through every person node in the graph one at a time.

`S.confirmIdx` tracks which person is up. `S.confirmations` maps `personId → true | null`.

- **Confirm** — sets `confirmations[person.id] = true`, increments `confirmIdx`, calls `renderConfirm()` again. When `confirmIdx >= persons().length`, calls `renderBill()` and navigates to `#s-bill`.
- **Go back and edit** — resets `confirmations` and `confirmIdx`, navigates back to `#s-review`.

The progress dots reflect confirmed (green), current (orange), and pending (grey) states.

---

## Extending the UI

**Add a new screen:** Add a `<section id="s-new" class="screen hidden">` to `mobile.html`, then call `show('s-new')` from JS when you want to navigate to it.

**Add a new API call:** Use `apiFetch(method, path, body)` — it handles auth, JSON serialisation, and error throwing.

**Add a new modal:** Copy one of the existing `<div id="modal-*">` blocks, give it a new id, and wire up `openModal('modal-new')` / `closeModal('modal-new')`. The `.modal-cancel` class is already handled globally.

**Change the colour scheme:** Edit the `tailwind.config` block in `mobile.html`. All Tailwind colour classes (`bg-accent`, `text-green`, etc.) will update automatically.
