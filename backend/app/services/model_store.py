"""Shared YOLO model cache with explicit isolation and serialization.

- Batch analysis uses `get_model` (one instance per weights/device key).
- Live streams use `get_stream_model`, which keys the cache by stream id so each
  stream owns its own model instance. Ultralytics persistent trackers
  (`model.track(..., persist=True)`) keep state on the model/predictor, so a
  shared instance would leak track identities between concurrent streams.
- `INFERENCE_LOCK` serializes inference calls: Ultralytics predictors are not
  safe for concurrent use on one instance, and serializing keeps CPU/GPU
  saturated by one worker instead of thrashing.
- `batch_slot` additionally caps *batch* concurrency to one job per shared model
  instance: a per-call lock only prevents overlapping predict() calls, not two
  jobs interleaving their ByteTrack state across successive calls.
"""

from __future__ import annotations

import threading
import time

_MODEL_CACHE: dict[str, object] = {}
_STREAM_MODEL_CACHE: dict[str, object] = {}
# Last-touch time per key: eviction is LRU, so a model that a live stream is using
# every second cannot be dropped out from under its ByteTrack state.
_USED_AT: dict[str, float] = {}
_LOCK = threading.Lock()
# Weights load once per key; the lock is per key so a slow first load cannot stall
# unrelated requests (previously the whole app waited on the global lock).
_BUILDING: dict[str, threading.Lock] = {}

# Serializes every model.track/model.predict call (batch and live).
INFERENCE_LOCK = threading.Lock()

# One batch job at a time per shared model instance (key = "weights|device").
_BATCH_SLOTS: dict[str, threading.Lock] = {}

# Bounded per-stream instance cache (each instance holds its own tracker state).
MAX_STREAM_MODELS = 6
MAX_MODELS = 4


def _load_model(name: str, device: str):
    from ultralytics import YOLO

    model = YOLO(name)
    if device and device != "auto":
        try:
            model.to(device)
        except Exception:  # pragma: no cover - device may not exist on this host
            pass
    return model


def _get_or_build(cache: dict[str, object], key: str, builder) -> object:
    with _LOCK:
        cached = cache.get(key)
        if cached is not None:
            _USED_AT[key] = time.monotonic()
            return cached
        build_lock = _BUILDING.setdefault(key, threading.Lock())

    # Loading happens outside _LOCK; only one thread builds a given key.
    with build_lock:
        with _LOCK:
            cached = cache.get(key)
            if cached is not None:
                _USED_AT[key] = time.monotonic()
                return cached
        model = builder()
        with _LOCK:
            _evict_locked(cache)
            cache[key] = model
            _USED_AT[key] = time.monotonic()
            _BUILDING.pop(key, None)
        return model


def _evict_locked(cache: dict[str, object]) -> None:
    limit = MAX_STREAM_MODELS if cache is _STREAM_MODEL_CACHE else MAX_MODELS
    while len(cache) >= limit:
        coldest = min(cache, key=lambda k: _USED_AT.get(k, 0.0))
        cache.pop(coldest, None)
        _USED_AT.pop(coldest, None)


def get_model(name: str, device: str = "auto"):
    """Load (and cache) an ultralytics model by weight filename. Import happens lazily so
    tests and the API can start without the CV stack installed."""
    key = f"{name}|{device}"
    return _get_or_build(_MODEL_CACHE, key, lambda: _load_model(name, device))


def batch_slot(name: str, device: str) -> threading.Lock:
    """Per-model-instance lock held for the whole of one batch job.

    The shared `get_model` cache means two concurrent jobs get the *same*
    predictor; without this slot their ByteTrack state interleaves across
    frames (S7). The caller heartbeats its job lease while waiting so a busy
    model cannot let reap_stale() fail a job that is merely queued for its turn.
    """
    key = f"{name}|{device}"
    with _LOCK:
        return _BATCH_SLOTS.setdefault(key, threading.Lock())


def reset_trackers(model) -> None:
    """Drop ByteTrack state left behind by the previous job on a shared instance."""
    predictor = getattr(model, "predictor", None)
    if predictor is not None and hasattr(predictor, "trackers"):
        predictor.trackers = []


def get_stream_model(name: str, device: str, stream_id: str):
    """Per-stream model instance so ByteTrack state never leaks across streams.

    Each live StreamSession must call this with its own stream_id and use the
    returned instance only for that stream's frames, always inside INFERENCE_LOCK.
    """
    key = f"{name}|{device}|stream:{stream_id}"
    return _get_or_build(_STREAM_MODEL_CACHE, key, lambda: _load_model(name, device))


def drop_stream_models(stream_id: str) -> None:
    """Release cached model instances for a stopped/deleted stream."""
    suffix = f"|stream:{stream_id}"
    with _LOCK:
        for key in [k for k in _STREAM_MODEL_CACHE if k.endswith(suffix)]:
            _STREAM_MODEL_CACHE.pop(key, None)
            _USED_AT.pop(key, None)
