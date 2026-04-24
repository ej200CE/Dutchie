# Module: `data_collection`

## Responsibility

Accept **user-provided raw material** for an event: **text notes** and **file uploads** (images, arbitrary files). Persist uploads on disk (or swap for object storage later) and expose a **`CollectedBundle`** for downstream modules.

For image uploads the service also extracts **EXIF metadata** — timestamp and GPS coordinates — and stores them directly on the item so downstream modules get location context without re-parsing binary files.

## Main idea

This layer does **no business interpretation**: it only records *what* the user gave and *when*. Bank PSD2, LLM, and graph logic stay out of here.

## EXIF extraction

When a file is uploaded with an `image/*` MIME type, `DataCollectionService.add_upload` calls `_extract_exif` (Pillow-backed, graceful no-op if Pillow is absent):

| EXIF field | Source tag | Stored as |
|------------|-----------|-----------|
| `exif_timestamp` | `DateTimeOriginal` (36867), fallback `DateTime` (306) | `datetime` (UTC) |
| `gps_lat` | `GPSInfo` IFD — latitude + ref | `float` decimal degrees |
| `gps_lon` | `GPSInfo` IFD — longitude + ref | `float` decimal degrees |

Fields are `None` when the image has no EXIF, when Pillow is not installed, or for non-image files.

## API endpoints (via `main.py`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/collect/note` | Add a text note to the session bundle |
| `POST` | `/api/collect/upload` | Upload one or more files (`files` form field, `multipart/form-data`) |
| `GET`  | `/api/collect/file/{item_id}` | Serve an uploaded file (for image thumbnails in the UI) |
| `POST` | `/api/collect/clear` | Clear all items from the session bundle |

## Contract

Output: **`CollectedBundle`** — [`../../contracts/collected.py`](../../contracts/collected.py).

### `CollectedItem` fields

| Field | Type | Set for |
|-------|------|---------|
| `id` | `str` | always |
| `kind` | `"note" \| "image" \| "file"` | always |
| `text` | `str \| None` | notes |
| `stored_path` | `str \| None` | file/image uploads |
| `mime_type` | `str \| None` | file/image uploads |
| `created_at` | `datetime` | always (server time) |
| `original_filename` | `str \| None` | file/image uploads |
| `file_size` | `int \| None` | file/image uploads (bytes) |
| `exif_timestamp` | `datetime \| None` | images with EXIF DateTimeOriginal |
| `gps_lat` | `float \| None` | images with EXIF GPS |
| `gps_lon` | `float \| None` | images with EXIF GPS |

## Architecture links

- **Transaction ingestor** (bank) is a *different* source later; uploads/notes are **context** in the sense of [`event-domain-and-graph.md`](../../../../../docs/architecture/event-domain-and-graph.md) §3 (context bundle).
- **Event** scopes time + participants in the same doc §2.

## Examples

See [`examples/`](examples/) for JSON fixtures used in tests.
