"""Live-stream correctness: tracker isolation, reconnect policy, bay hysteresis.

These tests use fake models/captures — they verify the isolation and lifecycle
wiring, not detection accuracy.
"""

import time
from types import SimpleNamespace

from app.config import settings as env_settings
from app.models import Stream
from app.services import live_stream
from app.services.live_stream import BayTracker, StreamSession, manager


def _stream(stream_id: str, kind: str = "url", url: str = "rtsp://192.168.1.9/stream") -> Stream:
    return Stream(id=stream_id, name=stream_id, kind=kind, url=url, enabled=True)


class _FakeModel:
    """Stands in for an ultralytics model; records which session drove it."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.calls = 0

    def track(self, frame, **kwargs):
        self.calls += 1
        return []  # empty Results => no detections; exercises the full _detect path

    def predict(self, frame, **kwargs):
        self.calls += 1
        return []


class TestTrackerIsolation:
    def test_two_sessions_get_distinct_models(self, monkeypatch):
        """Each StreamSession must resolve its own cached model instance.

        Uses the real get_stream_model cache with a stubbed loader so the
        per-stream keying (and cross-stream isolation) is what is exercised.
        """
        from app.services import model_store

        monkeypatch.setattr(model_store, "_load_model", lambda name, device: _FakeModel(f"{name}|{device}"))
        model_store._STREAM_MODEL_CACHE.clear()
        try:
            session_a = StreamSession(_stream("stream-a"), "rtsp://192.168.1.9/a", [], {"model": "m.pt", "device": "cpu"})
            session_b = StreamSession(_stream("stream-b"), "rtsp://192.168.1.9/b", [], {"model": "m.pt", "device": "cpu"})

            import numpy as np

            frame = np.zeros((64, 64, 3), dtype=np.uint8)
            assert session_a._detect(frame, 320) == []
            assert session_b._detect(frame, 320) == []
            assert session_a._detect(frame, 320) == []

            model_a = model_store.get_stream_model("m.pt", "cpu", "stream-a")
            model_b = model_store.get_stream_model("m.pt", "cpu", "stream-b")
            assert model_a is not model_b
            # Repeated calls for the same stream reuse the same instance (tracker state persists).
            assert model_store.get_stream_model("m.pt", "cpu", "stream-a") is model_a
            assert model_a.calls == 2
            assert model_b.calls == 1
        finally:
            model_store._STREAM_MODEL_CACHE.clear()

    def test_drop_stream_models_releases_instances(self, monkeypatch):
        from app.services import model_store

        monkeypatch.setattr(model_store, "_load_model", lambda name, device: _FakeModel("x"))
        model_store._STREAM_MODEL_CACHE.clear()
        model_store.get_stream_model("m.pt", "cpu", "to-drop")
        assert any("to-drop" in key for key in model_store._STREAM_MODEL_CACHE)
        model_store.drop_stream_models("to-drop")
        assert not any("to-drop" in key for key in model_store._STREAM_MODEL_CACHE)

    def test_bay_tracker_state_is_per_session(self):
        """Bay hysteresis state must not be shared between sessions."""
        polygon = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        tracker_a = BayTracker([{"name": "A1", "polygon": polygon}])
        tracker_b = BayTracker([{"name": "B1", "polygon": polygon}])

        for _ in range(4):
            tracker_a.update([(0.5, 0.5)])  # occupied votes only in A
        assert tracker_a.summary()[0]["state"] == "occupied"
        assert tracker_b.summary()[0]["state"] == "unknown"


class TestBayTrackerHysteresis:
    def test_requires_three_observing_frames(self):
        tracker = BayTracker([{"name": "B", "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]}])
        tracker.update([(0.5, 0.5)])
        tracker.update([(0.5, 0.5)])
        assert tracker.summary()[0]["state"] == "unknown"  # < 3 observations
        tracker.update([(0.5, 0.5)])
        assert tracker.summary()[0]["state"] == "occupied"

    def test_no_polygon_bays_stay_unknown(self):
        tracker = BayTracker([{"name": "Empty", "polygon": []}])
        tracker.update([(0.5, 0.5)] * 5)
        assert tracker.summary()[0]["state"] == "unknown"

    def test_free_requires_dominant_free_votes(self):
        tracker = BayTracker([{"name": "B", "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]}])
        # Three free observations after starting unknown
        for _ in range(3):
            tracker.update([])
        assert tracker.summary()[0]["state"] == "free"


class TestReconnectPolicy:
    def test_backoff_is_exponential_and_bounded(self):
        delays = [StreamSession._backoff_delay(n) for n in range(1, 8)]
        # Jittered, but the ceiling must hold and the general trend must grow.
        assert all(d <= 30.0 for d in delays)
        assert StreamSession._backoff_delay(1) < 8.0
        assert StreamSession._backoff_delay(6) >= 16.0 * 0.5

    def test_camera_open_failure_reaches_terminal_error(self, monkeypatch):
        """A camera that never opens must end in error after bounded attempts."""
        monkeypatch.setattr(env_settings, "stream_max_reconnect_attempts", 2, raising=False)

        class _NeverOpens:
            def __init__(self, source):
                pass

            def isOpened(self):
                return False

            def release(self):
                pass

        import sys

        fake_cv2 = SimpleNamespace(VideoCapture=_NeverOpens)
        monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
        # Speed up: no real sleeping in backoff waits (stop_event.wait is real, so
        # shrink the delay by forcing attempts to exhaust quickly).
        session = StreamSession(_stream("cam-x"), "rtsp://192.168.1.9/x", [], {"model": "m.pt"})
        session._backoff_delay = lambda attempt: 0.01  # type: ignore[method-assign]
        session.start()
        deadline = time.monotonic() + 5.0
        while session.alive and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not session.alive
        assert session.status == "error"
        assert session.last_error and "Could not open" in session.last_error

    def test_replay_source_fails_without_reconnect(self, monkeypatch):
        """A missing replay file must fail immediately (no pointless retries)."""
        monkeypatch.setattr(env_settings, "stream_max_reconnect_attempts", 5, raising=False)

        class _NeverOpens:
            def __init__(self, source):
                pass

            def isOpened(self):
                return False

            def release(self):
                pass

        import sys

        fake_cv2 = SimpleNamespace(VideoCapture=_NeverOpens)
        monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
        session = StreamSession(
            _stream("replay-x", kind="video", url=None), "/tmp/missing-file.mp4", [], {"model": "m.pt"}
        )
        session.start()
        deadline = time.monotonic() + 3.0
        while session.alive and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not session.alive
        assert session.status == "error"
        assert session.reconnect_attempts == 1  # no retries for replay files


class TestSourceMode:
    def test_video_kind_is_labelled_replay(self):
        session = StreamSession(_stream("r1", kind="video", url=None), "/tmp/x.mp4", [], {})
        assert session.source_mode == "replay"

    def test_url_kind_is_labelled_live_camera(self):
        session = StreamSession(_stream("c1"), "rtsp://192.168.1.9/s", [], {})
        assert session.source_mode == "live_camera"


class TestStaleness:
    def test_no_frame_yet_counts_as_stale_when_live(self):
        session = StreamSession(_stream("s1"), "rtsp://192.168.1.9/s", [], {})
        session.status = "live"
        assert session.is_stale() is True
        assert session.frame_age_seconds() is None

    def test_fresh_frame_is_not_stale(self):
        session = StreamSession(_stream("s2"), "rtsp://192.168.1.9/s", [], {})
        session.last_frame_monotonic = time.monotonic()
        assert session.is_stale() is False
        assert session.frame_age_seconds() is not None


def test_manager_stop_drops_stream_models(monkeypatch):
    dropped: list[str] = []
    monkeypatch.setattr(live_stream, "drop_stream_models", lambda sid: dropped.append(sid))
    session = StreamSession(_stream("gone"), "rtsp://192.168.1.9/g", [], {})
    monkeypatch.setattr(manager, "_sessions", {"gone": session})
    monkeypatch.setattr(session, "stop", lambda timeout=5.0: None)
    assert manager.stop("gone") is True
    assert dropped == ["gone"]
