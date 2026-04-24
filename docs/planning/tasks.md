# Task backlog

**Owners:** Klift · Yehor · Kirill · **Cynthia**

**Status:** ☐ todo · ◐ in progress · ☑ done · ⊘ cancelled

**Day 1 plan:** [`hackathon-day1.md`](hackathon-day1.md) (decisions, four tracks, test layers).

Edit this table or move rows to GitHub Issues / Projects when you outgrow Markdown.

| ID | Task | Owner | Status | Notes / links |
|----|------|-------|--------|----------------|
| T-001 | Initialize repo layout, `.env.example`, `.gitignore` | Klift | ☑ | — |
| T-002 | Fill `docs/architecture/overview.md` for chosen stack | Klift | ◐ | FastAPI demo = source of truth; link `hackathon-day1.md` |
| T-003 | First use case in `docs/use-cases/` (UC-001) | Kirill | ☐ | Template in `use-cases/README.md` |
| T-004 | bunq sandbox: authenticate + list payments (spike) | Cynthia | ☐ | Normalizer sketch → internal evidence JSON |
| T-005 | Align MVP scope with hackathon timebox | Kirill | ☐ | Must match `hackathon-day1.md` MVP slice |
| T-006 | Restore or add `fixtures/demo/*` for demo-prototype | Klift | ☐ | Required for `demo_data.py` |
| T-007 | Pytest: `compute_engine` + golden graphs | Yehor | ☐ | See test layers in `hackathon-day1.md` |
| T-008 | Pytest (optional): FastAPI routes with TestClient | Klift / Yehor | ☐ | After T-006 |
| T-009 | ADR or overview paragraph: stack, T_g, rounding | Klift | ☐ | Closes architecture §9 gaps |

### How to use

1. Add a row for each actionable item; keep **one owner** for clarity.
2. Kirill can own docs, prioritisation, and narrative; dev tasks stay on Klift/Yehor/Cynthia unless pairing.
3. When a task is large, split into new IDs and link in **Notes**.
