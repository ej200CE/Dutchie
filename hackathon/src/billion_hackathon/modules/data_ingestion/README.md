# Module: `data_ingestion`

## Responsibility

Turn a **`CollectedBundle`** into structured **`EvidenceBundle`** items (spend hints, receipt placeholders, free text, etc.). Today this is a **deterministic stub** (e.g. parsing `EXPENSE:` lines); later it can call the shared **`llm`** module for multimodal / messy input.

## Main idea

Implements the **normalization** step before the **Graph Builder** sees anything: heterogeneous inputs become comparable **evidence** rows with **confidence** and **provenance** (`source_item_ids`).

## Architecture links

- **Context Engine** ingestion & reasoning — [`event-domain-and-graph.md`](../../../../../docs/architecture/event-domain-and-graph.md) §3.  
- LLM is **upstream** of deterministic compute; output must stay **editable** (graph fixes).

## Contract

- Input: **`CollectedBundle`**  
- Output: **`EvidenceBundle`** — [`../../contracts/evidence.py`](../../contracts/evidence.py)

## LLM

Do **not** open HTTP to model providers from this package directly — use [`../llm/README.md`](../llm/README.md) so keys, retries, and logging stay centralized.

## Examples

[`examples/`](examples/) — `artifact_bundle.json` → `expected_evidence.json`.
