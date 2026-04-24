# data_collection examples

**Contract:** `CollectedBundle` — see `billion_hackathon.contracts.collected`.

| File | Meaning |
|------|---------|
| `artifact_bundle.json` | Minimal bundle used by the end-to-end test chain — one note item, no binary uploads. |

There is no separate `expected` file here: collection is a **sink**; the next module (`data_ingestion`) defines expected evidence for the same story.

## What a note item looks like

```json
{
  "id": "note-seed",
  "kind": "note",
  "text": "EXPENSE: 12000 cents for groceries payer=alice participants=alice,bob,carol",
  "stored_path": null,
  "mime_type": null,
  "created_at": "2026-04-24T12:00:00Z",
  "original_filename": null,
  "file_size": null,
  "exif_timestamp": null,
  "gps_lat": null,
  "gps_lon": null
}
```

## What an image item looks like (with EXIF)

```json
{
  "id": "file-7b293104",
  "kind": "image",
  "text": null,
  "stored_path": "/var/uploads/bac5fa70_photo.jpg",
  "mime_type": "image/jpeg",
  "created_at": "2026-04-24T21:07:40Z",
  "original_filename": "photo.jpg",
  "file_size": 3145728,
  "exif_timestamp": "2024-06-15T14:30:00Z",
  "gps_lat": 48.85661,
  "gps_lon": 2.352383
}
```

`exif_timestamp`, `gps_lat`, and `gps_lon` are `null` when the image carries no EXIF or Pillow is not installed.
