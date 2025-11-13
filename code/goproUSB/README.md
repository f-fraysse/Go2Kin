# goproUSB
A simple Python module for controlling, recording images and videos, and downloading media from GoPro cameras connected via USB.

It allows to connect to a single or multiple cameras and perform simultaneous recordings of images or videos.

The only thing required to connect to a camera is its serial number. The serial number is a 14. character string, beginning with "C3". It can be obtained either directly from the camera's menu ( [Preferences] > [About] > [Camera Info]), or by right-clicking camera connected via USB in file explorer (Windows) and selecting "Properties". 

I have only tested it with HERO 10 cameras. Not sure how will it work with other GoPro cameras.

Example usage - take picture and download it to a current working directory:

serial_number = 'C3xxxxxxxxxxxx'<br />
output_file_name = 'image'<br />
from goproUSB import GPcam<br />
cam1 = GPcam(serial_number)<br />
cam1.USBenable()<br />
cam1.modePhoto()<br />
cam1.shutterStart()<br />
#wait for the camera to finish processing:<br />
while cam1.camBusy():<br />
   &emsp; continue<br />
while cam1.encodingActive():<br />
   &emsp; continue<br />
cam1.mediaDownloadLast(output_file_name)<br />
cam1.USBdisable(output_file_name)<br />

For examples of other operating options - recording videos, using webcam mode, and acquiring data from multiple cameras simultaneously - please refer to the "examples" folder.
