#Example - connect to a gopro camera, take photo and save it using a given filename


#************************ INPUT PARAMETERS **************************************
#Camera serial number - you can find it either under settings in the camera itself,
#or by selecting the camera and clicking "Properties" in the file explorer
SNcam1 = 'C3xxxxxxxxxxxx'

#Output file name - it can, but does not have to, inclue ".jpg" extension
fname = 'testX'

#make sure that the camera is connected and switched on!
#********************************************************************************


from goproUSB import GPcam


cam1 = GPcam(SNcam1)
cam1.USBenable()
cam1.modePhoto()
cam1.shutterStart()

#wait for the camera to finish processing:
while cam1.camBusy():
    continue
while cam1.encodingActive():
    continue


cam1.mediaDownloadLast(fname)

cam1.USBdisable()
