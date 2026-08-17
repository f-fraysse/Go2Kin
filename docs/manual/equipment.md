# Equipment

What you need before installing Go2Kin. This page has some comments, tips, things learned along the way, and notes on our own experience, so may be worth a quick read even if you know/have the equipment. 

**Note**: long USB cables (20-30m) are not able to power the cameras on their own, the batteries are still needed, and they will slowly discharge while the cameras are on. Some choices and comments below reflect this. It's possible a powered USB hub solves this issue (we haven't tested this). In our lab we find USB + battery is simple to use so we stuck with that.

## Cameras

- **Cameras and batteries:** up to 4 GoPro cameras + one battery per camera. We use Hero 12 Black; any model supporting the Open GoPro HTTP API (Hero 9 or later) should work.

- Battery charger: we use 2 sets of 4 batteries, and 2 GoPro battery chargers. This way we can have 4 cameras running + 4 batteries charging, and swap batteries every few hours. You can purchase [a charger with 2 batteries bundle from GoPro](https://gopro.com/en/au/shop/mounts-accessories/hero10-black-dual-battery-charger-enduro-batteries/ADDBD-211-master.html) for approx. 90 AUD.
  
- **SD cards**: each camera needs a MicroSD card. Pay attention to the SD card rating [(see here for the rundown on SD card ratings)](https://www.kingston.com/en/blog/personal-storage/memory-card-speed-classes), lower rated ones won't be able to keep pace with recording at high resolutions / high FPS. We are using SanDisk UHS Mark I and record at 4K 50FPS / 1080p 100FPS so this rating should be enough. Capacity doesn't matter much since each recording gets deleted off the SD card straight after downloading. 

## USB cables

- One **data-capable** USB cable per camera, long enough to reach from each tripod to the PC.

- You want cables with a good rating since we are using long cables. In our lab setup, we use 2x 20m and 2x 30m cables. We are using [these from a local Australian supplier](https://au.element14.com/bulgin-limited/aous1-030/usb-cable-3-2-typ-a-plug-rcpt/dp/4574389?MER=BR-MER-PDP-RECO-STM72194), expensive but we've had no issues controlling cameras and downloading videos over the 30m cable, straight from a PC USB port with no hub.

- Note that, even with the cables plugged in, we still need to use the batteries in the cameras - the long cables + PC power are not able to supply enough to the camera. The batteries will slowly drain even with the USB connected. We find that the batteries deplete after ~5 hours, which is very workable but still need to keep an eye on for very long sessions.

> 🚧 **TODO:** recommended cable length, models and sellers — pull from Ryan's email.

> 🚧 **TODO:** confirm whether a (powered) USB hub works, or whether four separate ports on the PC are required.## Tripods / mounting

- One tripod (or wall mount) per camera. 

> 🚧 **TODO:** recommended tripod models, typical heights, and camera placement guidance for a 4-camera volume (photo/diagram of a working lab layout).



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
