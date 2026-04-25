#!/usr/bin/env python3
"""Compare preprocess pipeline timings CPU vs GPU (if available)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from billion_hackathon.modules.data_ingestion.image_ocr import extract_ocr_text
from billion_hackathon.modules.data_ingestion.image_preprocess import preprocess_image_bytes
from billion_hackathon.modules.data_ingestion.image_segmentation import segment_people


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def run_one(path: Path) -> dict:
    print(f"[{_ts()}] start file={path.name}")
    raw = path.read_bytes()
    print(f"[{_ts()}]   preprocess start")
    t0 = time.perf_counter()
    processed, pmime, _diag = preprocess_image_bytes(
        raw, mime_type="image/jpeg", original_filename=path.name
    )
    t1 = time.perf_counter()
    print(f"[{_ts()}]   preprocess done ms={int((t1 - t0) * 1000)}")
    print(f"[{_ts()}]   ocr start")
    _txt, ocr_meta = extract_ocr_text(processed)
    t2 = time.perf_counter()
    print(f"[{_ts()}]   ocr done ms={int((t2 - t1) * 1000)} engine={ocr_meta.get('engine')}")
    print(f"[{_ts()}]   segmentation start")
    seg_meta, _preview, _m = segment_people(processed)
    t3 = time.perf_counter()
    print(
        f"[{_ts()}]   segmentation done ms={int((t3 - t2) * 1000)} "
        f"engine={seg_meta.get('engine')} people={seg_meta.get('people_count', 0)} device={seg_meta.get('device', 'cpu')}"
    )
    return {
        "file": path.name,
        "pre_ms": int((t1 - t0) * 1000),
        "ocr_ms": int((t2 - t1) * 1000),
        "seg_ms": int((t3 - t2) * 1000),
        "total_ms": int((t3 - t0) * 1000),
        "ocr_engine": ocr_meta.get("engine"),
        "seg_engine": seg_meta.get("engine"),
        "seg_device": seg_meta.get("device", "cpu"),
        "mime": pmime,
    }


def bench(files: list[Path], use_gpu: bool) -> list[dict]:
    os.environ["BILLION_USE_GPU"] = "true" if use_gpu else "false"
    print(f"\n[{_ts()}] === BILLION_USE_GPU={os.environ['BILLION_USE_GPU']} ===")
    out: list[dict] = []
    total = len(files)
    for idx, p in enumerate(files, start=1):
        print(f"[{_ts()}] --- ({idx}/{total}) {p.name} ---")
        r = run_one(p)
        out.append(r)
        print(
            f"[{_ts()}] {r['file']}: total={r['total_ms']}ms pre={r['pre_ms']} ocr={r['ocr_ms']} seg={r['seg_ms']} "
            f"ocr={r['ocr_engine']} seg={r['seg_engine']} dev={r['seg_device']}"
        )
    return out


def main() -> None:
    root = Path(__file__).resolve().parents[2] / "Story" / "2"
    files = [root / "photo-tabel2_with_exif.jpg", root / "receipt2_with_exif.jpg", root / "table-selfie2_with_exif.jpg"]
    files = [p for p in files if p.exists()]
    if not files:
        raise SystemExit("No benchmark files found in Story/2")
    bench(files, use_gpu=False)
    bench(files, use_gpu=True)


if __name__ == "__main__":
    main()
