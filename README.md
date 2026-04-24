# Billion idea · bunq hackathon 2026

Zero-input expense splitting — product vision in [`summarise.md`](summarise.md).

## Quick start (developers)

1. Clone the repo.
2. Copy environment template: `cp .env.example .env`
3. Fill in secrets in **`.env`** (file is gitignored; never commit it).
4. Run the app from [`hackathon/README.md`](hackathon/README.md) (`uv` or `pip`).

## Repository layout

| Path | Purpose |
|------|---------|
| [`docs/`](docs/) | Ideas, use cases, architecture (including ADRs), roadmap and tasks |
| [`hackathon/`](hackathon/) | **Main hackathon app** (FastAPI + modules + UI) |
| [`src/`](src/) | *(Reserved — app lives under `hackathon/src`)* |
| [`demo-prototype/`](demo-prototype/) | Earlier standalone demo (same compute semantics) |
| [`scripts/`](scripts/) | Setup and automation scripts |
| [`.github/workflows/`](.github/workflows/) | CI pipelines (when added) |
| [`summarise.md`](summarise.md) | Original product / technical brief |

## Team

- **Kirill** — vision, product direction  
- **Yehor** — development  
- **Klift** — development, coordination  
- **Cynthia** — ingest / integrations  

Planning artifacts live under [`docs/planning/`](docs/planning/) — **day 1:** [`docs/planning/hackathon-day1.md`](docs/planning/hackathon-day1.md).
