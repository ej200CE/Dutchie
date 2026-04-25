# Scripts

Automation that you run locally or in CI:

- `bootstrap.sh` — install deps, copy `.env.example` → `.env` *(add when ready)*
- One-off migrations, seed data, API smoke tests

**Hackathon app** (under `hackathon/scripts/`): e.g. `assess_scenarios_llm.py` — full ingest → aggregate → graph on Story/1 and Story/2 with a real LLM (see [`hackathon/README.md`](../hackathon/README.md)).

Keep scripts **thin**; heavy logic belongs in `src/` or `hackathon/src/`.

## `add_exif_to_image.py` — EXIF helper (uv)

Adds **DateTime** / **DateTimeOriginal** / **DateTimeDigitized**, optional **GPS**, and **Make / Model / Software** (device presets: `iphone`, `android`, `samsung`, `generic`). Dependencies are declared **inline** for **`uv run`** (PEP 723).

From the **repository root**:

```bash
uv run scripts/add_exif_to_image.py \
  --input path/to/llm_image.png \
  --output path/out.jpg \
  --device iphone \
  --when "2024-06-15T14:30:00" \
  --lat 52.37 \
  --lon 4.90
```

- **Input:** common raster formats; output is always **JPEG** with embedded EXIF (piexif + Pillow).
- **GPS:** pass **both** `--lat` and `--lon` (decimal WGS84), or omit both.
- **Overrides:** `--make`, `--model`, `--software` (plain strings) replace preset fields.

```bash
uv run scripts/add_exif_to_image.py -h
```
