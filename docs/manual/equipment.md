# Equipment

What you need before installing Go2Kin.

## Cameras

- Up to **4 GoPro cameras**. Developed and tested with the **Hero 12 Black**; any model supporting the Open GoPro HTTP API (Hero 9 or later) should work.
- One **battery** and one **SD card** per camera.

> 🚧 **TODO:** recommended SD card spec (capacity, speed/endurance rating) and battery notes — e.g. does the camera charge over USB while connected?

## Tripods and mounting

- One tripod (or wall/truss mount) per camera.
- Cameras must not move between extrinsic calibration and recording — mounts should be stable and hard to knock.

> 🚧 **TODO:** recommended tripod models, typical heights, and camera placement guidance for a 4-camera volume (photo/diagram of a working lab layout).

## USB cables

- One **data-capable** USB cable per camera, long enough to reach from each tripod to the PC. Cheap charge-only cables will not work.

> 🚧 **TODO:** recommended cable length, models and sellers — pull from Ryan's email.

> 🚧 **TODO:** confirm whether a (powered) USB hub works, or whether four separate ports on the PC are required.

## PC

- **Windows 11** (tested on Windows 11 Enterprise LTSC 2024).
- **NVIDIA GPU strongly recommended.** Pose estimation runs via CUDA; it will run on CPU, but far too slowly to be realistically usable.
- Plenty of **disk space** on a fast drive — multi-camera video adds up quickly. See [Create the data folder](first-time-setup/02-data-folder.md).

> 🚧 **TODO:** minimum/recommended specs — GPU model and VRAM, RAM, free disk per hour of collection.

## Calibration board

A printed **charuco board**, generated from the Calibration tab (default size A1) and mounted on a rigid, flat surface.

- **Measure the actual printed square size** — printers don't always scale exactly — and use the measured value in the board config.
- Highly recommended: also print the "inverted" image and make a **double-sided board** (see the Caliscope documentation).

> 🚧 **TODO:** how to get a good board built — print shop vs in-house, mounting material (foam board / dibond / acrylic), matte lamination, approximate cost, and a supplier that has worked well.

## Other

- Nothing special is needed for synchronisation — **two loud hand claps** at the start of each recording do the job.
- A tape measure, for positioning the board at the lab origin.

> 🚧 **TODO:** lab environment tips if relevant (lighting, background, flooring).
