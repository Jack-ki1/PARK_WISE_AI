"""C0.6: batch analysis must not run two jobs against one shared model instance.

The shared `get_model` cache hands both jobs the same predictor, whose ByteTrack
state lives on the instance. Two mechanisms guard this:

* `batch_slot` — one job at a time per model key (job-level, so track state
  cannot interleave *between* passes), with the lease heartbeated while waiting;
* `INFERENCE_LOCK` — per-call serialization shared with the live path.

This test drives the real `process_video_job` on two tiny synthetic videos with
a fake model that records concurrent entries, caller threads, and the tracker
state it saw at the start of every track call.
"""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from app.config import settings as env_settings
from app.database import SessionLocal
from app.models import VideoJob
from app.services import video_pipeline


class _T:
    def __init__(self, values):
        self._values = values

    def cpu(self):
        return self

    def tolist(self):
        return self._values


class _Boxes:
    def __init__(self, rows):
        self.xyxy = _T([row["box"] for row in rows])
        self.conf = _T([row["confidence"] for row in rows])
        self.cls = _T([row["class_id"] for row in rows])
        self.id = _T([row["track_id"] for row in rows])

    def __len__(self):
        return len(self.xyxy.tolist())


class _Result:
    def __init__(self, rows):
        self.boxes = _Boxes(rows)


class _FakeModel:
    """Stands in for a YOLO model: sleeps to force overlap attempts, records state."""

    def __init__(self):
        self.predictor = SimpleNamespace(trackers=["stale-state-from-previous-job"])
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.thread_sequence: list[int] = []
        self.trackers_at_entry: list[list] = []

    def _run(self):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.05)
            with self._lock:
                self.thread_sequence.append(threading.get_ident())
                self.trackers_at_entry.append(list(self.predictor.trackers))
                # Simulate ByteTrack accumulating per-frame state on the instance.
                self.predictor.trackers.append(object())
            rows = [
                {"box": [10 + i * 6, 10, 50 + i * 6, 50], "confidence": 0.9, "class_id": 2, "track_id": i + 1}
                for i in range(6)
            ]
            return [_Result(rows)]
        finally:
            with self._lock:
                self.active -= 1

    def track(self, *_args, **_kwargs):
        return self._run()

    def predict(self, *_args, **_kwargs):
        return self._run()


def _write_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 64))
    assert writer.isOpened(), "cv2.VideoWriter failed to open"
    try:
        for _ in range(10):
            writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    finally:
        writer.release()


def _queue_job() -> str:
    video_id = str(uuid.uuid4())
    path = env_settings.data_path / "uploads" / f"{video_id}.avi"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_video(path)
    db = SessionLocal()
    try:
        db.add(
            VideoJob(
                id=video_id,
                original_name=f"{video_id}.avi",
                file_path=str(path),
                status="queued",
                width=64,
                height=64,
                fps=10.0,
                source_frame_count=10,
                duration_seconds=1.0,
            )
        )
        db.commit()
    finally:
        db.close()
    return video_id


def _status(video_id: str) -> str:
    db = SessionLocal()
    try:
        job = db.get(VideoJob, video_id)
        return job.status if job else "missing"
    finally:
        db.close()


def test_concurrent_batch_jobs_never_share_a_model_instance(monkeypatch):
    fake = _FakeModel()
    monkeypatch.setattr(video_pipeline, "get_model", lambda _name, _device: fake)
    monkeypatch.setattr(video_pipeline, "_ffmpeg_executable", lambda: None)

    first = _queue_job()
    second = _queue_job()
    errors: list[BaseException] = []

    def _run(video_id: str) -> None:
        try:
            video_pipeline.process_video_job(video_id)
        except BaseException as exc:  # noqa: BLE001 - surfaced via assertions below
            errors.append(exc)

    threads = [threading.Thread(target=_run, args=(vid,)) for vid in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, f"pipeline raised: {errors!r}"
    assert _status(first) == "completed"
    assert _status(second) == "completed"

    # No overlapping inference...
    assert fake.max_active == 1
    # ...and each job ran as one uninterrupted block in a single worker thread
    # (more than one thread-id switch would mean the jobs interleaved)...
    switches = sum(1 for a, b in zip(fake.thread_sequence, fake.thread_sequence[1:]) if a != b)
    assert switches <= 1, f"job track calls interleaved across threads: {fake.thread_sequence}"
    # ...starting each time from a clean tracker (the previous job's state was reset).
    assert fake.trackers_at_entry.count([]) == 2, fake.trackers_at_entry
    assert fake.trackers_at_entry[0] == []


def test_batch_slot_is_per_model_key():
    from app.services.model_store import batch_slot

    assert batch_slot("a.pt", "cpu") is batch_slot("a.pt", "cpu")
    assert batch_slot("a.pt", "cpu") is not batch_slot("b.pt", "cpu")
    assert batch_slot("a.pt", "cpu") is not batch_slot("a.pt", "0")
