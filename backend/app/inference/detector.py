"""Detector abstraction layer for ParkWise.

Decouples detection and tracking from any single vendor library:
- Provides a clean Detector Protocol.
- Allows pluggable backends: Ultralytics (AGPL-3.0 / Enterprise), ONNX Runtime / OpenCV DNN (Apache-2.0 / MIT), and MockDetector (testing).
- Explicitly surfaces model name, backend, and license for compliance scans, /api/system/info, and SBOMs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence
import numpy as np


@dataclass(frozen=True, slots=True)
class Detection:
    xyxy: tuple[float, float, float, float]
    confidence: float
    cls: str
    class_id: int = 2
    track_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "box": [int(round(float(c))) for c in self.xyxy],
            "confidence": float(self.confidence),
            "class_id": int(self.class_id),
            "cls": self.cls,
            "track_id": int(self.track_id) if self.track_id is not None else None,
        }


class Detector(Protocol):
    name: str
    backend: str
    license: str

    def warmup(self) -> None:
        """Warm up predictor/session caches."""
        ...

    def detect(
        self,
        frames: Sequence[np.ndarray],
        confidence: float = 0.25,
        imgsz: int = 640,
    ) -> list[list[Detection]]:
        """Run batch vehicle detection over one or more frames."""
        ...

    def track(
        self,
        stream_key: str,
        frame: np.ndarray,
        confidence: float = 0.25,
        imgsz: int = 640,
    ) -> list[Detection]:
        """Run vehicle tracking with persistent track IDs for a specific stream."""
        ...


# COCO vehicle classes: car (2), motorcycle (3), bus (5), truck (7)
VEHICLE_COCO_CLASSES = [2, 3, 5, 7]
COCO_CLASS_NAMES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


class UltralyticsDetector:
    """Ultralytics YOLO detector wrapper with ByteTrack tracking.
    
    License Notice:
    Ultralytics YOLO is licensed under AGPL-3.0 for open-source / copyleft use,
    or requires an Ultralytics Enterprise license for proprietary network distribution.
    """

    def __init__(self, model_name: str = "yolo26s.pt", device: str = "auto") -> None:
        self.name = model_name
        self.device = device
        self.backend = "ultralytics"
        self.license = "AGPL-3.0 / Enterprise"
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from ..services.model_store import get_model
            self._model = get_model(self.name, self.device)
        return self._model

    def warmup(self) -> None:
        model = self._ensure_model()
        dummy = np.zeros((320, 320, 3), dtype=np.uint8)
        try:
            model.predict(dummy, imgsz=320, verbose=False)
        except Exception:
            pass

    def detect(
        self,
        frames: Sequence[np.ndarray],
        confidence: float = 0.25,
        imgsz: int = 640,
    ) -> list[list[Detection]]:
        model = self._ensure_model()
        results_list: list[list[Detection]] = []
        for frame in frames:
            kwargs = {
                "conf": confidence,
                "imgsz": imgsz,
                "classes": VEHICLE_COCO_CLASSES,
                "verbose": False,
            }
            if self.device != "auto":
                kwargs["device"] = self.device
            result = model.predict(frame, **kwargs)[0]
            results_list.append(self._parse_yolo_result(result))
        return results_list

    def track(
        self,
        stream_key: str,
        frame: np.ndarray,
        confidence: float = 0.25,
        imgsz: int = 640,
    ) -> list[Detection]:
        from ..services.model_store import get_stream_model
        model = get_stream_model(self.name, self.device, stream_key)
        result = model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            conf=confidence,
            imgsz=imgsz,
            classes=VEHICLE_COCO_CLASSES,
            verbose=False,
        )[0]
        return self._parse_yolo_result(result)

    def _parse_yolo_result(self, result: Any) -> list[Detection]:
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []
        xyxy = boxes.xyxy.cpu().tolist()
        confidences = boxes.conf.cpu().tolist()
        classes = boxes.cls.cpu().tolist()
        ids = boxes.id.cpu().tolist() if boxes.id is not None else [None] * len(xyxy)

        detections: list[Detection] = []
        for coords, conf, class_id, track_id in zip(xyxy, confidences, classes, ids):
            cid = int(class_id)
            detections.append(
                Detection(
                    xyxy=(float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])),
                    confidence=float(conf),
                    cls=COCO_CLASS_NAMES.get(cid, "vehicle"),
                    class_id=cid,
                    track_id=int(track_id) if track_id is not None else None,
                )
            )
        return detections


class MockDetector:
    """Deterministic mock detector for unit tests and CI without CV weights."""

    def __init__(self, name: str = "mock-yolo", detections: list[Detection] | None = None) -> None:
        self.name = name
        self.backend = "mock"
        self.license = "MIT"
        self._preset = detections or [
            Detection(xyxy=(100.0, 100.0, 250.0, 300.0), confidence=0.92, cls="car", class_id=2, track_id=1)
        ]

    def warmup(self) -> None:
        pass

    def detect(
        self,
        frames: Sequence[np.ndarray],
        confidence: float = 0.25,
        imgsz: int = 640,
    ) -> list[list[Detection]]:
        return [[d for d in self._preset if d.confidence >= confidence] for _ in frames]

    def track(
        self,
        stream_key: str,
        frame: np.ndarray,
        confidence: float = 0.25,
        imgsz: int = 640,
    ) -> list[Detection]:
        return [d for d in self._preset if d.confidence >= confidence]


def get_detector(name: str = "yolo26s.pt", device: str = "auto") -> Detector:
    """Detector factory with fallbacks for testing."""
    if name.startswith("mock"):
        return MockDetector(name=name)
    return UltralyticsDetector(model_name=name, device=device)
