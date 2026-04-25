"""Small helpers to decide CPU vs GPU runtime."""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def torch_cuda_available() -> bool:
    try:
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def use_gpu() -> bool:
    raw = os.environ.get("BILLION_USE_GPU", "true").strip().lower()
    wanted = raw not in {"0", "false", "no", "off"}
    return wanted and torch_cuda_available()


def gpu_device_str() -> str:
    return os.environ.get("BILLION_GPU_DEVICE", "0").strip() or "0"
