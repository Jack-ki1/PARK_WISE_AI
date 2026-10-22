"""Live view: decode a camera URL or replay an uploaded video, run YOLO + tracking,
annotate every frame and expose the latest frame/payload to WebSocket subscribers.

Design notes
------------
- One daemon thread per active stream (StreamSession); frames are shared with the
  FastAPI event loop through a poll-once-per-tick snapshot (the same style as the
  job-progress WebSocket), so no cross-thread asyncio calls are needed.
- Analytics follow Nvidia's gst-nvdsanalytics vocabulary (ROI filtering, overcrowding,
  direction / line-crossing) implemented in pure Python over bay polygons + track ids,
  which is the portable equivalent for a FastAPI/OpenCV deployment (no DeepStream).
- Sources are validated by security.validate_external_url before a session starts (SSRF).
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from ..config import settings as env_settings
from ..models import Stream
from .model_store import get_model

VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
OVERCROWDING_RATIO = 0.8
OVERCROWDING_COOLDOWN_S = 60.0


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def point_in_polygon(point: tuple[float, float], polygon: list[list[float]]) -> bool:
    """Ray casting; polygon is a list of [x, y] pairs normalised to 0..1."""
    x, y = point
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]
        if (yi > y) != (yj > y):
            cross = (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
            if x < cross:
                inside = not inside
        j = i
    return inside


class BayTracker:
    """Smoothed bay state with hysteresis (same 3-sample/60% rule as the batch pipeline)."""

    def __init__(self, spaces: list[dict]) -> None:
        self.names = [str(space.get("name") or f"Bay {i + 1}") for i, space in enumerate(spaces)]
        self.polygons = [space.get("polygon") or [] for space in spaces]
        self.votes: list[deque[str]] = [deque(maxlen=4) for _ in spaces]
        self.states: list[str] = ["unknown"] * len(spaces)
        self.confidences: list[float] = [0.0] * len(spaces)

    def update(self, centers: list[tuple[float, float]]) -> list[dict]:
        transitions: list[dict] = []
        for idx, polygon in enumerate(self.polygons):
            if len(polygon) < 3:
                continue
            occupied = any(point_in_polygon(center, polygon) for center in centers)
            queue = self.votes[idx]
            queue.append("occupied" if occupied else "free")
            observations = list(queue)
            count = len(observations)
            occupied_votes = observations.count("occupied")
            ratio = occupied_votes / count
            previous = self.states[idx]
            # Mirrors video_pipeline._space_states: decide after 3 observations using the
            # same 60%/20% thresholds, otherwise hold the last confirmed state.
            if count >= 3 and ratio >= 0.6:
                new_state = "occupied"
            elif count >= 3 and ratio <= 0.2:
                new_state = "free"
            elif previous in {"occupied", "free"}:
                new_state = previous
            else:
                new_state = "unknown"
            self.states[idx] = new_state
            self.confidences[idx] = round(max(ratio, 1 - ratio), 3)
            if previous != new_state and previous != "unknown":
                transitions.append({"bay": self.names[idx], "from": previous, "to": new_state})
        return transitions

    def summary(self) -> list[dict]:
        return [
            {"name": name, "state": state, "confidence": round(conf, 3)}
            for name, state, conf in zip(self.names, self.states, self.confidences)
        ]


class DirectionDetector:
    """nvdsanalytics-style direction/line-crossing: a track entering or leaving the
    calibrated ROI (its bounding box) produces a line_crossing event with a direction."""

    def __init__(self) -> None:
        self._inside: dict[int, bool] = {}

    def update(self, track_centers: dict[int, tuple[float, float]], roi: list[list[float]]) -> list[dict]:
        if len(roi) < 3:
            return []
        events: list[dict] = []
        live_ids = set(track_centers)
        for track_id in list(self._inside):
            if track_id not in live_ids:
                del self._inside[track_id]
        for track_id, center in track_centers.items():
            now_inside = point_in_polygon(center, roi)
            previous = self._inside.get(track_id)
            if previous is not None and previous != now_inside:
                events.append(
                    {
                        "type": "line_crossing",
                        "direction": "in" if now_inside else "out",
                        "track_id": track_id,
                        "ts": utcnow().isoformat(),
                    }
                )
            self._inside[track_id] = now_inside
        return events


class StreamSession:
    def __init__(self, stream: Stream, source: str, spaces: list[dict], inference: dict[str, Any]) -> None:
        self.stream_id = stream.id
        self.source = source
        self.kind = stream.kind
        self.spaces = spaces
        self.inference = inference
        self.target_fps = max(1, min(int(stream.target_fps or 4), 15))
        self.status = "starting"
        self.last_error: str | None = None
        self.subscribers = 0
        self.frames_delivered = 0
        self.started_at = time.monotonic()
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self._seq = 0
        self._jpeg: bytes | None = None
        self._payload: dict[str, Any] = {}
        self._events: deque[dict] = deque(maxlen=50)
        self._thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name=f"stream-{self.stream_id}", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self.stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self.stop_event.is_set())

    def add_subscriber(self) -> int:
        with self._lock:
            self.subscribers += 1
            return self.subscribers

    def remove_subscriber(self) -> int:
        with self._lock:
            self.subscribers = max(0, self.subscribers - 1)
            return self.subscribers

    def snapshot(self) -> tuple[int, bytes | None, dict[str, Any]]:
        with self._lock:
            return self._seq, self._jpeg, self._payload

    def recent_events(self, limit: int = 20) -> list[dict]:
        with self._lock:
            return list(self._events)[:limit]

    # -- worker ------------------------------------------------------------
    def _run(self) -> None:
        try:
            import cv2  # noqa: F401  (imported here so unit tests can import this module)
        except ModuleNotFoundError as exc:  # pragma: no cover - guarded in video_pipeline too
            self._fail(f"{exc}. Install the backend requirements inside the project venv.")
            return

        import cv2

        self._set_status("live")
        capture = cv2.VideoCapture(self.source)
        if not capture.isOpened():
            self._fail("Could not open the source (connection refused or unsupported URL).")
            return

        try:
            self._loop(capture, cv2)
        except Exception as exc:  # pragma: no cover - defensive: keep the manager in control
            self._fail(f"{type(exc).__name__}: {exc}")
        finally:
            capture.release()
            if self.status == "live":
                self._set_status("idle")

    def _loop(self, capture, cv2) -> None:
        tracker = BayTracker(self.spaces)
        direction = DirectionDetector()
        roi = self._roi()
        frame_interval = 1.0 / self.target_fps
        inference_scale = max(480, min(int(self.inference.get("image_size", 1280)), 960))
        imgsz = int(self.inference.get("image_size", 1280))
        imgsz = min(imgsz, inference_scale)
        last_overcrowding = 0.0
        last_db_write = 0.0
        fps_ema = 0.0
        failures = 0

        max_seconds = int(env_settings.stream_max_seconds or 0)
        while not self.stop_event.is_set():
            if max_seconds and time.monotonic() - self.started_at > max_seconds:
                self._set_status("idle")
                return
            started = time.monotonic()
            ok, frame = capture.read()
            if not ok or frame is None:
                if self.kind == "video":
                    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = capture.read()
                if not ok or frame is None:
                    failures += 1
                    if self.kind != "video" and failures > 10:
                        self._fail("Source stopped delivering frames (10 consecutive failures).")
                        return
                    time.sleep(0.4)
                    continue
            failures = 0

            detections = self._detect(frame, imgsz, cv2)
            boxes: list[dict] = []
            centers: dict[int, tuple[float, float]] = {}
            confidences: list[float] = []
            for box in detections:
                x1, y1, x2, y2, conf, cls_id, track_id = box
                cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                centers[track_id] = (cx, cy)
                confidences.append(conf)
                boxes.append((x1, y1, x2, y2, conf, cls_id, track_id))

            transitions = tracker.update(list(centers.values()))
            crossings = direction.update(centers, roi)
            events = [
                {"type": "bay_state", "bay": t["bay"], "from": t["from"], "to": t["to"], "ts": utcnow().isoformat()}
                for t in transitions
            ] + crossings

            states = tracker.summary()
            occupied = sum(1 for bay in states if bay["state"] == "occupied")
            now = time.monotonic()
            if states and occupied / len(states) >= OVERCROWDING_RATIO and now - last_overcrowding > OVERCROWDING_COOLDOWN_S:
                last_overcrowding = now
                events.append(
                    {
                        "type": "overcrowding",
                        "occupied": occupied,
                        "total": len(states),
                        "ts": utcnow().isoformat(),
                    }
                )

            annotated = self._annotate(frame, boxes, states, cv2)
            jpeg = self._encode(annotated, cv2)

            elapsed = time.monotonic() - started
            fps_ema = fps_ema * 0.8 + (1.0 / max(elapsed, 1e-3)) * 0.2 if fps_ema else 1.0 / max(elapsed, 1e-3)
            payload = {
                "stream_id": self.stream_id,
                "ts": utcnow().isoformat(),
                "vehicle_count": len(boxes),
                "tracked": len(centers),
                "mean_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
                "bays": states,
                "occupied": occupied,
                "total": len(states),
                "events": events,
                "inference_fps": round(fps_ema, 2),
                "latency_ms": round(elapsed * 1000, 1),
                "model": self.inference.get("model"),
            }
            with self._lock:
                self._seq += 1
                self._jpeg = jpeg
                self._payload = payload
                self.frames_delivered += 1
                if events:
                    for event in events:
                        self._events.appendleft(event)

            if now - last_db_write > 5.0:
                last_db_write = now
                self._touch_db()

            spare = frame_interval - elapsed
            if spare > 0:
                self.stop_event.wait(spare)
            elif elapsed > 1.5 and self.target_fps > 1:  # adaptive degrade on slow hosts
                self.target_fps = max(1, self.target_fps - 1)
                frame_interval = 1.0 / self.target_fps

    # -- helpers -----------------------------------------------------------
    def _roi(self) -> list[list[float]]:
        if not self.spaces:
            return []
        xs = [p[0] for space in self.spaces for p in space.get("polygon", []) if len(p) == 2]
        ys = [p[1] for space in self.spaces for p in space.get("polygon", []) if len(p) == 2]
        if not xs or not ys:
            return []
        return [[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]]

    def _detect(self, frame, imgsz: int, cv2) -> list[tuple]:
        """Returns (x1, y1, x2, y2, conf, class_id, track_id) in pixel coordinates."""
        height, width = frame.shape[:2]
        model = get_model(self.inference.get("model", "yolo26s.pt"), self.inference.get("device", "auto"))
        conf = float(self.inference.get("confidence", 0.25))
        results = None
        try:
            results = model.track(
                frame,
                persist=True,
                conf=conf,
                imgsz=imgsz,
                verbose=False,
                tracker="bytetrack.yaml",
                classes=list(VEHICLE_CLASSES),
            )
        except Exception:
            results = None
        if results is None:
            results = model.predict(frame, conf=conf, imgsz=imgsz, verbose=False, classes=list(VEHICLE_CLASSES))
        result = results[0] if results else None
        boxes: list[tuple] = []
        if result is None or result.boxes is None or len(result.boxes) == 0:
            return boxes
        names = result.names or {}
        xyxy = result.boxes.xyxy.cpu().numpy()
        confs = result.boxes.conf.cpu().numpy()
        clss = result.boxes.cls.cpu().numpy().astype(int)
        track_ids = (
            result.boxes.id.cpu().numpy().astype(int)
            if getattr(result.boxes, "id", None) is not None
            else [-(i + 1) for i in range(len(xyxy))]
        )
        for idx in range(len(xyxy)):
            class_id = int(clss[idx])
            label = names.get(class_id, "")
            if label and label not in VEHICLE_CLASSES.values() and class_id not in VEHICLE_CLASSES:
                continue
            x1 = max(0.0, float(xyxy[idx][0]))
            y1 = max(0.0, float(xyxy[idx][1]))
            x2 = min(float(width), float(xyxy[idx][2]))
            y2 = min(float(height), float(xyxy[idx][3]))
            boxes.append((x1, y1, x2, y2, float(confs[idx]), class_id, int(track_ids[idx])))
        return boxes

    def _annotate(self, frame, boxes: list[tuple], bays: list[dict], cv2):
        import numpy as np

        height, width = frame.shape[:2]
        scale = env_settings.stream_width / width if width else 1.0
        if scale != 1.0:
            frame = cv2.resize(frame, (env_settings.stream_width, int(height * scale)))
            factor = scale
        else:
            factor = 1.0
        for bay, state in zip(bays, self.spaces or []):
            polygon = [(int(p[0] * frame.shape[1]), int(p[1] * frame.shape[0])) for p in state.get("polygon", [])]
            if len(polygon) < 3:
                continue
            color = {"occupied": (66, 90, 245), "free": (70, 200, 130)}.get(bay["state"], (120, 130, 150))
            cv2.polylines(frame, [np.array(polygon, dtype=np.int32)], True, color, 2, cv2.LINE_AA)
            top = polygon[0]
            label = f"{bay['name']} {bay['state']}"
            cv2.putText(
                frame,
                label,
                (top[0] + 4, max(14, top[1] - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
                cv2.LINE_AA,
            )
        for x1, y1, x2, y2, conf, _cls, track_id in boxes:
            pt1 = (int(x1 * factor), int(y1 * factor))
            pt2 = (int(x2 * factor), int(y2 * factor))
            cv2.rectangle(frame, pt1, pt2, (186, 139, 248), 2, cv2.LINE_AA)
            caption = f"#{track_id} {conf:.2f}" if track_id > 0 else f"{conf:.2f}"
            cv2.putText(
                frame,
                caption,
                (pt1[0], max(12, pt1[1] - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (186, 139, 248),
                1,
                cv2.LINE_AA,
            )
        hud = f"vehicles {len(boxes)}   bays {sum(1 for b in bays if b['state'] == 'occupied')}/{len(bays)}   {self.target_fps} fps"
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 26), (16, 20, 30), -1)
        cv2.putText(frame, hud, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (235, 240, 250), 1, cv2.LINE_AA)
        return frame

    def _encode(self, frame, cv2) -> bytes:
        ok, buffer = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(env_settings.stream_quality)]
        )
        if not ok:  # pragma: no cover - JPEG encode essentially never fails
            return b""
        return buffer.tobytes()

    def _fail(self, message: str) -> None:
        self.last_error = message
        self._set_status("error")

    def _set_status(self, status: str) -> None:
        self.status = status
        self._write_db(status=status, error=self.last_error)

    def _touch_db(self) -> None:
        self._write_db(status=None, error=None, touch=True)

    def _write_db(self, status: str | None, error: str | None, touch: bool = False) -> None:
        from ..database import SessionLocal

        session = SessionLocal()
        try:
            row = session.get(Stream, self.stream_id)
            if row is None:
                return
            if status:
                row.status = status
            if error is not None:
                row.last_error = error
            if status or touch:
                row.frames_delivered = self.frames_delivered
                row.subscriber_count = self.subscribers
            if touch:
                row.last_frame_at = utcnow()
            session.commit()
        except Exception:  # pragma: no cover - DB hiccups must not kill the feed
            session.rollback()
        finally:
            session.close()


class StreamManager:
    def __init__(self) -> None:
        self._sessions: dict[str, StreamSession] = {}
        self._lock = threading.Lock()

    def get(self, stream_id: str) -> StreamSession | None:
        with self._lock:
            session = self._sessions.get(stream_id)
        if session and not session.alive and session.status in {"error", "idle"}:
            return session
        return session

    def start(self, stream: Stream, spaces: list[dict], inference: dict[str, Any]) -> StreamSession:
        source = stream.url if stream.kind == "url" else None
        if stream.kind != "url":
            from ..database import SessionLocal
            from ..models import VideoJob

            db = SessionLocal()
            try:
                job = db.get(VideoJob, stream.video_id) if stream.video_id else None
                source = job.file_path if job else None
            finally:
                db.close()
        if not source:
            raise ValueError("Stream has no usable source")
        with self._lock:
            existing = self._sessions.get(stream.id)
            if existing and existing.alive:
                return existing
            session = StreamSession(stream, source, spaces, inference)
            self._sessions[stream.id] = session
        session.start()
        return session

    def stop(self, stream_id: str, timeout: float = 5.0) -> bool:
        with self._lock:
            session = self._sessions.pop(stream_id, None)
        if session is None:
            return False
        session.stop(timeout=timeout)
        if session.status == "live":
            session._write_db(status="idle", error=None)
        return True

    def stop_if_idle(self, stream_id: str) -> None:
        session = self.get(stream_id)
        if session is None:
            return
        if session.subscribers <= 0:
            self.stop(stream_id, timeout=2.0)

    def active(self) -> dict[str, StreamSession]:
        with self._lock:
            return {key: value for key, value in self._sessions.items() if value.alive}

    def reset_on_startup(self) -> None:
        """Sessions are in-memory; mark any stale 'live' rows as idle after a restart."""
        from ..database import SessionLocal
        from ..models import Stream as StreamRow

        db = SessionLocal()
        try:
            db.query(StreamRow).filter(StreamRow.status == "live").update(
                {"status": "idle", "subscriber_count": 0}
            )
            db.commit()
        finally:
            db.close()

    def shutdown(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.stop(timeout=3.0)


manager = StreamManager()


def snapshot_for(stream: Stream, spaces: list[dict], inference: dict[str, Any]) -> bytes | None:
    """Grab one annotated frame (running session first, else a one-shot capture)."""
    session = manager.get(stream.id)
    if session and session.alive:
        _, jpeg, _ = session.snapshot()
        if jpeg:
            return jpeg
    source = stream.url if stream.kind == "url" else None
    if stream.kind != "url":
        from ..database import SessionLocal
        from ..models import VideoJob

        db = SessionLocal()
        try:
            job = db.get(VideoJob, stream.video_id) if stream.video_id else None
            source = job.file_path if job else None
        finally:
            db.close()
    if not source:
        return None
    import cv2

    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        return None
    try:
        ok, frame = capture.read()
        if not ok or frame is None:
            return None
        session = StreamSession(stream, source, spaces, inference)
        return session._encode(session._annotate(frame, [], session_dummy_bays(spaces), cv2), cv2)
    finally:
        capture.release()


def session_dummy_bays(spaces: list[dict]) -> list[dict]:
    return [
        {"name": space.get("name") or f"Bay {i + 1}", "state": "unknown", "confidence": 0.0}
        for i, space in enumerate(spaces)
    ]


def save_snapshot(stream_id: str, jpeg: bytes) -> str:
    folder = env_settings.data_path / "streams"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stream_id}_calib.jpg"
    path.write_bytes(jpeg)
    return str(path)


def load_spaces(stream: Stream) -> list[dict]:
    try:
        parsed = json.loads(stream.spaces_json or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [space for space in parsed if isinstance(space, dict) and len(space.get("polygon") or []) >= 3]
