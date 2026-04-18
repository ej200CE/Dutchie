# Architecture

## Living documents

| Document | Role |
|----------|------|
| [`overview.md`](overview.md) | Current modules, responsibilities, dependencies (high level) |
| [`event-domain-and-graph.md`](event-domain-and-graph.md) | **Event**, context, **transactional graph**, Graph Builder, Context Engine, Computational Engine |
| [`vocabulary-map.md`](vocabulary-map.md) | **Cross-reference:** Trip vs Event, Good vs expense, Split Engine vs Computational Engine, legacy Summarise terms |
| [`adr/`](adr/) | Architecture Decision Records — **why** something was chosen |

Update the overview when modules split or merge. For each non-obvious choice (framework, data store, sync vs async flows), add an ADR.

## ADR convention

- One decision per file: `adr/NNNN-short-title.md` (`0001-use-sqlite-for-prototype.md`).
- Status: Proposed | Accepted | Superseded by ADR-XXXX.
- Keep them short; link to code or issues when useful.

See [`adr/0000-template.md`](adr/0000-template.md).
