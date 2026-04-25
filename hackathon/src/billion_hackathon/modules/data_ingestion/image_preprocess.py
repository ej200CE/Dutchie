"""Deterministic image preprocessing before vision ingestion."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

_MAX_LONG_SIDE = 2200
_MAX_BYTES = 4 * 1024 * 1024
_JPEG_QUALITY = 86


def preprocess_image_bytes(
    raw: bytes,
    *,
    mime_type: str,
    original_filename: str | None,
) -> tuple[bytes, str, dict[str, Any]]:
    """Return processed bytes + media type + diagnostics."""
    img = Image.open(io.BytesIO(raw))
    diag: dict[str, Any] = {
        "applied": [],
        "source_quality": {},
        "original_bytes": len(raw),
        "original_size": [img.width, img.height],
    }

    img = ImageOps.exif_transpose(img)
    diag["applied"].append("exif_transpose")
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
        diag["applied"].append("convert_rgb")

    receipt_like = _looks_like_receipt_name(original_filename or "")
    if receipt_like:
        img, seg_diag = _segment_document_region(img)
        if seg_diag.get("applied"):
            diag["applied"].append("segment_document")
        diag["segmentation"] = seg_diag
        cropped = _crop_dark_borders(img)
        if cropped.size != img.size:
            img = cropped
            diag["applied"].append("crop_borders")
        img = _enhance_for_text(img)
        diag["applied"].append("text_enhance")

    if max(img.size) > _MAX_LONG_SIDE:
        ratio = _MAX_LONG_SIDE / float(max(img.size))
        img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.Resampling.LANCZOS)
        diag["applied"].append("resize_long_side")

    out_raw, out_mime = _encode_best_effort(img, mime_type)
    if len(out_raw) > _MAX_BYTES:
        # Last-resort shrink loop for oversized images.
        q = _JPEG_QUALITY
        cur = img
        while len(out_raw) > _MAX_BYTES and max(cur.size) > 800:
            cur = cur.resize((int(cur.width * 0.9), int(cur.height * 0.9)), Image.Resampling.LANCZOS)
            q = max(65, q - 5)
            out_raw, out_mime = _encode_jpeg(cur, q)
        diag["applied"].append("size_cap")

    diag["final_bytes"] = len(out_raw)
    with Image.open(io.BytesIO(out_raw)) as check:
        diag["final_size"] = [check.width, check.height]
        diag["source_quality"] = _quality_signals(check)
    diag["receipt_like"] = receipt_like
    return out_raw, out_mime, diag


def _looks_like_receipt_name(name: str) -> bool:
    n = Path(name).name.lower()
    # Keep aggressive text-enhancing pipeline for receipts/invoices only.
    # Transaction screenshots often get worse with document-style filtering.
    return any(k in n for k in ("receipt", "bill", "invoice", "bon"))


def _crop_dark_borders(img: Image.Image) -> Image.Image:
    gray = img.convert("L")
    # Use a bright-ish background to trim dark camera borders around receipts.
    bg = Image.new("L", gray.size, color=245)
    diff = ImageChops.difference(gray, bg)
    bbox = diff.getbbox()
    if not bbox:
        return img
    l, t, r, b = bbox
    if (r - l) < int(img.width * 0.55) or (b - t) < int(img.height * 0.55):
        return img
    return img.crop((l, t, r, b))


def _enhance_for_text(img: Image.Image) -> Image.Image:
    base = img.convert("RGB")
    base = ImageEnhance.Contrast(base).enhance(1.25)
    base = ImageEnhance.Sharpness(base).enhance(1.15)
    return base.filter(ImageFilter.MedianFilter(size=3))


def _encode_best_effort(img: Image.Image, mime_type: str) -> tuple[bytes, str]:
    if mime_type in ("image/jpeg", "image/jpg"):
        return _encode_jpeg(img, _JPEG_QUALITY)
    if mime_type == "image/png":
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue(), "image/png"
    # Default to jpeg for gif/webp after preprocessing to keep payload compact.
    return _encode_jpeg(img, _JPEG_QUALITY)


def _encode_jpeg(img: Image.Image, quality: int) -> tuple[bytes, str]:
    buf = io.BytesIO()
    rgb = img.convert("RGB")
    rgb.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue(), "image/jpeg"


def _quality_signals(img: Image.Image) -> dict[str, float]:
    g = ImageOps.grayscale(img)
    hist = g.histogram()
    px = max(1, sum(hist))
    dark = sum(hist[:28]) / px
    bright = sum(hist[228:]) / px
    mean = sum(i * c for i, c in enumerate(hist)) / px
    variance = sum(((i - mean) ** 2) * c for i, c in enumerate(hist)) / px
    # Rough blur proxy from variance of intensity.
    blur_score = max(0.0, min(1.0, 1.0 - (variance / 5000.0)))
    glare_score = max(0.0, min(1.0, bright))
    occlusion_score = max(0.0, min(1.0, dark))
    return {
        "blur": round(blur_score, 3),
        "glare": round(glare_score, 3),
        "occlusion": round(occlusion_score, 3),
    }


def _segment_document_region(img: Image.Image) -> tuple[Image.Image, dict[str, Any]]:
    """Optional CV segmentation (largest quad contour) for receipts/docs."""
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return img, {"engine": "none", "applied": False}

    arr = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(gray, 40, 120)
    contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img, {"engine": "opencv", "applied": False}

    h, w = gray.shape[:2]
    img_area = float(h * w)
    best = None
    best_area = 0.0
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) != 4:
            continue
        area = cv2.contourArea(approx)
        if area > best_area:
            best_area = area
            best = approx
    if best is None or (best_area / img_area) < 0.45:
        return img, {"engine": "opencv", "applied": False, "coverage": round(best_area / img_area, 3)}

    pts = best.reshape(4, 2).astype("float32")
    rect = _order_points(pts)
    (tl, tr, br, bl) = rect
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_w = int(max(width_a, width_b))
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_h = int(max(height_a, height_b))
    if max_w < 200 or max_h < 200:
        return img, {"engine": "opencv", "applied": False}
    dst = np.array(
        [[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]],
        dtype="float32",
    )
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(arr, M, (max_w, max_h))
    out = Image.fromarray(warped)
    return out, {
        "engine": "opencv",
        "applied": True,
        "coverage": round(best_area / img_area, 3),
        "out_size": [max_w, max_h],
    }


def _order_points(pts):
    import numpy as np  # type: ignore

    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]
    return rect
