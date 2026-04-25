"""Optional local OCR + lightweight image classification helpers."""

from __future__ import annotations

import io
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image
from billion_hackathon.modules.data_ingestion.gpu_runtime import gpu_device_str, use_gpu

# Keywords that indicate the image is a photo of people/scenery — no point running
# EasyOCR (slow, finds nothing).  Generic names (IMG_1234.jpg) are NOT in this list
# so they still go through the full OCR path.
_PHOTO_KEYWORDS = frozenset({"photo", "selfie", "selfe", "tabel", "table", "people", "group", "portrait"})


def _text_content_likely(filename: str | None) -> bool:
    """Return False only when the filename strongly suggests a people/scenery photo."""
    if not filename:
        return True
    n = Path(filename).stem.lower()
    return not any(k in n for k in _PHOTO_KEYWORDS)


@lru_cache(maxsize=4)
def _get_easyocr_reader(gpu: bool, model_dir: str) -> Any:
    """Load and cache the EasyOCR reader — expensive first call, free thereafter."""
    import easyocr  # type: ignore
    return easyocr.Reader(
        ["en"],
        gpu=gpu,
        verbose=False,
        model_storage_directory=model_dir,
        user_network_directory=model_dir,
    )


def extract_ocr_text(raw: bytes, *, filename: str | None = None) -> tuple[str, dict[str, Any]]:
    """Best-effort OCR using locally available engines.

    Priority:
      1) pytesseract (if installed + tesseract binary available)
      2) easyocr (if installed AND filename doesn't suggest a photo)
      3) no OCR
    """
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return "", {"engine": "none", "reason": "invalid_image"}

    attempted: list[str] = []

    # Try pytesseract first.
    try:
        attempted.append("pytesseract")
        import pytesseract  # type: ignore

        txt = pytesseract.image_to_string(img) or ""
        txt = _cleanup_text(txt)
        if txt:
            return txt, {"engine": "pytesseract", "chars": len(txt)}
    except Exception as exc:
        pyt_err = str(exc)
    else:
        pyt_err = ""

    # Skip EasyOCR entirely when the filename indicates a people/scenery photo —
    # EasyOCR finds nothing there and takes 4–8 seconds.
    if not _text_content_likely(filename):
        return "", {
            "engine": "none",
            "chars": 0,
            "reason": "skipped_photo_filename",
            "attempted": attempted,
        }

    # Fallback: easyocr with cached reader.
    try:
        attempted.append("easyocr")
        import numpy as np  # type: ignore

        arr = np.array(img)
        model_dir = _easyocr_model_dir()
        gpu = use_gpu()
        reader = _get_easyocr_reader(gpu, str(model_dir))
        parts = reader.readtext(arr, detail=0, paragraph=True)
        txt = _cleanup_text("\n".join(parts))
        if txt:
            return txt, {
                "engine": "easyocr",
                "chars": len(txt),
                "model_dir": str(model_dir),
                "gpu": gpu,
                "device": gpu_device_str() if gpu else "cpu",
            }
    except Exception as exc:
        easy_err = str(exc)
    else:
        easy_err = ""

    reason = "no_local_ocr_engine"
    if pyt_err or easy_err:
        reason = f"pytesseract={pyt_err[:120] or 'ok_no_text'}; easyocr={easy_err[:120] or 'ok_no_text'}"
    return "", {"engine": "none", "chars": 0, "reason": reason, "attempted": attempted}


def classify_image_hint(filename: str | None, ocr_text: str) -> str | None:
    """Heuristic class hint for ingestion context (not a strict label)."""
    f = (filename or "").lower()
    t = ocr_text.lower()
    if any(k in f for k in ("receipt", "invoice", "bill")):
        return "receipt"
    if any(k in f for k in ("transaction", "bank", "payment", "tikkie", "bunq", "screenshot")):
        return "transaction_screenshot"
    if re.search(r"\btotal\b|\bvat\b|\beur\b|\bsubtotal\b|\btip\b", t):
        return "receipt"
    if re.search(r"\biban\b|\bpaid\b|\bfrom\b|\bto\b|\btransfer\b", t):
        return "transaction_screenshot"
    return None


def _cleanup_text(txt: str) -> str:
    txt = txt.replace("\r", "\n")
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    txt = txt.strip()
    if len(txt) > 3000:
        txt = txt[:3000]
    return txt


def _easyocr_model_dir() -> Path:
    p = os.environ.get("BILLION_EASYOCR_MODEL_DIR", "").strip()
    if p:
        d = Path(p)
    else:
        d = Path(__file__).resolve().parents[4] / "var" / "easyocr_models"
    d.mkdir(parents=True, exist_ok=True)
    return d
