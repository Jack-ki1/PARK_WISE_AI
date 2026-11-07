"""Export YOLO .pt weights to ONNX for the serverless (onnxruntime) inference path.

Run locally with the dev venv (ultralytics installed), e.g.:
    .venv/bin/python scripts/export_model_onnx.py yolo26n.pt
Then upload the resulting models/*.onnx to blob storage under models/{name}.onnx.
"""

import sys
from pathlib import Path


def main() -> None:
    from ultralytics import YOLO

    names = sys.argv[1:] or ["yolo26n.pt"]
    for name in names:
        weights = Path(name)
        if not weights.exists():
            weights = Path(__file__).resolve().parents[1] / name
        model = YOLO(str(weights))
        path = model.export(
            format="onnx",
            imgsz=640,
            dynamic=True,
            simplify=True,
            opset=12,
        )
        out = Path(path)
        print(f"{weights.name} -> {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
