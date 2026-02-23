# goproUSB
A simple Python module for controlling, recording images and videos, and downloading media from GoPro cameras connected via USB.

It allows to connect to a single or multiple cameras and perform simultaneous recordings of images or videos.

The only thing required to connect to a camera is its serial number. The serial number is a 14-character string, beginning with "C3". It can be obtained either directly from the camera's menu ( [Preferences] > [About] > [Camera Info]), or by right-clicking camera connected via USB in file explorer (Windows) and selecting "Properties". 

Originally developed for HERO 10 cameras. Extended and tested with HERO 12 Black cameras for the Go2Kin project.

## Features
- Camera connection and USB control
- Recording start/stop (photo, video, timelapse)
- Settings configuration (lens, resolution, FPS, and generic setting API)
- Digital zoom control (0-100%)
- Live preview stream start/stop
- Media download and deletion
- Status monitoring (busy, encoding active)
- HTTP request timeouts for robustness

## Example Usage

Take a picture and download it to the current working directory:

```python
from goproUSB import GPcam

serial_number = 'C3xxxxxxxxxxxx'
output_file_name = 'image'

cam1 = GPcam(serial_number)
cam1.USBenable()
cam1.modePhoto()
cam1.shutterStart()

# Wait for the camera to finish processing
while cam1.camBusy():
    continue
while cam1.encodingActive():
    continue

cam1.mediaDownloadLast(output_file_name)
cam1.USBdisable()
```

For examples of other operating options — recording videos, using webcam mode, and acquiring data from multiple cameras simultaneously — please refer to the `examples/` folder.
