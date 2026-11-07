"""Trust-aware bay occupancy state machine (Change Set 1, C1.2/C1.3).

Replaces centre-point-in-polygon & sample-count smoothing with:
- Overlap ratio evidence (box ∩ polygon ÷ bay area, and ÷ box area)
- Hysteresis measured in seconds, independent of stride/FPS
- Image quality gating (degraded frame -> unknown state, never false-free)
- Five distinct states: free | occupied | unknown | stale | out_of_service
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import math
from typing import Any

import numpy as np

try:
    import cv2
except ModuleNotFoundError:  # pragma: no cover
    cv2 = None

logger = logging.getLogger(__name__)

STATE_FREE = "free"
STATE_OCCUPIED = "occupied"
STATE_UNKNOWN = "unknown"
STATE_STALE = "stale"
STATE_OUT_OF_SERVICE = "out_of_service"

CONFIRMED_STATES = frozenset({STATE_FREE, STATE_OCCUPIED})
RULE_VERSION = "bay-state-v2"


@dataclass(frozen=True)
class BayTuning:
    enter_occupied_dwell_s: float = 1.0
    enter_free_dwell_s: float = 2.0
    min_bay_coverage: float = 0.35
    min_box_coverage: float = 0.25
    quality_min_luminance: float = 15.0
    quality_min_sharpness: float = 30.0
    frozen_max_delta: float = 1.0


@dataclass(frozen=True)
class QualityReport:
    ok: bool
    luminance: float
    sharpness: float
    frozen: bool
    reason: str | None = None


class QualityGate:
    """Per-frame image quality assessment: luminance, sharpness (Laplacian variance), and frozen-frame hash."""

    def __init__(self, tuning: BayTuning | None = None) -> None:
        self.tuning = tuning or BayTuning()
        self._prev_small: np.ndarray | None = None

    def assess(self, frame: np.ndarray) -> QualityReport:
        if cv2 is None or frame is None or frame.size == 0:
            return QualityReport(ok=False, luminance=0.0, sharpness=0.0, frozen=False, reason="Invalid frame")

        try:
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame

            luminance = float(gray.mean())
            # Sharpness via variance of Laplacian
            sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

            # Frozen frame detection using 64x36 downsampled mean absolute difference
            small = cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA)
            frozen = False
            if self._prev_small is not None:
                delta = float(np.abs(small.astype(np.float32) - self._prev_small.astype(np.float32)).mean())
                if delta < self.tuning.frozen_max_delta:
                    frozen = True
            self._prev_small = small

            ok = True
            reason = None
            if luminance < self.tuning.quality_min_luminance:
                ok = False
                reason = f"Luminance too low ({luminance:.1f} < {self.tuning.quality_min_luminance})"
            elif sharpness < self.tuning.quality_min_sharpness:
                ok = False
                reason = f"Frame too blurry ({sharpness:.1f} < {self.tuning.quality_min_sharpness})"
            elif frozen:
                ok = False
                reason = "Frozen video frame detected"

            return QualityReport(ok=ok, luminance=luminance, sharpness=sharpness, frozen=frozen, reason=reason)
        except Exception as exc:  # pragma: no cover
            return QualityReport(ok=False, luminance=0.0, sharpness=0.0, frozen=False, reason=str(exc))


def polygon_box_overlap(polygon_px: np.ndarray, box_px: list[int] | tuple[int, int, int, int]) -> tuple[float, float]:
    """Calculate (bay_coverage, box_coverage) for a polygon and box [x1, y1, x2, y2]."""
    if cv2 is None or len(polygon_px) < 3:
        return 0.0, 0.0

    x1, y1, x2, y2 = box_px
    box_w = max(1, x2 - x1)
    box_h = max(1, y2 - y1)
    box_area = float(box_w * box_h)

    poly_pts = polygon_px.reshape((-1, 1, 2)).astype(np.int32)
    bay_area = float(cv2.polygonArea(poly_pts))
    if bay_area <= 0:
        return 0.0, 0.0

    box_poly = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.int32)

    try:
        # Try fast convex intersection first
        success, intersection = cv2.intersectConvexConvex(
            poly_pts.astype(np.float32), box_poly.astype(np.float32)
        )
        if success and intersection is not None and len(intersection) >= 3:
            inter_area = float(cv2.polygonArea(intersection))
            return min(1.0, inter_area / bay_area), min(1.0, inter_area / box_area)
    except cv2.error:
        pass

    # Fallback to crop mask intersection for arbitrary non-convex polygons
    min_x = max(0, min(int(polygon_px[:, 0].min()), x1))
    max_x = max(min_x + 1, max(int(polygon_px[:, 0].max()), x2))
    min_y = max(0, min(int(polygon_px[:, 1].min()), y1))
    max_y = max(min_y + 1, max(int(polygon_px[:, 1].max()), y2))

    crop_w = max_x - min_x
    crop_h = max_y - min_y
    if crop_w > 2000 or crop_h > 2000:  # Safety guard for giant masks
        return 0.0, 0.0

    bay_mask = np.zeros((crop_h, crop_w), dtype=np.uint8)
    poly_shifted = polygon_px - np.array([min_x, min_y])
    cv2.fillPoly(bay_mask, [poly_shifted.astype(np.int32)], 255)

    bx1, my1 = max(0, x1 - min_x), max(0, y1 - min_y)
    bx2, my2 = min(crop_w, x2 - min_x), min(crop_h, y2 - min_y)

    if bx2 <= bx1 or my2 <= my1:
        return 0.0, 0.0

    inter_area = float(np.count_nonzero(bay_mask[my1:my2, bx1:bx2]))
    return min(1.0, inter_area / bay_area), min(1.0, inter_area / box_area)


@dataclass
class BayTransition:
    bay_id: str
    from_state: str
    to_state: str
    confidence: float | None
    confidence_band: str
    timestamp_s: float


def confidence_band(confidence: float | None) -> str:
    if confidence is None:
        return "none"
    if confidence >= 0.70:
        return "high"
    if confidence >= 0.40:
        return "medium"
    return "low"


class BayStateMachine:
    """State machine tracking per-bay state with time-based hysteresis & quality gating."""

    def __init__(
        self,
        bays: list[tuple[str, str, np.ndarray]],  # (bay_id, bay_name, polygon_px)
        tuning: BayTuning | None = None,
        model_name: str | None = None,
    ) -> None:
        self.tuning = tuning or BayTuning()
        self.model_name = model_name
        self.bays = bays
        self.states: dict[str, str] = {bay_id: STATE_UNKNOWN for bay_id, _, _ in bays}
        self.confidences: dict[str, float | None] = {bay_id: None for bay_id, _, _ in bays}
        self._evidence_s: dict[str, float] = {bay_id: 0.0 for bay_id, _, _ in bays}
        self._clear_s: dict[str, float] = {bay_id: 0.0 for bay_id, _, _ in bays}
        self._last_t: float | None = None

    def update(
        self,
        timestamp_s: float,
        boxes: list[dict],
        quality: QualityReport,
    ) -> list[BayTransition]:
        dt = 0.0 if self._last_t is None else max(0.0, timestamp_s - self._last_t)
        self._last_t = timestamp_s
        transitions: list[BayTransition] = []

        for bay_id, _, polygon_px in self.bays:
            prev = self.states[bay_id]
            if prev == STATE_OUT_OF_SERVICE:
                continue

            if not quality.ok:
                # Degraded image quality immediately forces unknown state, resetting timers
                self._evidence_s[bay_id] = 0.0
                self._clear_s[bay_id] = 0.0
                new_state = STATE_UNKNOWN
                best_conf = None
            else:
                # Check overlaps
                matching_scores: list[float] = []
                for box in boxes:
                    bay_cov, box_cov = polygon_box_overlap(polygon_px, box["box"])
                    if bay_cov >= self.tuning.min_bay_coverage or box_cov >= self.tuning.min_box_coverage:
                        conf = box.get("confidence", 0.5)
                        # Scale confidence by relative bay coverage
                        eff_conf = conf * min(1.0, bay_cov / max(self.tuning.min_bay_coverage, 1e-6))
                        matching_scores.append(eff_conf)

                has_evidence = len(matching_scores) > 0
                if has_evidence:
                    self._evidence_s[bay_id] += dt
                    self._clear_s[bay_id] = 0.0
                    best_conf = max(matching_scores)
                else:
                    self._clear_s[bay_id] += dt
                    self._evidence_s[bay_id] = 0.0
                    best_conf = None

                # Apply time-based hysteresis
                if self._evidence_s[bay_id] >= self.tuning.enter_occupied_dwell_s:
                    new_state = STATE_OCCUPIED
                elif self._clear_s[bay_id] >= self.tuning.enter_free_dwell_s:
                    new_state = STATE_FREE
                elif prev in CONFIRMED_STATES:
                    new_state = prev  # Hold previous confirmed state while in hysteresis window
                else:
                    new_state = STATE_UNKNOWN

            self.states[bay_id] = new_state
            self.confidences[bay_id] = best_conf if new_state == STATE_OCCUPIED else None

            if prev != new_state and not (prev == STATE_UNKNOWN and new_state == STATE_UNKNOWN):
                transitions.append(
                    BayTransition(
                        bay_id=bay_id,
                        from_state=prev,
                        to_state=new_state,
                        confidence=self.confidences[bay_id],
                        confidence_band=confidence_band(self.confidences[bay_id]),
                        timestamp_s=timestamp_s,
                    )
                )

        return transitions

    def mark_out_of_service(self, bay_id: str) -> None:
        if bay_id in self.states:
            self.states[bay_id] = STATE_OUT_OF_SERVICE
            self.confidences[bay_id] = None

    def mark_stale(self, timestamp_s: float) -> list[BayTransition]:
        transitions: list[BayTransition] = []
        for bay_id in self.states:
            prev = self.states[bay_id]
            if prev in CONFIRMED_STATES:
                self.states[bay_id] = STATE_STALE
                self.confidences[bay_id] = None
                transitions.append(
                    BayTransition(
                        bay_id=bay_id,
                        from_state=prev,
                        to_state=STATE_STALE,
                        confidence=None,
                        confidence_band="none",
                        timestamp_s=timestamp_s,
                    )
                )
        return transitions
