"""Shared YOLO model cache with explicit isolation and serialization.

- Batch analysis uses `get_model` (one instance per weights/device key).
- Live streams use `get_stream_model`, which keys the cache by stream id so each
  stream owns its own model instance. Ultralytics persistent trackers
  (`model.track(..., persist=True)`) keep state on the model/predictor, so a
  shared instance would leak track identities between concurrent streams.
- `INFERENCE_LOCK` serializes inference calls: Ultralytics predictors are not
  safe for concurrent use on one instance, and serializing keeps CPU/GPU
  saturated by one worker instead of thrashing.
"""

from __future__ import annotations

import threading

_MODEL_CACHE: dict[str, object] = {}
_STREAM_MODEL_CACHE: dict[str, object] = {}
_LOCK = threading.Lock()

# Serializes every model.track/model.predict call (batch and live).
INFERENCE_LOCK = threading.Lock()

# Bounded per-stream instance cache (each instance holds its own tracker state).
MAX_STREAM_MODELS = 6


def _load_model(name: str, device: str):
    from ultralytics import YOLO

    model = YOLO(name)
    if device and device != "auto":
        try:
            model.to(device)
        except Exception:  # pragma: no cover - device may not exist on this host
            pass
    return model


def get_model(name: str, device: str = "auto"):
    """Load (and cache) an ultralytics model by weight filename. Import happens lazily so
    tests and the API can start without the CV stack installed."""
    key = f"{name}|{device}"
    with _LOCK:
        cached = _MODEL_CACHE.get(key)
        if cached is not None:
            return cached
        model = _load_model(name, device)
        if len(_MODEL_CACHE) > 4:  # bounded cache
            _MODEL_CACHE.pop(next(iter(_MODEL_CACHE)))
        _MODEL_CACHE[key] = model
        return model


def get_stream_model(name: str, device: str, stream_id: str):
    """Per-stream model instance so ByteTrack state never leaks across streams.

    Each live StreamSession must call this with its own stream_id and use the
    returned instance only for that stream's frames, always inside INFERENCE_LOCK.
    """
    key = f"{name}|{device}|stream:{stream_id}"
    with _LOCK:
        cached = _STREAM_MODEL_CACHE.get(key)
        if cached is not None:
            return cached
        model = _load_model(name, device)
        if len(_STREAM_MODEL_CACHE) >= MAX_STREAM_MODELS:
            _STREAM_MODEL_CACHE.pop(next(iter(_STREAM_MODEL_CACHE)))
        _STREAM_MODEL_CACHE[key] = model
        return model


def drop_stream_models(stream_id: str) -> None:
    """Release cached model instances for a stopped/deleted stream."""
    suffix = f"|stream:{stream_id}"
    with _LOCK:
        for key in [k for k in _STREAM_MODEL_CACHE if k.endswith(suffix)]:
            _STREAM_MODEL_CACHE.pop(key, None)
