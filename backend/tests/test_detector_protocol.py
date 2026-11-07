import numpy as np
from app.inference.detector import Detection, MockDetector, UltralyticsDetector, get_detector


def test_detection_dataclass():
    d = Detection(xyxy=(10.0, 20.0, 50.0, 80.0), confidence=0.88, cls="car", class_id=2, track_id=42)
    assert d.cls == "car"
    assert d.track_id == 42
    data = d.to_dict()
    assert data["box"] == [10, 20, 50, 80]
    assert data["confidence"] == 0.88
    assert data["track_id"] == 42


def test_mock_detector():
    detector = get_detector("mock-test")
    assert isinstance(detector, MockDetector)
    assert detector.backend == "mock"
    assert detector.license == "MIT"

    frames = [np.zeros((100, 100, 3), dtype=np.uint8)]
    results = detector.detect(frames, confidence=0.5)
    assert len(results) == 1
    assert len(results[0]) >= 1
    assert results[0][0].cls == "car"

    tracked = detector.track("stream-1", frames[0], confidence=0.5)
    assert len(tracked) >= 1


def test_ultralytics_detector_metadata():
    detector = UltralyticsDetector("yolo26n.pt")
    assert detector.name == "yolo26n.pt"
    assert detector.backend == "ultralytics"
    assert "AGPL" in detector.license
