4x .mp4 videos, approx. 6 sec long, from GoPro, 4K 50FPS, bitrate 110mbps (each file ~75MB)

Running Pose2Sim with config: (only relevant parameters)

mode = 'performance' (yolox-X and rtmpose-X)

det_frequency = 4

device = 'CUDA'

backend = 'onnxruntime'

...

display_detection = false

overwrite_pose = true

save_video = 'to_video'

Single threaded:

[13:42:23] --- Starting Pose Estimation ---

[13:44:31] --- Starting Triangulation ---

Total 128sec

with 4 threads:

[13:37:49] --- Starting Pose Estimation ---

[13:38:42] --- Starting Triangulation --

Total 53 sec

---

2nd run:

Single threaded:

[13:48:47] --- Starting Pose Estimation ---

[13:50:41] --- Starting Triangulation ---

total pose time = 114sec

with 4 threads:

[13:46:24] --- Starting Pose Estimation ---

[13:47:16] --- Starting Triangulation ---

Total 52 sec

With config change:

save_video = 'none'

single threaded

[14:00:44] --- Starting Pose Estimation ---

[14:01:40] --- Starting Triangulation ---

Total 56sec

With 4 threads:

[14:03:18] --- Starting Pose Estimation ---

[14:03:50] --- Starting Triangulation ---

Total 32sec

Second run

single threaded

[14:05:38] --- Starting Pose Estimation ---

[14:06:37] --- Starting Triangulation ---

Total 59sec

With 4 threads:

[14:08:00] --- Starting Pose Estimation ---

[14:08:33] --- Starting Triangulation ---

Total 32sec
