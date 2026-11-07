"""Unit tests for the trust-aware BayStateMachine and QualityGate."""

import numpy as np
import pytest

from app.services.bay_state import (
    BayStateMachine,
    BayTuning,
    QualityGate,
    QualityReport,
    confidence_band,
    polygon_box_overlap,
    STATE_FREE,
    STATE_OCCUPIED,
    STATE_OUT_OF_SERVICE,
    STATE_STALE,
    STATE_UNKNOWN,
)


class TestConfidenceBand:
    def test_bands(self):
        assert confidence_band(None) == "none"
        assert confidence_band(0.85) == "high"
        assert confidence_band(0.70) == "high"
        assert confidence_band(0.55) == "medium"
        assert confidence_band(0.40) == "medium"
        assert confidence_band(0.20) == "low"


class TestQualityGate:
    def test_empty_or_none_frame(self):
        gate = QualityGate()
        rep = gate.assess(None)
        assert not rep.ok
        assert rep.reason == "Invalid frame"

        rep_empty = gate.assess(np.array([]))
        assert not rep_empty.ok

    def test_low_luminance(self):
        gate = QualityGate(BayTuning(quality_min_luminance=20.0))
        dark_frame = np.full((100, 100, 3), 10, dtype=np.uint8)
        rep = gate.assess(dark_frame)
        assert not rep.ok
        assert "Luminance too low" in (rep.reason or "")

    def test_blurry_frame(self):
        gate = QualityGate(BayTuning(quality_min_sharpness=50.0))
        # Uniform color has 0 variance of Laplacian
        flat_frame = np.full((100, 100, 3), 150, dtype=np.uint8)
        rep = gate.assess(flat_frame)
        assert not rep.ok
        assert "blurry" in (rep.reason or "").lower()

    def test_frozen_frame_detection(self):
        gate = QualityGate(BayTuning(quality_min_luminance=10.0, quality_min_sharpness=5.0, frozen_max_delta=1.0))
        # Create noisy frame to pass sharpness and luminance
        np.random.seed(42)
        frame1 = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
        frame2 = frame1.copy()

        rep1 = gate.assess(frame1)
        assert rep1.ok
        assert not rep1.frozen

        rep2 = gate.assess(frame2)
        assert not rep2.ok
        assert rep2.frozen
        assert "Frozen video frame" in (rep2.reason or "")

    def test_valid_sharp_frame(self):
        gate = QualityGate(BayTuning(quality_min_luminance=15.0, quality_min_sharpness=20.0))
        np.random.seed(123)
        frame1 = np.random.randint(80, 220, (200, 200, 3), dtype=np.uint8)
        frame2 = np.random.randint(80, 220, (200, 200, 3), dtype=np.uint8)

        rep1 = gate.assess(frame1)
        assert rep1.ok
        rep2 = gate.assess(frame2)
        assert rep2.ok


class TestPolygonBoxOverlap:
    def test_invalid_polygon(self):
        bay_cov, box_cov = polygon_box_overlap(np.array([[0, 0], [10, 10]]), [0, 0, 10, 10])
        assert bay_cov == 0.0
        assert box_cov == 0.0

    def test_exact_overlap(self):
        # 100x100 bay and 100x100 box
        polygon = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)
        box = [0, 0, 100, 100]
        bay_cov, box_cov = polygon_box_overlap(polygon, box)
        assert pytest.approx(bay_cov, rel=1e-2) == 1.0
        assert pytest.approx(box_cov, rel=1e-2) == 1.0

    def test_no_overlap(self):
        polygon = np.array([[0, 0], [50, 0], [50, 50], [0, 50]], dtype=np.int32)
        box = [100, 100, 150, 150]
        bay_cov, box_cov = polygon_box_overlap(polygon, box)
        assert bay_cov == 0.0
        assert box_cov == 0.0

    def test_partial_overlap(self):
        polygon = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)
        # 50% overlap of bay
        box = [50, 0, 150, 100]
        bay_cov, box_cov = polygon_box_overlap(polygon, box)
        assert pytest.approx(bay_cov, rel=1e-2) == 0.5
        assert pytest.approx(box_cov, rel=1e-2) == 0.5


class TestBayStateMachine:
    @pytest.fixture
    def single_bay(self):
        poly = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)
        return [("bay_1", "Bay 01", poly)]

    @pytest.fixture
    def good_quality(self):
        return QualityReport(ok=True, luminance=120.0, sharpness=80.0, frozen=False)

    @pytest.fixture
    def bad_quality(self):
        return QualityReport(ok=False, luminance=5.0, sharpness=10.0, frozen=False, reason="Too dark")

    def test_initial_state_unknown(self, single_bay):
        sm = BayStateMachine(single_bay)
        assert sm.states["bay_1"] == STATE_UNKNOWN
        assert sm.confidences["bay_1"] is None

    def test_occupancy_hysteresis(self, single_bay, good_quality):
        tuning = BayTuning(enter_occupied_dwell_s=1.0, enter_free_dwell_s=2.0)
        sm = BayStateMachine(single_bay, tuning=tuning)
        car_box = [{"box": [10, 10, 90, 90], "confidence": 0.9}]

        # t=0.0: first sample
        transitions = sm.update(0.0, car_box, good_quality)
        assert sm.states["bay_1"] == STATE_UNKNOWN
        assert len(transitions) == 0

        # t=0.5: still within dwell window (0.5s < 1.0s)
        transitions = sm.update(0.5, car_box, good_quality)
        assert sm.states["bay_1"] == STATE_UNKNOWN
        assert len(transitions) == 0

        # t=1.1: dwell requirement met (1.1s >= 1.0s) -> occupied
        transitions = sm.update(1.1, car_box, good_quality)
        assert sm.states["bay_1"] == STATE_OCCUPIED
        assert len(transitions) == 1
        assert transitions[0].from_state == STATE_UNKNOWN
        assert transitions[0].to_state == STATE_OCCUPIED
        assert transitions[0].confidence_band in {"high", "medium"}

        # Empty bay at t=2.0 (car leaves) - 0.9s empty is < 2.0s dwell -> holds occupied
        transitions = sm.update(2.0, [], good_quality)
        assert sm.states["bay_1"] == STATE_OCCUPIED
        assert len(transitions) == 0

        # Empty bay at t=3.5 (total clear 2.4s >= 2.0s) -> transitions to free
        transitions = sm.update(3.5, [], good_quality)
        assert sm.states["bay_1"] == STATE_FREE
        assert len(transitions) == 1
        assert transitions[0].from_state == STATE_OCCUPIED
        assert transitions[0].to_state == STATE_FREE

    def test_quality_degradation_forces_unknown(self, single_bay, good_quality, bad_quality):
        tuning = BayTuning(enter_occupied_dwell_s=1.0)
        sm = BayStateMachine(single_bay, tuning=tuning)
        car_box = [{"box": [0, 0, 100, 100], "confidence": 0.95}]

        sm.update(0.0, car_box, good_quality)
        sm.update(1.5, car_box, good_quality)
        assert sm.states["bay_1"] == STATE_OCCUPIED

        # Quality drops
        transitions = sm.update(2.0, car_box, bad_quality)
        assert sm.states["bay_1"] == STATE_UNKNOWN
        assert len(transitions) == 1
        assert transitions[0].to_state == STATE_UNKNOWN

    def test_mark_stale_and_out_of_service(self, single_bay, good_quality):
        tuning = BayTuning(enter_occupied_dwell_s=0.5)
        sm = BayStateMachine(single_bay, tuning=tuning)
        car_box = [{"box": [0, 0, 100, 100], "confidence": 0.9}]

        sm.update(0.0, car_box, good_quality)
        sm.update(1.0, car_box, good_quality)
        assert sm.states["bay_1"] == STATE_OCCUPIED

        # Mark stale
        stale_transitions = sm.mark_stale(timestamp_s=2.0)
        assert sm.states["bay_1"] == STATE_STALE
        assert len(stale_transitions) == 1
        assert stale_transitions[0].to_state == STATE_STALE

        # Mark out of service
        sm.mark_out_of_service("bay_1")
        assert sm.states["bay_1"] == STATE_OUT_OF_SERVICE

        # Further updates ignore out_of_service bays
        trans = sm.update(3.0, car_box, good_quality)
        assert sm.states["bay_1"] == STATE_OUT_OF_SERVICE
        assert len(trans) == 0
