# Module: `data_collection`

## Responsibility

Accept **user-provided raw material** for an event: **text notes** and **file uploads** (images, arbitrary files). Persist uploads on disk (or swap for object storage later) and expose a **`CollectedBundle`** for downstream modules.

## Main idea

This layer does **no** interpretation: it only records *what* the user gave and *when*. Bank PSD2, LLM, and graph logic stay out of here.

## Architecture links

- **Transaction ingestor** (bank) is a *different* source later; uploads/notes are **context** in the sense of [`event-domain-and-graph.md`](../../../../../docs/architecture/event-domain-and-graph.md) §3 (context bundle).
- **Event** scopes time + participants in the same doc §2.

## Contract

Output: **`CollectedBundle`** — [`../../contracts/collected.py`](../../contracts/collected.py).

## Examples

See [`examples/`](examples/) for JSON fixtures used in tests.
