"""Shared YOLO model cache with a lock so batch analysis and live sessions reuse one instance."""

from __future__ import annotations

import threading

_MODEL_CACHE: dict[str, object] = {}
_LOCK = threading.Lock()


def get_model(name: str, device: str = "auto"):
    """Load (and cache) an ultralytics model by weight filename. Import happens lazily so
    tests and the API can start without the CV stack installed."""
    key = f"{name}|{device}"
    with _LOCK:
        cached = _MODEL_CACHE.get(key)
        if cached is not None:
            return cached
        from ultralytics import YOLO

        model = YOLO(name)
        if device and device != "auto":
            try:
                model.to(device)
            except Exception:  # pragma: no cover - device may not exist on this host
                pass
        if len(_MODEL_CACHE) > 4:  # bounded cache
            _MODEL_CACHE.pop(next(iter(_MODEL_CACHE)))
        _MODEL_CACHE[key] = model
        return model
