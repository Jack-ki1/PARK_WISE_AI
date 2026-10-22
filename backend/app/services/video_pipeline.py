from __future__ import annotations

import json
import logging
import math
import shutil
import subprocess
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from uuid import uuid4

try:
    import cv2
except ModuleNotFoundError as exc:  # pragma: no cover - only hit with a broken interpreter choice
    raise ModuleNotFoundError(
        "OpenCV (cv2) is missing from this interpreter. Run the API from the project virtualenv, "
        "e.g. `.venv/bin/python3 -m uvicorn app.main:app --app-dir backend --reload`, "
        "or start everything with `./scripts/run_local.sh`."
    ) from exc
import numpy as np
from sqlalchemy import delete

from ..config import settings
from ..database import SessionLocal
from ..models import DetectionSample, OccupancySample, ParkingSpace, VideoJob
from . import integrations as integrations_service
from . import settings_store
from .activity import record as record_activity
from .model_store import get_model

logger = logging.getLogger(__name__)
VEHICLE_COCO_CLASSES = [2, 3, 5, 7]  # car, motorcycle, bus, truck in COCO
# A frame this small on vehicle classes is re-run at higher resolution (see _scale_candidates).
MULTISCALE_MIN_VEHICLES = 5


def _ffmpeg_executable() -> str | None:
    """Locate ffmpeg: system install first, then the bundled imageio-ffmpeg binary."""
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None



def inspect_video(path: Path, preview_path: Path) -> dict:
    """Read real media metadata and create a real first-frame preview."""
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError("File is not a readable video. Check the codec/container and try MP4, MOV, or AVI.")
        ok, frame = cap.read()
        if not ok or frame is None:
            raise ValueError("The video has no readable first frame.")
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or frame.shape[1])
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or frame.shape[0])
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if not math.isfinite(fps) or fps <= 0:
            fps = 0.0
        duration = count / fps if count > 0 and fps > 0 else None
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        max_width = 1600
        if width > max_width:
            scale = max_width / width
            frame = cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
        if not cv2.imwrite(str(preview_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            raise ValueError("Could not create the preview image.")
        return {"width": width, "height": height, "fps": fps, "frame_count": count, "duration": duration}
    finally:
        cap.release()


def _vehicle_boxes(result) -> list[dict]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []
    xyxy = boxes.xyxy.cpu().tolist()
    confidences = boxes.conf.cpu().tolist()
    classes = boxes.cls.cpu().tolist()
    ids = boxes.id.cpu().tolist() if boxes.id is not None else [None] * len(xyxy)
    rows = []
    for coords, confidence, class_id, track_id in zip(xyxy, confidences, classes, ids):
        rows.append({
            "box": [int(round(float(x))) for x in coords],
            "confidence": float(confidence),
            "class_id": int(class_id),
            "track_id": int(track_id) if track_id is not None else None,
        })
    return rows


def _model_kwargs(imgsz: int, cfg: dict) -> dict:
    kwargs = {
        "conf": cfg["confidence"],
        "imgsz": imgsz,
        "classes": VEHICLE_COCO_CLASSES,
        "verbose": False,
    }
    if cfg["device"] != "auto":
        kwargs["device"] = cfg["device"]
    return kwargs


def _detect_pass(model, frame: np.ndarray, imgsz: int, *, track: bool, cfg: dict) -> list[dict]:
    """One vehicle-only detection pass. Only the primary pass runs ByteTrack."""
    if track:
        result = model.track(frame, persist=True, tracker="bytetrack.yaml", **_model_kwargs(imgsz, cfg))[0]
    else:
        result = model.predict(frame, **_model_kwargs(imgsz, cfg))[0]
    return _vehicle_boxes(result)


def _scale_candidates(width: int, cfg: dict) -> list[int]:
    """Inference resolutions to try, cheapest first: configured size, then sharper passes.

    Dense aerial footage is scale-sensitive: a pass that fits the model's training scale
    detects close-up vehicles, while zoomed-out frames need native-resolution inference.
    """
    sizes = [max(320, int(cfg["image_size"]))]
    if cfg["multiscale"] and width > sizes[0]:
        for alternate in (2560, width):
            size = min(alternate, width)
            if size > sizes[-1]:
                sizes.append(size)
    return sizes


def _merge_vehicle_boxes(primary: list[dict], secondary: list[dict], cfg: dict) -> list[dict]:
    """Class-wise NMS across passes; boxes with ByteTrack IDs win ties."""
    if not secondary:
        return primary
    if not primary:
        return secondary
    rows = primary + secondary
    widths = [max(1, row["box"][2] - row["box"][0]) for row in rows]
    heights = [max(1, row["box"][3] - row["box"][1]) for row in rows]
    boxes = [[row["box"][0], row["box"][1], w, h] for row, w, h in zip(rows, widths, heights)]
    scores = [row["confidence"] for row in rows]
    try:
        keep = cv2.dnn.NMSBoxes(boxes, scores, cfg["confidence"], 0.5)
    except cv2.error:
        return primary
    if keep is None or len(keep) == 0:
        return primary
    return [rows[int(index)] for index in np.array(keep).flatten()]


def _space_states(frame: np.ndarray, boxes: list[dict], spaces: list[ParkingSpace], history: dict[str, deque]) -> dict[str, tuple[str, float | None]]:
    """Map detection centers to calibrated normalized polygons, with short smoothing."""
    height, width = frame.shape[:2]
    output: dict[str, tuple[str, float | None]] = {}
    for space in spaces:
        try:
            points = json.loads(space.polygon_json)
        except (TypeError, json.JSONDecodeError):
            output[space.id] = ("unknown", None)
            continue
        polygon = np.array([[int(float(x) * width), int(float(y) * height)] for x, y in points], dtype=np.int32)
        matching = []
        for box in boxes:
            x1, y1, x2, y2 = box["box"]
            cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
            if cv2.pointPolygonTest(polygon, (float(cx), float(cy)), False) >= 0:
                matching.append(box)
        occupied_now = bool(matching)
        history[space.id].append(occupied_now)
        observations = list(history[space.id])
        if len(observations) >= 3 and sum(observations) >= math.ceil(len(observations) * 0.6):
            state = "occupied"
        elif len(observations) >= 3 and sum(observations) <= math.floor(len(observations) * 0.2):
            state = "free"
        elif space.state in {"occupied", "free"}:
            state = space.state
        else:
            state = "unknown"
        confidence = max((box["confidence"] for box in matching), default=None)
        output[space.id] = (state, confidence)
    return output


def _notify_quietly(db, job) -> None:
    try:
        integrations_service.notify_job(db, job)
    except Exception:  # pragma: no cover - delivery must never break a finished run
        logger.warning("Webhook dispatch failed for job %s", job.id, exc_info=True)


def process_video_job(video_id: str) -> None:
    """Synchronous worker function. FastAPI runs this in a threadpool background task."""
    db = SessionLocal()
    cap = None
    writer = None
    try:
        job = db.get(VideoJob, video_id)
        if not job:
            return
        if job.status == "processing":
            logger.warning("Job %s is already processing; ignoring duplicate request", video_id)
            return
        source_path = Path(job.file_path)
        if not source_path.exists():
            raise FileNotFoundError("Original video file no longer exists on this server.")
        job.status = "processing"
        db.query(DetectionSample).filter(DetectionSample.video_id == video_id).delete(synchronize_session=False)
        db.query(OccupancySample).filter(OccupancySample.video_id == video_id).delete(synchronize_session=False)
        for old_space in db.query(ParkingSpace).filter(ParkingSpace.video_id == video_id).all():
            old_space.state = "unknown"
            old_space.confidence = None
            old_space.last_seen_seconds = None
        job.progress_percent = 0.0
        job.error_message = None
        job.started_at = datetime.now(timezone.utc)
        cfg = settings_store.inference_config(db)  # dashboard overrides win over env defaults
        job.model_name = cfg["model"]
        db.commit()

        # Model weights load lazily (and are shared with live view sessions) so app
        # startup and API docs stay available without the heavyweight CV runtime.
        model = get_model(cfg["model"], cfg["device"])
        cap = cv2.VideoCapture(str(source_path))
        if not cap.isOpened():
            raise ValueError("OpenCV could not open this video. Re-encode to H.264 MP4 and retry.")
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or job.width or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or job.height or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or job.fps or 25.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or job.source_frame_count or 0)
        duration = total_frames / fps if total_frames > 0 and fps > 0 else job.duration_seconds
        if duration is not None and duration > settings.max_video_seconds:
            raise ValueError(f"Video is {duration:.0f}s; limit is {settings.max_video_seconds}s. Trim it before analysis.")
        if width < 2 or height < 2:
            raise ValueError("Video metadata is missing valid dimensions.")

        output_path = settings.data_path / "processed" / f"{video_id}_annotated.mp4"
        raw_output_path = settings.data_path / "processed" / f"{video_id}_annotated_opencv.mp4"
        output_fps = max(1.0, (fps if fps > 0 else 25.0) / max(1, cfg["frame_stride"]))
        writer = cv2.VideoWriter(str(raw_output_path), cv2.VideoWriter_fourcc(*"mp4v"), output_fps, (width, height))
        if not writer.isOpened():
            raw_output_path = settings.data_path / "processed" / f"{video_id}_annotated_opencv.avi"
            writer = cv2.VideoWriter(str(raw_output_path), cv2.VideoWriter_fourcc(*"MJPG"), output_fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError("Could not initialize an output-video writer. Check available OpenCV codecs/FFmpeg.")

        spaces = db.query(ParkingSpace).filter(ParkingSpace.video_id == video_id).all()
        state_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=5))
        samples_to_save: list[DetectionSample] = []
        occupancy_to_save: list[OccupancySample] = []
        frame_index = -1
        processed_index = 0
        max_vehicles = 0
        confidence_values: list[float] = []
        stride = max(1, int(cfg["frame_stride"]))
        scale_candidates = _scale_candidates(width, cfg)
        started = time.monotonic()

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_index += 1
            if frame_index % stride != 0:
                continue
            detections = _detect_pass(model, frame, scale_candidates[0], track=True, cfg=cfg)
            if len(detections) < MULTISCALE_MIN_VEHICLES:
                # Sharpness matters more than speed here: a zoomed-out frame can hide
                # dozens of vehicles from the configured (smaller) inference scale.
                for alternate in scale_candidates[1:]:
                    detections = _merge_vehicle_boxes(
                        detections, _detect_pass(model, frame, alternate, track=False, cfg=cfg), cfg
                    )
                    if len(detections) >= MULTISCALE_MIN_VEHICLES:
                        break
            confs = [d["confidence"] for d in detections]
            confidence_values.extend(confs)
            mean_conf = mean(confs) if confs else None
            vehicle_count = len(detections)
            tracked_count = len({d["track_id"] for d in detections if d["track_id"] is not None})
            max_vehicles = max(max_vehicles, vehicle_count)
            timestamp_s = frame_index / fps if fps > 0 else float(processed_index)

            # Space state based on user-calibrated geometry, never inferred from a global count.
            states = _space_states(frame, detections, spaces, state_history) if spaces else {}
            for space in spaces:
                state, confidence = states[space.id]
                # _space_states already reports the last confirmed state while the
                # smoothing window is undecided, so a known bay never flips to
                # "unknown" mid-run; it only resets when a job is re-queued.
                if state in {"occupied", "free"}:
                    space.state = state
                space.confidence = confidence
                space.last_seen_seconds = timestamp_s
                occupancy_to_save.append(OccupancySample(
                    video_id=video_id,
                    space_id=space.id,
                    timestamp_seconds=timestamp_s,
                    state=space.state,
                    confidence=confidence,
                ))

            # Annotate real frames; palette is for visualization only, not a claim of certainty.
            for det in detections:
                x1, y1, x2, y2 = det["box"]
                label = f"{det['track_id'] if det['track_id'] is not None else 'vehicle'} {det['confidence']:.2f}"
                cv2.rectangle(frame, (x1, y1), (x2, y2), (180, 120, 255), 2)
                cv2.putText(frame, label, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (240, 240, 240), 2, cv2.LINE_AA)
            for space in spaces:
                points = json.loads(space.polygon_json)
                polygon = np.array([[int(float(x) * width), int(float(y) * height)] for x, y in points], dtype=np.int32)
                color = (60, 190, 100) if space.state == "free" else ((50, 70, 235) if space.state == "occupied" else (140, 140, 140))
                cv2.polylines(frame, [polygon], True, color, 2, cv2.LINE_AA)
                anchor = tuple(polygon[0].tolist())
                cv2.putText(frame, space.name, anchor, cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
            cv2.putText(frame, f"ParkWise AI | observed vehicles: {vehicle_count}", (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
            writer.write(frame)

            samples_to_save.append(DetectionSample(
                video_id=video_id,
                frame_number=frame_index,
                timestamp_seconds=round(timestamp_s, 3),
                vehicle_count=vehicle_count,
                tracked_vehicle_count=tracked_count,
                mean_confidence=mean_conf,
            ))
            processed_index += 1
            if len(samples_to_save) >= 20:
                db.add_all(samples_to_save)
                db.add_all(occupancy_to_save)
                samples_to_save.clear()
                occupancy_to_save.clear()
                job = db.get(VideoJob, video_id)
                if job:
                    job.current_frame = frame_index
                    job.processed_frames = processed_index
                    job.progress_percent = min(99.0, (frame_index + 1) * 100 / total_frames) if total_frames else 0.0
                    job.max_vehicle_count = max_vehicles
                    job.avg_confidence = mean(confidence_values) if confidence_values else None
                db.commit()
        if processed_index == 0:
            raise ValueError("No readable frames were processed from this video.")
        if samples_to_save:
            db.add_all(samples_to_save)
        if occupancy_to_save:
            db.add_all(occupancy_to_save)
        cap.release()
        cap = None
        writer.release()
        writer = None

        # Prefer H.264 MP4 for browser compatibility; fall back to the OpenCV file if ffmpeg
        # is missing or this host lacks the libx264 encoder.
        ffmpeg = _ffmpeg_executable()
        if raw_output_path.suffix.lower() == ".mp4" and ffmpeg:
            try:
                conversion = subprocess.run(
                    [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_output_path), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path)],
                    capture_output=True, text=True, timeout=900, check=False,
                )
                if conversion.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 0:
                    raw_output_path.unlink(missing_ok=True)
                else:
                    logger.warning("H.264 conversion failed for %s: %s", video_id, conversion.stderr[-500:])
                    output_path = raw_output_path
            except (OSError, subprocess.TimeoutExpired) as conversion_error:
                logger.warning("Could not convert annotated output for %s: %s", video_id, conversion_error)
                output_path = raw_output_path
        else:
            output_path = raw_output_path

        # Generate a preview from a real annotated frame, if a video frame is available.
        preview_path = settings.data_path / "previews" / f"{video_id}.jpg"
        annotated_cap = cv2.VideoCapture(str(output_path))
        try:
            preview_ok, preview_frame = annotated_cap.read()
            if preview_ok and preview_frame is not None:
                preview_frame = cv2.resize(preview_frame, (min(1600, width), int(height * min(1600 / width, 1.0)))) if width > 1600 else preview_frame
                cv2.imwrite(str(preview_path), preview_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        finally:
            annotated_cap.release()

        job = db.get(VideoJob, video_id)
        if job:
            job.status = "completed"
            job.progress_percent = 100.0
            job.current_frame = max(frame_index, 0)
            job.processed_frames = processed_index
            job.max_vehicle_count = max_vehicles
            job.avg_confidence = mean(confidence_values) if confidence_values else None
            job.processed_video_path = str(output_path)
            job.preview_path = str(preview_path) if preview_path.exists() else job.preview_path
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            record_activity(db, "system", "analysis.completed", "video", video_id, f"{processed_index} samples, peak {max_vehicles} vehicles")
            _notify_quietly(db, job)
        logger.info("Processed video %s: %s samples in %.1fs", video_id, processed_index, time.monotonic() - started)
    except Exception as exc:  # persist failure so the dashboard explains what actually happened
        logger.exception("Video job %s failed", video_id)
        try:
            db.rollback()
            job = db.get(VideoJob, video_id)
            if job:
                job.status = "failed"
                job.error_message = f"{type(exc).__name__}: {exc}"[:2000]
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                record_activity(db, "system", "analysis.failed", "video", video_id, job.error_message[:200])
                _notify_quietly(db, job)
        except Exception:
            logger.exception("Could not persist failure for video %s", video_id)
    finally:
        if cap is not None:
            cap.release()
        if writer is not None:
            writer.release()
        db.close()
