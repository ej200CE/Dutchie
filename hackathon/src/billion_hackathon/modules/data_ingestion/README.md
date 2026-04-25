# Module: `data_ingestion`

## Responsibility

Turn a **`CollectedBundle`** into a structured **`EvidenceBundle`**.  
Each `CollectedItem` is dispatched to the right ingestor based on its `kind`:

| `kind` | Ingestor | Strategy |
|--------|----------|----------|
| `note` | inline rule parser | Regex for `EXPENSE:` lines; free_text fallback. Fast, no LLM. |
| `image` | `ImageIngestor` | Vision LLM → JSON → EvidenceItems. EXIF-based stub when LLM is not configured. |
| `audio` | `AudioIngestor` | Speech-to-text (OpenAI-compatible when configured), then transcript → evidence extraction. Sidecar `.txt` transcript fallback in stub/dev mode. |
| `file` | `DocumentIngestor` | Text LLM → JSON → EvidenceItems. Regex stub for `EXPENSE:` lines when LLM is not configured. Binary files (PDF, DOCX) emit a `confidence=0` placeholder. |

The LLM client is created once in `DataIngestionService.__init__` and shared across ingestors.
LLM calls for all items are dispatched concurrently via `aingest` (the web-server path).
A sequential `ingest` method is kept for tests and scripts.

## Post-processing (after LLM or stub ingest)

`service` runs a two-pass ingest (`payer/total-heavy sources` first, then contextual sources with injected event context), then `_postprocess_evidence` on every bundle before it leaves this module:

| Step | Module | Purpose |
|------|--------|--------|
| Merge orphan payer | `merge_orphan_payer_with_group.py` | If the receipt/tx payer id does not match `group_pos_*` slots from people photos, remap to the first group slot so the graph does not get an extra person. |
| Drop inferred photographer | same file | Remove `inferred_photographer_*` when enough `group_pos_*` people are already present. |
| Consolidate receipt lines | `consolidate_receipt_lines.py` | When many `receipt_line` items come from the **same source image** (vision “menu explosion”), collapse to **one** line aligned with the dominant `spend_hint` total and shared `good_id` / participants. |

Scenario fixtures can bypass vision via `stub_scenario_evidence.py` (`scenario_stub_evidence_if_applicable`).

## Main idea

Normalization: heterogeneous inputs become comparable evidence rows with **confidence**, **provenance** (`source_item_ids`), and **rich metadata** in `extra` so the aggregator can cross-correlate evidence without re-fetching source files.

### OCR and segmentation (local-first, optional)

- `image_preprocess.py` runs deterministic preprocessing and optional OpenCV document segmentation (`largest quadrilateral` + perspective warp) when OpenCV is available.
- `image_ocr.py` runs best-effort local OCR:
  - `pytesseract` if installed and system tesseract is available,
  - fallback to `easyocr` if installed,
  - otherwise no OCR.
- OCR text is injected into the image prompt context and stored in `extra.ocr_text` / `extra.ocr_meta`.
- A local heuristic class hint (`receipt` vs `transaction_screenshot`) is stored as `extra.image_type_hint_local`.

## What each ingestor extracts

### Image ingestor

The LLM returns four top-level arrays; all four are stored in `extra` on every `EvidenceItem` produced from that image:

#### `context` — cross-correlation anchor to bank transactions and other images
```json
{
  "venue": "La Trattoria",
  "venue_type": "restaurant",
  "datetime_visible": "2024-06-15T20:30:00",
  "location_hint": "Barcelona",
  "total_amount_cents": 8700,
  "currency": "EUR"
}
```
`venue + datetime_visible + total_amount_cents` lets the aggregator match this receipt image to the corresponding bank transaction.

#### `persons` — per-person descriptions for cross-image identity resolution
```json
[
  {
    "person_id": "alice",
    "display_name": "Alice",
    "description": "Woman, ~30s, brown hair, blue jacket",
    "seat_or_position": "far-left seat",
    "confidence": 0.9
  },
  {
    "person_id": "adult_male_red_shirt",
    "display_name": null,
    "description": "Man, ~35s, red shirt, glasses",
    "seat_or_position": "centre seat",
    "confidence": 0.85
  }
]
```
`seat_or_position` is the key field for table photos: it lets the aggregator link `"far-left seat"` in the persons array to `"visual_cues": "far-left seat"` in the goods array, establishing who ate which dish without face recognition.

#### `goods` — per-good descriptions for cross-image goods matching
```json
[
  {
    "good_id": "carbonara_pasta",
    "label": "Carbonara Pasta",
    "category": "food",
    "quantity": 1,
    "unit_price_cents": 1800,
    "total_cents": 1800,
    "description": "creamy pasta with bacon bits",
    "visual_cues": "white bowl, creamy sauce, far-left seat"
  }
]
```
`description + visual_cues` lets the aggregator match a `receipt_line` from a receipt image to a good visible in a table photo, building the `contribution` edge (who ate it).

#### Items — the core `EvidenceItem` list

Each item references its good via `extra["good_id"]` and references persons via `payer_person_id` / `participant_person_ids` (both are `person_id` values from the `persons` array).

### Document ingestor

Same structure — `context`, `persons`, `goods` at top level, `good_id` per item — but without `visual_cues` and `seat_or_position` (no visual information). For text files with named people, the `persons` array provides the same identity anchors as images.

## Image categories

| Category | Typical evidence kinds produced |
|----------|---------------------------------|
| `receipt` | Vision may emit `receipt_line` × N + `spend_hint` for total; post-process may **collapse** many lines per image to one shared total for group splits. |
| `transaction_screenshot` | `spend_hint` |
| `people_photo` | `presence_hint` |
| `location_photo` | `presence_hint` or `free_text` |
| `group_chat_screenshot` | `spend_hint`, `p2p_hint`, `free_text` |
| `other` | `free_text` |

## Evidence kinds

| `kind` | Meaning | Graph edge |
|--------|---------|-----------|
| `spend_hint` | Expense with amount and payer | `cash_flow` Person→Good |
| `receipt_line` | Single line item; payer may be unknown | `cash_flow` pending payer resolution |
| `p2p_hint` | Person-to-person transfer or IOU | `cash_flow` Person→Person |
| `presence_hint` | Who was present at a moment | `contribution` edges inferred by aggregator |
| `free_text` | Notable but ambiguous | kept for aggregator context |

## Cross-correlation paths (aggregator uses these)

| Signal | How it links evidence |
|--------|----------------------|
| `context.venue + context.datetime_visible + context.total_amount_cents` | Receipt image ↔ bank transaction |
| `context.venue + context.datetime_visible` | Multiple images ↔ same meal/event |
| `goods[].description + goods[].visual_cues` | Receipt line-item ↔ dish in table photo |
| `persons[].person_id` | Same person across images (exact match) |
| `persons[].description` | Same person across images (LLM/fuzzy match) |
| `persons[].seat_or_position` ↔ `goods[].visual_cues` | Person ↔ specific dish at table |

## LLM setup

Uses the shared `llm` module — see [`../llm/README.md`](../llm/README.md).  
Set `BILLION_LLM_PROVIDER` / `BILLION_LLM_API_KEY` / `BILLION_LLM_MODEL` in `.env` to switch from stub to a real provider.

Prompts live in [`prompts.py`](prompts.py).

## Stub behaviour (no API key)

| Input | Stub output |
|-------|-------------|
| Image | Single `presence_hint` from EXIF (timestamp, GPS). `confidence=0.1`. No `context`/`persons`/`goods` in `extra`. |
| Text file | `EXPENSE:` regex → `spend_hint` items (`confidence=0.7`); else `free_text` (`confidence=0.1`). |
| Binary file | `free_text`, `confidence=0.0`, `extra.stub=True`. |

## Contract

- Input: **`CollectedBundle`**
- Output: **`EvidenceBundle`** — [`../../contracts/evidence.py`](../../contracts/evidence.py)

## Files

| File | Purpose |
|------|---------|
| `service.py` | Entry point — `aingest` / `ingest`; chains merge, drop-inferred, consolidate |
| `image_ingestor.py` | Image → vision LLM → EvidenceItems |
| `image_preprocess.py` | Deterministic rotate/crop/enhance/resize preprocessing + quality diagnostics |
| `audio_ingestor.py` | Audio transcription path (OpenAI-compatible or sidecar transcript), then transcript → EvidenceItems |
| `document_ingestor.py` | Text file → text LLM → EvidenceItems |
| `merge_orphan_payer_with_group.py` | Payer/group id alignment; optional drop of redundant inferred photographer |
| `consolidate_receipt_lines.py` | Collapse exploded per-dish receipt lines to one total per check image |
| `stub_scenario_evidence.py` | Deterministic Story/1–2 evidence when running stub scenarios |
| `prompts.py` | All LLM prompt templates and field-mapping notes |

## Examples

[`examples/`](examples/) — `artifact_bundle.json` → `expected_evidence.json` (note-only; tests the rule-based path).
