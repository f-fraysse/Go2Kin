#Example:
#Connect to two gopro cameras with given serial numbers and record - simultaneously - videos
#For the script to work only the correct serial numbers are required
#The video files are saved using given core file name, to which camera and video indices are automatically added


#************************ INPUT PARAMETERS **************************************
#Camera serial number - you can find it either under settings in the camera itself,
#or by selecting the camera and clicking "Properties" in the file explorer
SNcam1 = 'C3501326042700'
SNcam2 = 'C3501326062418'

#Core file name using which all the subsequent downloaded images will be saved
#camera number and image number will be added automatically, do not include them here
fname = 'test_multicam'

#Video duration (seconds):
vidDuration = 3

#make sure that the cameras are connected and switched on!
#********************************************************************************

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from goproUSB import GPcam
import glob
import time
import concurrent.futures





def shootVideo(cam):
    cam.shutterStart()
    time.sleep(vidDuration)
    cam.shutterStop()


cam1 = GPcam(SNcam1)
cam2 = GPcam(SNcam2)

cam1.USBenable()
cam1.modeVideo()
cam2.USBenable()
cam2.modeVideo()

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    results = pool.map(shootVideo, [cam1,cam2])

#wait for the camera to finish processing:
while cam1.camBusy() or cam2.camBusy():
    continue
while cam1.encodingActive() or cam2.encodingActive():
    continue


ml1 = cam1.getMediaList()
ml2 = cam2.getMediaList()

fileidx = len(glob.glob(f'{fname}1_*.mp4')) + 1



cam1.mediaDownloadLast(f'{fname}1_{fileidx:03}')
cam2.mediaDownloadLast(f'{fname}2_{fileidx:03}')

cam1.USBdisable()
cam2.USBdisable()
