#Example:
#Connect to two gopro cameras with given serial numbers and take - simultaneously - pictures
#For the script to work only the correct serial numbers are required
#The images are saved using given core file name, to which camera and image indices are automatically added


#************************ INPUT PARAMETERS **************************************
#Camera serial number - you can find it either under settings in the camera itself,
#or by selecting the camera and clicking "Properties" in the file explorer
SNcam1 = 'C3xxxxxxxxxxxx'
SNcam2 = 'C3yyyyyyyyyyyy'

#Core file name using which all the subsequent downloaded images will be saved
#camera number and image number will be added automatically, do not include them here
fname = 'cam'

#make sure that the cameras are connected and switched on!
#********************************************************************************


from goproUSB import GPcam
import glob
import concurrent.futures



def takePhoto(cam):
    cam.shutterStart()
    
    
cam1 = GPcam(SNcam1)
cam2 = GPcam(SNcam2)

cam1.USBenable()
cam1.modePhoto()
cam2.USBenable()
cam2.modePhoto()


with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    results = pool.map(takePhoto, [cam1,cam2])

#wait for the camera to finish processing:
while cam1.camBusy() or cam2.camBusy():
    continue
while cam1.encodingActive() or cam2.encodingActive():
    continue

#get list of files from both cameras
ml1 = cam1.getMediaList()
ml2 = cam2.getMediaList()

#determine
fileidx = len(glob.glob(f'{fname}1_*.jpg')) + 1



cam1.mediaDownloadLast(f'{fname}1_{fileidx:03}')
cam2.mediaDownloadLast(f'{fname}2_{fileidx:03}')

cam1.USBdisable()
cam2.USBdisable()
