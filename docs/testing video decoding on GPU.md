# Testing Video Decoding on GPU (NVDEC)

## Motivation

The pose estimation pipeline (`poseEstimation.py`) uses `cv2.VideoCapture` for video decoding, which runs on CPU. We investigated whether replacing it with NVIDIA's hardware video decoder (NVDEC) via [PyNvVideoCodec](https://pypi.org/project/PyNvVideoCodec/) would meaningfully speed up the pipeline.

## Approach

Created a benchmark script (`tools/bench_decode.py`) that compares:
1. **cv2.VideoCapture** (CPU software decode) -> BGR numpy frame
2. **PyNvVideoCodec SimpleDecoder** (NVDEC hardware decode) -> RGB host memory -> BGR numpy frame

Both paths feed the same rtmlib `PoseTracker` (YOLOX + RTMPose, ONNX Runtime with CUDA EP) to measure end-to-end impact.

### PyNvVideoCodec setup notes

- `SimpleDecoder` with `use_device_memory=False` and `output_color_type=RGB` decodes to host memory in RGB format.
- Frame data is extracted via `frame.GetPtrToPlane(0)` + `np.ctypeslib.as_array` + reshape (not `np.array(frame)` which doesn't work on `DecodedFrame` objects).

## Benchmark results

**Hardware**: Windows 10, NVIDIA GPU with CUDA 12.4, 4K GoPro Hero 12 footage (3840x2160 @ 50fps, h.264)

**Common config**: HALPE_26 model, ONNX Runtime + CUDA EP, 200 frames after 10-frame warmup

### Performance mode (yolox-x + rtmpose-x)

#### Decode only (no inference)

| Backend  | Avg (ms) | Median (ms) | Min (ms) | Max (ms) | Total (s) |
|----------|----------|-------------|----------|----------|-----------|
| cv2      | 14.84    | 14.31       | 10.83    | 25.72    | 2.967     |
| PyNvVC   | 7.52     | 7.17        | 6.48     | 14.81    | 1.505     |

**Decode speedup: 1.97x**

#### Decode + inference (full pipeline)

| Backend  | Phase  | Avg (ms) | Median (ms) | Min (ms) | Max (ms) |
|----------|--------|----------|-------------|----------|----------|
| cv2      | decode | 13.77    | 13.72       | 11.14    | 23.17    |
| cv2      | infer  | 50.76    | 48.37       | 45.89    | 80.01    |
| cv2      | TOTAL  | 64.53    | 62.43       | 57.76    | 102.54   |
| PyNvVC   | decode | 7.12     | 7.04        | 6.24     | 9.25     |
| PyNvVC   | infer  | 51.36    | 45.31       | 44.05    | 90.94    |
| PyNvVC   | TOTAL  | 58.48    | 52.97       | 50.46    | 97.93    |

**End-to-end speedup: 1.10x** (6.0 ms/frame saved, 1.2s over 200 frames)

### Balanced mode (yolox-m + rtmpose-m)

#### Decode only (no inference)

| Backend  | Avg (ms) | Median (ms) | Min (ms) | Max (ms) | Total (s) |
|----------|----------|-------------|----------|----------|-----------|
| cv2      | 15.22    | 14.61       | 10.93    | 29.21    | 3.045     |
| PyNvVC   | 8.14     | 7.61        | 6.59     | 16.14    | 1.628     |

**Decode speedup: 1.87x**

#### Decode + inference (full pipeline)

| Backend  | Phase  | Avg (ms) | Median (ms) | Min (ms) | Max (ms) |
|----------|--------|----------|-------------|----------|----------|
| cv2      | decode | 14.81    | 14.55       | 10.87    | 19.54    |
| cv2      | infer  | 46.37    | 35.35       | 29.64    | 86.29    |
| cv2      | TOTAL  | 61.17    | 50.01       | 42.42    | 102.04   |
| PyNvVC   | decode | 7.50     | 7.27        | 6.33     | 9.17     |
| PyNvVC   | infer  | 41.92    | 31.21       | 28.10    | 82.86    |
| PyNvVC   | TOTAL  | 49.42    | 39.20       | 35.08    | 90.98    |

**End-to-end speedup: 1.24x** (11.8 ms/frame saved, 2.4s over 200 frames)

Not really worth the trouble for pose2sim / pose estimation pipelines. Could be worth it for pure encore / decode (e.g. for a visualisation tool?)

## Inference stage breakdown

Two things from the above results:
- yolox-X is not that much slower than yolox-M which is surprising.
- when decoding on GPU, the video frame goes GPU memory -> CPU memory for pre processing (resize, normalise etc) -> GPU for inference -> CPU for post processing
- these CPU-GPU data transfers and cpu computations could be the bottleneck - which could also explain small difference between X and M models.
- so we broke down inference time some more.
 
To understand where time is actually spent within inference, we created a second benchmark (`tools/bench_inference.py`) that breaks down each model into 5 stages using ONNX Runtime `io_binding`:

1. **preprocess** (CPU) — resize/warpAffine, normalize, transpose, contiguous
2. **h2d** — host-to-device memory transfer
3. **compute** — GPU model execution
4. **d2h** — device-to-host memory transfer
5. **postprocess** (CPU) — NMS, SimCC decode

**Config**: HALPE_26 model, ONNX Runtime + CUDA EP, 100 frames after 10-frame warmup, 1 person in scene

### Performance mode (yolox-x + rtmpose-x)

| Stage       | YOLOX Avg (ms) | YOLOX % | RTMPose Avg (ms) | RTMPose % | Combined Avg (ms) | Combined % |
|-------------|---------------|---------|-------------------|-----------|-------------------|------------|
| preprocess  | 2.61          | 6.7%    | 3.55              | 29.3%     | 6.16              | 12.1%      |
| h2d         | 0.55          | 1.4%    | 0.17              | 1.4%      | 0.71              | 1.4%       |
| **compute** | **35.65**     | **91.7%** | **8.23**        | **67.8%** | **43.88**         | **86.0%**  |
| d2h         | 0.04          | 0.1%    | 0.07              | 0.5%      | 0.11              | 0.2%       |
| postprocess | 0.05          | 0.1%    | 0.12              | 1.0%      | 0.17              | 0.3%       |
| **total**   | **38.89**     | 100%    | **12.14**         | 100%      | **51.03**         | 100%       |

### Balanced mode (yolox-m + rtmpose-m)

| Stage       | YOLOX Avg (ms) | YOLOX % | RTMPose Avg (ms) | RTMPose % | Combined Avg (ms) | Combined % |
|-------------|---------------|---------|-------------------|-----------|-------------------|------------|
| preprocess  | 2.70          | 9.6%    | 1.76              | 24.8%     | 4.47              | 12.6%      |
| h2d         | 0.59          | 2.1%    | 0.10              | 1.4%      | 0.69              | 2.0%       |
| **compute** | **24.87**     | **88.0%** | **5.06**        | **71.3%** | **29.94**         | **84.7%**  |
| d2h         | 0.05          | 0.2%    | 0.06              | 0.9%      | 0.11              | 0.3%       |
| postprocess | 0.04          | 0.1%    | 0.11              | 1.6%      | 0.15              | 0.4%       |
| **total**   | **28.26**     | 100%    | **7.10**          | 100%      | **35.36**         | 100%       |

### Key takeaways

- **GPU compute dominates**: 84-86% of total inference time is pure GPU computation.
- **Memory transfers are negligible**: H2D ~0.7ms, D2H ~0.1ms — together under 2% of total.
- **CPU preprocessing is small**: ~12% of total (resize 4K to 640x640 for YOLOX, warpAffine for RTMPose).
- **YOLOX-X vs YOLOX-M pure compute**: 35.6ms vs 24.9ms (1.43x)

## Conclusion

### GPU video decode (NVDEC)

not worth the trouble for pose2sim pipeline - small overall gains (10-20% on pose estimation).

### Keeping frames on GPU for the full pipeline

Not worth either. Too complex and, as seen above, those steps take little time anyway.

CV-CUDA, the library needed for GPU-accelerated image preprocessing (resize, warpAffine, normalize), only supports Linux/WSL2 — no native Windows builds. It was also not validated whether CV-CUDA and ONNX Runtime could share GPU memory without additional copies.

### Other things to try

- TensorRT backend instead of ONNX Runtime (typically 2-3x for these model architectures) - had explored, rtmdet / rtmpose use custom ops (see mmdeploy docs) and I wasn't able to convert to TRT successfully 
- Batch inference (amortize GPU kernel launch overhead across multiple frames/persons) - use rtmdet / rtmpose with flexible input size to batch frames.
