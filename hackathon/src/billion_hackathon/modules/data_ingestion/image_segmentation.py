"""Optional heavy-model people segmentation (Ultralytics YOLO-seg)."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from billion_hackathon.modules.data_ingestion.gpu_runtime import gpu_device_str, use_gpu

_MODEL = None


def segment_people(raw: bytes) -> tuple[dict[str, Any], bytes, str]:
    """Return segmentation metadata and annotated preview image bytes."""
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return {"engine": "none", "enabled": False, "reason": "invalid_image"}, raw, "image/jpeg"

    arr = _to_numpy(img)
    if arr is None:
        return {"engine": "none", "enabled": False, "reason": "numpy_missing"}, _as_jpeg(img), "image/jpeg"

    model = _get_model()
    if model is None:
        return {"engine": "none", "enabled": False, "reason": "ultralytics_missing"}, _as_jpeg(img), "image/jpeg"

    # Predict people only, and keep moderate confidence.
    device = gpu_device_str() if use_gpu() else "cpu"
    res = model.predict(arr, conf=0.3, classes=[0], verbose=False, device=device)
    boxes: list[dict[str, Any]] = []
    if res and len(res) > 0 and getattr(res[0], "boxes", None) is not None:
        b = res[0].boxes
        xyxy = b.xyxy.cpu().numpy() if hasattr(b.xyxy, "cpu") else b.xyxy
        confs = b.conf.cpu().numpy() if hasattr(b.conf, "cpu") else b.conf
        for i in range(len(xyxy)):
            x1, y1, x2, y2 = [float(v) for v in xyxy[i].tolist()]
            boxes.append(
                {
                    "bbox_xyxy": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                    "confidence": round(float(confs[i]), 3),
                }
            )

    annotated = _draw_people_boxes(img, boxes)
    return {
        "engine": "ultralytics_yolov8_seg",
        "enabled": True,
        "model": "yolov8n-seg.pt",
        "device": device,
        "people_count": len(boxes),
        "people": boxes,
    }, _as_jpeg(annotated), "image/jpeg"


def _get_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        settings_dir = Path(__file__).resolve().parents[4] / "var" / "ultralytics_settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("YOLO_CONFIG_DIR", str(settings_dir))
        os.environ.setdefault("ULTRALYTICS_SETTINGS_DIR", str(settings_dir))
        from ultralytics import YOLO  # type: ignore

        model_dir = Path(__file__).resolve().parents[4] / "var" / "ultralytics_models"
        model_dir.mkdir(parents=True, exist_ok=True)
        _MODEL = YOLO("yolov8n-seg.pt")
        return _MODEL
    except Exception:
        return None


def _to_numpy(img: Image.Image):
    try:
        import numpy as np  # type: ignore

        return np.array(img)
    except Exception:
        return None


def _draw_people_boxes(img: Image.Image, people: list[dict[str, Any]]) -> Image.Image:
    out = img.copy()
    draw = ImageDraw.Draw(out)
    for i, p in enumerate(people, start=1):
        x1, y1, x2, y2 = p["bbox_xyxy"]
        draw.rectangle((x1, y1, x2, y2), outline=(255, 160, 40), width=3)
        draw.text((x1 + 2, max(0, y1 - 14)), f"person {i} {p['confidence']:.2f}", fill=(255, 220, 130))
    return out


def _as_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue()
