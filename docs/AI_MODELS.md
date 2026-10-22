# AI model and validation guide

## Implemented baseline

- Default: `yolo26s.pt` from Ultralytics, loaded lazily when analysis starts.
- Vehicle classes in the COCO label map: 2 car, 3 motorcycle, 5 bus, 7 truck.
- Tracking: ByteTrack via `model.track(..., persist=True, tracker="bytetrack.yaml")`.
- Sampling: `PARKWISE_FRAME_STRIDE` defaults to 3; detection image size defaults to 1280; confidence defaults to 0.25.
- Multi-scale pass: dense aerial/top-down footage is scale-sensitive. If the configured scale finds fewer than 5 vehicles on a frame, the frame is re-inferred at 2560 px and then native resolution (`PARKWISE_MULTISCALE=true`, default) and results are merged with class-wise NMS. If even native-resolution inference finds no vehicle classes on a frame — extreme zoom-out where a vehicle spans only a few pixels — the pipeline records 0 for that frame instead of estimating a count.
- The model is not fine-tuned for aerial parking images by this repository. It is an off-the-shelf baseline and may miss tiny/distant vehicles in top-down footage.

## Comparisons worth conducting

1. YOLO26 nano/small vs YOLO11 nano/small on identical held-out views.
2. RT-DETR on the same set if GPU/latency permits.
3. Domain-tuned vehicle models trained on appropriately licensed aerial/parking annotations.
4. Per-space segmentation/classification for fixed cameras where vehicles are small or overlapping.

Do not assume a two-model ensemble is inherently better. Only retain model fusion if offline evaluation and live latency tests show a measurable benefit for the target site.

## A credible evaluation plan

1. Sample frames across daylight, dusk/night, shadows, rain, glare, crowded periods and partial occlusion.
2. Label vehicles and every configured parking bay. Keep train/validation/test splits separated by recording or camera—not random adjacent frames—to avoid leakage.
3. Report detection precision, recall and mAP; tracking IDF1/HOTA or ID switches; and per-space occupancy precision/recall/F1, confusion matrix and unknown/stale rate.
4. Report p50/p95 inference latency, processed FPS, RAM/VRAM, output drop rate and thermal behaviour for the actual edge device.
5. Define operational acceptance thresholds with the facility. Evaluate false-free errors separately; they are often more costly than false-occupied errors.
6. Run in shadow mode with human ground truth before using occupancy to guide drivers or reservations.

## Environment overrides

`PARKWISE_MODEL=yolo11n.pt` or a supported `rtdetr-l.pt` may be used for controlled comparison. Validate model support in the installed Ultralytics version and ensure the license is appropriate. `PARKWISE_DEVICE=cpu` forces CPU inference; a supported CUDA index such as `0` may select a GPU. `auto` lets the runtime choose.

## License notes

Ultralytics publishes its code/models under AGPL-3.0 and offers Enterprise licensing. Review the current license terms for the exact weights and how the software is distributed/used before incorporating it into a proprietary commercial product. Video datasets and pretrained weights have separate terms from this source repository's MIT license.
