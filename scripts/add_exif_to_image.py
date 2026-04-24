# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pillow>=10.0.0",
#   "piexif>=1.1.3",
# ]
# ///
"""
Add / replace EXIF on an image (e.g. LLM-generated PNG/JPEG) — datetime, optional GPS, device-style Make/Model/Software.

Run with uv (from repo root or this directory):

  uv run scripts/add_exif_to_image.py --input photo.png --output photo.jpg --device iphone --when "2024-06-15T14:30:00" --lat 52.37 --lon 4.90

EXIF is written in a standard JPEG. Non-JPEG inputs are re-encoded as JPEG (quality configurable).
"""

from __future__ import annotations

import argparse
import io
from datetime import datetime
from fractions import Fraction
from typing import Any

import piexif
from PIL import Image


def _exif_datetime(dt: datetime) -> bytes:
    return dt.strftime("%Y:%m:%d %H:%M:%S").encode("ascii")


def _decimal_to_dms_rationals(decimal: float) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    d = abs(decimal)
    deg = int(d)
    m_float = (d - deg) * 60.0
    minutes = int(m_float)
    seconds = (m_float - minutes) * 60.0
    sec_frac = Fraction(seconds).limit_denominator(10_000_000)
    return ((deg, 1), (minutes, 1), (sec_frac.numerator, sec_frac.denominator))


def _device_preset(name: str) -> dict[str, bytes]:
    presets: dict[str, dict[str, bytes]] = {
        "iphone": {
            "make": b"Apple",
            "model": b"iPhone 14 Pro",
            "software": b"iOS 17.2.1",
        },
        "android": {
            "make": b"Google",
            "model": b"Pixel 8",
            "software": b"Android 14",
        },
        "samsung": {
            "make": b"samsung",
            "model": b"SM-S918B",
            "software": b"Android 14",
        },
        "generic": {
            "make": b"Generic",
            "model": b"Camera",
            "software": b"1.0",
        },
    }
    key = name.lower().strip()
    if key not in presets:
        raise SystemExit(f"Unknown --device {name!r}; choose: {', '.join(sorted(presets))}")
    return presets[key]


def _build_exif_dict(
    when: datetime,
    *,
    lat: float | None,
    lon: float | None,
    make: bytes,
    model: bytes,
    software: bytes,
    image_description: bytes | None,
) -> dict[str, Any]:
    dt = _exif_datetime(when)
    exif: dict[str, Any] = {
        "0th": {
            piexif.ImageIFD.Make: make,
            piexif.ImageIFD.Model: model,
            piexif.ImageIFD.Software: software,
            piexif.ImageIFD.DateTime: dt,
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: dt,
            piexif.ExifIFD.DateTimeDigitized: dt,
        },
        "GPS": {},
        "Interop": {},
        "1st": {},
        "thumbnail": None,
    }
    if image_description:
        exif["0th"][piexif.ImageIFD.ImageDescription] = image_description

    if lat is not None and lon is not None:
        lat_ref = b"N" if lat >= 0 else b"S"
        lon_ref = b"E" if lon >= 0 else b"W"
        exif["GPS"][piexif.GPSIFD.GPSLatitudeRef] = lat_ref
        exif["GPS"][piexif.GPSIFD.GPSLongitudeRef] = lon_ref
        exif["GPS"][piexif.GPSIFD.GPSLatitude] = _decimal_to_dms_rationals(lat)
        exif["GPS"][piexif.GPSIFD.GPSLongitude] = _decimal_to_dms_rationals(lon)

    return exif


def _image_to_jpeg_bytes(im: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    rgb = im.convert("RGB")
    rgb.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", "-i", required=True, help="Source image (JPEG, PNG, WebP, …)")
    p.add_argument("--output", "-o", required=True, help="Output JPEG path (EXIF embedded)")
    p.add_argument(
        "--when",
        required=True,
        help='Capture time (ISO-ish), e.g. "2024-06-15T14:30:00" or "2024-06-15 14:30:00"',
    )
    p.add_argument("--lat", type=float, default=None, help="Latitude (decimal degrees, WGS84)")
    p.add_argument("--lon", type=float, default=None, help="Longitude (decimal degrees, WGS84)")
    p.add_argument(
        "--device",
        default="iphone",
        help="Preset: iphone | android | samsung | generic (use with --make/--model to override)",
    )
    p.add_argument("--make", default=None, help="Override EXIF Make (ASCII string)")
    p.add_argument("--model", default=None, help="Override EXIF Model")
    p.add_argument("--software", default=None, help="Override EXIF Software")
    p.add_argument("--description", default=None, help="ImageDescription tag (optional)")
    p.add_argument("--quality", type=int, default=92, help="JPEG quality when re-encoding (1–95)")
    args = p.parse_args()

    if (args.lat is None) ^ (args.lon is None):
        p.error("Pass both --lat and --lon, or neither")

    try:
        when = datetime.fromisoformat(args.when.replace("Z", "+00:00").replace(" ", "T"))
    except ValueError as e:
        raise SystemExit(f"Bad --when: {args.when!r} ({e})") from e

    preset = _device_preset(args.device)
    make = preset["make"] if args.make is None else args.make.encode("utf-8", errors="replace")
    model = preset["model"] if args.model is None else args.model.encode("utf-8", errors="replace")
    software = (
        preset["software"] if args.software is None else args.software.encode("utf-8", errors="replace")
    )
    desc = args.description.encode("utf-8", errors="replace") if args.description else None

    exif_dict = _build_exif_dict(
        when,
        lat=args.lat,
        lon=args.lon,
        make=make,
        model=model,
        software=software,
        image_description=desc,
    )
    exif_bytes = piexif.dump(exif_dict)

    with Image.open(args.input) as im:
        jpeg_bytes = _image_to_jpeg_bytes(im, max(1, min(95, args.quality)))

    # piexif requires an output path or BytesIO when `image` is raw JPEG bytes
    piexif.insert(exif_bytes, jpeg_bytes, args.output)


if __name__ == "__main__":
    main()
