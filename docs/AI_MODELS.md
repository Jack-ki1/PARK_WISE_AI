# AI Models, Architecture & Licensing Guide

## Pluggable Detector Architecture

ParkWise provides a formal `Detector` protocol (`app.inference.detector`) that decouples application logic from any single computer vision vendor.

```python
class Detector(Protocol):
    name: str
    backend: str
    license: str
    def warmup(self) -> None: ...
    def detect(self, frames: Sequence[np.ndarray], confidence: float, imgsz: int) -> list[list[Detection]]: ...
    def track(self, stream_key: str, frame: np.ndarray, confidence: float, imgsz: int) -> list[Detection]: ...
```

### Supported Backends

| Backend | Typical Models | License | Best For |
| :--- | :--- | :--- | :--- |
| **Ultralytics** | `yolo26s.pt`, `yolo26n.pt`, `yolo11n.pt` | AGPL-3.0 / Enterprise | Turnkey out-of-the-box accuracy with ByteTrack |
| **ONNX Runtime** | Exported `.onnx` models | Apache-2.0 / Permissive | Air-gapped CPU/serverless deployments |
| **Mock** | `mock-test` | MIT | Zero-dependency unit testing & CI gates |

The active model name, backend, and license are surfaced programmatically in `/api/config/public` and `/api/system/info`.

---

## Detection & Tracking Pipeline

- **Vehicle Classes**: Filtered strictly for COCO vehicle classes: `2` (car), `3` (motorcycle), `5` (bus), and `7` (truck).
- **Persistent Tracking**: ByteTrack tracker assigns consistent vehicle identities across consecutive video frames.
- **Adaptive Multi-Scale Inference**: Top-down or high-angle cameras often contain distant vehicles. If a frame has fewer than 5 vehicles detected, ParkWise automatically re-evaluates the frame at 2560px and native resolution (`PARKWISE_MULTISCALE=true`) and merges bounding boxes with class-wise Non-Maximum Suppression (NMS).

---

## Bay State Machine & Quality Gating

Per-bay occupancy is computed by `BayStateMachine` (`app.services.bay_state`), which combines:

1. **Polygon-Box Overlap**: Calculates contour intersection area between calibrated bay polygons and detected bounding boxes (`bay_cov` >= 0.35 or `box_cov` >= 0.25).
2. **Time-Based Dwell Hysteresis**:
   - Occupied transition: Requires minimum sustained evidence (default `1.0s`).
   - Free transition: Requires sustained clearance (default `1.5s - 2.0s`).
3. **Quality Gate**:
   - Assesses luminance, sharpness (Laplacian variance), and frozen frame hash.
   - When cameras experience glare, blackout, or freezing, bays transition to `unknown` rather than reporting false free capacity.

---

## Accuracy Evaluation Benchmark

To run empirical accuracy validation on holdout datasets:

```bash
python scripts/evaluate_occupancy.py --min-precision 0.90 --min-recall 0.90
```

### Published Holdout Results (N = 1,200)

- **Overall F1-Score**: 96.2%
- **Overall Precision**: 93.1%
- **Overall Recall**: 99.5%
- **False-Free Rate**: 0.5% (Occupied bay mistakenly marked free)
- **False-Occupied Rate**: 7.6%
- **Unknown Rate**: 4.7% (Degraded conditions safely flagged as unknown)

---

## Enterprise Licensing Advice

1. **MIT Core**: The ParkWise server, web application, state machine, and database schema are licensed under the MIT License.
2. **Ultralytics Weights/Library**: If you deploy with Ultralytics (`ultralytics==8.4.x`), comply with AGPL-3.0 copyleft terms or acquire an Ultralytics Enterprise license.
3. **Permissive Deployment Path**: For proprietary enterprise SaaS distribution without AGPL obligations, export models to ONNX (`scripts/export_model_onnx.py`) and utilize the permissive ONNX/OpenCV runtime path.
