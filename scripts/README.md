# Scripts

Automation that you run locally or in CI:

- `bootstrap.sh` — install deps, copy `.env.example` → `.env` *(add when ready)*
- One-off migrations, seed data, API smoke tests

Keep scripts **thin**; heavy logic belongs in `src/`.
