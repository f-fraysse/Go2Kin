#goproUSB
#copyright 2022 Lukasz J. Nowak
#
#
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU General Public License
#along with this program.  If not, see <http://www.gnu.org/licenses/>

import requests
import datetime


class GPcam:
    def __init__(self,sn):
        self.base_url = 'http://172.2'+sn[-3]+'.1'+sn[-2:]+'.51'
    #*******************************************
    #Camera status and info
    #*******************************************
    def getState(self):
        url = self.base_url + '/gopro/camera/state'
        response = requests.get(url)
        return response
    def getDateTime(self):
        url = self.base_url + '/gopro/camera/get_date_time'
        response = requests.get(url)
        return response
    def setDateTime(self,y,mo,d,h,mi,s):
        url = self.base_url + f'/gopro/camera/set_date_time?date={y}_{mo}_{d}&time={h}_{mi}_{s}'
        response = requests.get(url)
        return response
    def setDateTimeNow(self):
        url = self.base_url + datetime.datetime.now().strftime('/gopro/camera/set_date_time?date=%Y_%m_%d&time=%H_%M_%S')
        response = requests.get(url)
        return response
    #*******************************************
    #Camera control
    #*******************************************
    def keepAlive(self):
        url = self.base_url + '/gopro/camera/keep_alive'
        response = requests.get(url)
        return response
    def USBenable(self):
        url = self.base_url + '/gopro/camera/control/wired_usb?p=1'
        response = requests.get(url)
        return response
    def USBdisable(self):
        url = self.base_url + '/gopro/camera/control/wired_usb?p=0'
        response = requests.get(url)
        return response
    def setControlIdle(self):
        url = self.base_url + '/gopro/camera/control/set_ui_controller?p=0'
        response = requests.get(url)
        return response
    def setControlExt(self):
        url = self.base_url + '/gopro/camera/control/set_ui_controller?p=2'
        response = requests.get(url)
        return response
    def shutterStart(self):
        url = self.base_url + '/gopro/camera/shutter/start'
        response = requests.get(url)
        return response
    def shutterStop(self):
        url = self.base_url + '/gopro/camera/shutter/stop'
        response = requests.get(url)
        return response
    #*******************************************
    #Modes and presets
    #*******************************************
    def modePhoto(self):
        url = self.base_url + '/gopro/camera/presets/set_group?id=1001'
        response = requests.get(url)
        return response
    def modeVideo(self):
        url = self.base_url + '/gopro/camera/presets/set_group?id=1000'
        response = requests.get(url)
        return response
    def modeTimelapse(self):
        url = self.base_url + '/gopro/camera/presets/set_group?id=1002'
        response = requests.get(url)
        return response
    def getPresetsStatus(self):
        url = self.base_url + '/gopro/camera/presets/get'
        response = requests.get(url)
        return response
    def presetsStandard(self):
        url = self.base_url + '/gopro/camera/presets/load?id=0'
        response = requests.get(url)
        return response
    def presetsActivity(self):
        url = self.base_url + '/gopro/camera/presets/load?id=1'
        response = requests.get(url)
        return response
    def presetsCinematic(self):
        url = self.base_url + '/gopro/camera/presets/load?id=2'
        response = requests.get(url)
        return response
    def presetsUltraSloMo(self):
        url = self.base_url + '/gopro/camera/presets/load?id=4'
        response = requests.get(url)
        return response
    def presetsBasic(self):
        url = self.base_url + '/gopro/camera/presets/load?id=5'
        response = requests.get(url)
        return response
    def presetsPhoto(self):
        url = self.base_url + '/gopro/camera/presets/load?id=65536'
        response = requests.get(url)
        return response
    def presetsLiveBurst(self):
        url = self.base_url + '/gopro/camera/presets/load?id=65537'
        response = requests.get(url)
        return response
    def presetsBurstPhoto(self):
        url = self.base_url + '/gopro/camera/presets/load?id=65538'
        response = requests.get(url)
        return response
    def presetsNightPhoto(self):
        url = self.base_url + '/gopro/camera/presets/load?id=65539'
        response = requests.get(url)
        return response
    def presetsTimeWarp(self):
        url = self.base_url + '/gopro/camera/presets/load?id=131072'
        response = requests.get(url)
        return response
    def presetsTimeLapse(self):
        url = self.base_url + '/gopro/camera/presets/load?id=131073'
        response = requests.get(url)
        return response
    def presetsNightLapse(self):
        url = self.base_url + '/gopro/camera/presets/load?id=131074'
        response = requests.get(url)
        return response
    #*******************************************
    #Webcam and streaming controls
    #Note: Prior to issuing webcam commands, Wired USB Control must be disabled
    #*******************************************
    def streamStart(self):
        url = self.base_url + '/gopro/camera/stream/start'
        response = requests.get(url)
        return response
    def streamStop(self):
        url = self.base_url + '/gopro/camera/stream/stop'
        response = requests.get(url)
        return response
    def webcamStart(self):
        url = self.base_url + '/gopro/webcam/start'
        response = requests.get(url)
        return response
    def webcamStop(self):
        url = self.base_url + '/gopro/webcam/stop'
        response = requests.get(url)
        return response
    def webcamPreview(self):
        url = self.base_url + '/gopro/webcam/preview'
        response = requests.get(url)
        return response
    def webcamGetStatus(self):
        url = self.base_url + '/gopro/webcam/status'
        response = requests.get(url)
        return response
    def webcamExit(self):
        url = self.base_url + '/gopro/webcam/exit'
        response = requests.get(url)
        return response
    def getMediaList(self):
        url = self.base_url + '/gopro/media/list'
        response = requests.get(url)
        return response
    #*******************************************
    #Lenses settings
    #*******************************************
    def setPhotoLensesNarrow(self):
        url = self.base_url + '/gopro/camera/setting?setting=122&option=19'
        response = requests.get(url)
        return response
    def setPhotoLensesMaxSuperview(self):
        url = self.base_url + '/gopro/camera/setting?setting=122&option=100'
        response = requests.get(url)
        return response
    def setPhotoLensesWide(self):
        url = self.base_url + '/gopro/camera/setting?setting=122&option=101'
        response = requests.get(url)
        return response
    def setPhotoLensesLinear(self):
        url = self.base_url + '/gopro/camera/setting?setting=122&option=102'
        response = requests.get(url)
        return response
    #video
    def setVideoLensesWide(self):
        url = self.base_url + '/gopro/camera/setting?setting=122&option=19'
        response = requests.get(url)
        return response
    def setVideoLensesNarrow(self):
        url = self.base_url + '/gopro/camera/setting?setting=121&option=2'
        response = requests.get(url)
        return response
    def setVideoLensesSuperview(self):
        url = self.base_url + '/gopro/camera/setting?setting=121&option=3'
        response = requests.get(url)
        return response
    def setVideoLensesLinear(self):
        url = self.base_url + '/gopro/camera/setting?setting=121&option=4'
        response = requests.get(url)
        return response
    def setVideoLensesMaxSuperview(self):
        url = self.base_url + '/gopro/camera/setting?setting=121&option=7'
        response = requests.get(url)
        return response
    def setVideoLensesLinearHorizon(self):
        url = self.base_url + '/gopro/camera/setting?setting=121&option=8'
        response = requests.get(url)
        return response
    #webcam
    def setWebcamLensesWide(self):
        url = self.base_url + '/gopro/camera/setting?setting=43&option=0'
        response = requests.get(url)
        return response
    def setWebcamLensesNarrow(self):
        url = self.base_url + '/gopro/camera/setting?setting=43&option=2'
        response = requests.get(url)
        return response
    def setWebcamLensesSuperview(self):
        url = self.base_url + '/gopro/camera/setting?setting=43&option=3'
        response = requests.get(url)
        return response
    def setWebcamLensesLinear(self):
        url = self.base_url + '/gopro/camera/setting?setting=43&option=4'
        response = requests.get(url)
        return response
    #timelapse
    def setTimelapseLensesNarrow(self):
        url = self.base_url + '/gopro/camera/setting?setting=123&option=19'
        response = requests.get(url)
        return response
    def setTimelapseLensesMaxSuperview(self):
        url = self.base_url + '/gopro/camera/setting?setting=123&option=100'
        response = requests.get(url)
        return response
    def setTimelapseLensesWide(self):
        url = self.base_url + '/gopro/camera/setting?setting=123&option=101'
        response = requests.get(url)
        return response
    def setTimelapseLensesLinear(self):
        url = self.base_url + '/gopro/camera/setting?setting=123&option=102'
        response = requests.get(url)
        return response
    #Maxlens - firmware >= v01.20.00
    def setMaxLensOff(self):
        url = self.base_url + '/gopro/camera/setting?setting=162&option=0'
        response = requests.get(url)
        return response
    def setMaxLensOn(self):
        url = self.base_url + '/gopro/camera/setting?setting=162&option=0'
        response = requests.get(url)
        return response
    #*******************************************
    #Video resolution settings
    #*******************************************
    def setVideoResolution4k(self):
        url = self.base_url + '/gopro/camera/setting?setting=2&option=1'
        response = requests.get(url)
        return response
    def setVideoResolution2p7k(self):
        url = self.base_url + '/gopro/camera/setting?setting=2&option=4'
        response = requests.get(url)
        return response
    def setVideoResolution2p7k_4to3(self):
        url = self.base_url + '/gopro/camera/setting?setting=2&option=6'
        response = requests.get(url)
        return response
    def setVideoResolution1440(self):
        url = self.base_url + '/gopro/camera/setting?setting=2&option=7'
        response = requests.get(url)
        return response
    def setVideoResolution1080(self):
        url = self.base_url + '/gopro/camera/setting?setting=2&option=9'
        response = requests.get(url)
        return response
    def setVideoResolution4k_4to3(self):
        url = self.base_url + '/gopro/camera/setting?setting=2&option=18'
        response = requests.get(url)
        return response
    def setVideoResolution5k(self):
        url = self.base_url + '/gopro/camera/setting?setting=2&option=24'
        response = requests.get(url)
        return response
    def setVideoResolution5k_4to3(self):
        url = self.base_url + '/gopro/camera/setting?setting=2&option=25'
        response = requests.get(url)
        return response
    def setVideoResolution5p3k(self):
        url = self.base_url + '/gopro/camera/setting?setting=2&option=100'
        response = requests.get(url)
        return response
    #*******************************************
    #Frames per second Settings
    #*******************************************
    def setFPS240(self):
        url = self.base_url + '/gopro/camera/setting?setting=3&option=0'
        response = requests.get(url)
        return response
    def setFPS120(self):
        url = self.base_url + '/gopro/camera/setting?setting=3&option=1'
        response = requests.get(url)
        return response
    def setFPS100(self):
        url = self.base_url + '/gopro/camera/setting?setting=3&option=2'
        response = requests.get(url)
        return response
    def setFPS60(self):
        url = self.base_url + '/gopro/camera/setting?setting=3&option=5'
        response = requests.get(url)
        return response
    def setFPS50(self):
        url = self.base_url + '/gopro/camera/setting?setting=3&option=6'
        response = requests.get(url)
        return response
    def setFPS30(self):
        url = self.base_url + '/gopro/camera/setting?setting=3&option=8'
        response = requests.get(url)
        return response
    def setFPS25(self):
        url = self.base_url + '/gopro/camera/setting?setting=3&option=9'
        response = requests.get(url)
        return response
    def setFPS24(self):
        url = self.base_url + '/gopro/camera/setting?setting=3&option=10'
        response = requests.get(url)
        return response
    def setFPS200(self):
        url = self.base_url + '/gopro/camera/setting?setting=3&option=13'
        response = requests.get(url)
        return response
    #*******************************************
    #Media Format Settings
    #*******************************************
    def setMediaFormatTimelapseVideo(self):
        url = self.base_url + '/gopro/camera/setting?setting=128&option=13'
        response = requests.get(url)
        return response
    def setMediaFormatTimelapsePhoto(self):
        url = self.base_url + '/gopro/camera/setting?setting=128&option=20'
        response = requests.get(url)
        return response
    def setMediaFormatNightlapsePhoto(self):
        url = self.base_url + '/gopro/camera/setting?setting=128&option=21'
        response = requests.get(url)
        return response
    def setMediaFormatNightlapseVideo(self):
        url = self.base_url + '/gopro/camera/setting?setting=128&option=26'
        response = requests.get(url)
        return response
    #*******************************************
    #Auto Power Down Settings
    #*******************************************
    def setAPDnever(self):
        url = self.base_url + '/gopro/camera/setting?setting=59&option=0'
        response = requests.get(url)
        return response
    def setAPD5min(self):
        url = self.base_url + '/gopro/camera/setting?setting=59&option=4'
        response = requests.get(url)
        return response
    def setAPD15min(self):
        url = self.base_url + '/gopro/camera/setting?setting=59&option=6'
        response = requests.get(url)
        return response
    def setAPD30min(self):
        url = self.base_url + '/gopro/camera/setting?setting=59&option=7'
        response = requests.get(url)
        return response
    #*******************************************
    #Camera status - boolean
    #*******************************************
    def camBusy(self):
        if self.getState().json()['status']['8'] == 0:
            return False
        else:
            return True
    def encodingActive(self):
        if self.getState().json()['status']['10'] == 0:
            return False
        else:
            return True
    #*******************************************
    #Media 
    #*******************************************
    #Download the last captured media file from the camera
    #outFileName - name of file to which save the last taken picture (extension added/modified automatically)
    def mediaDownloadLast(self,outFileName):
        ml = self.getMediaList()
        while self.encodingActive():
            continue
        url = self.base_url + f"/videos/DCIM/"+ml.json()['media'][-1]['d']+"/"+ml.json()['media'][-1]['fs'][-1]['n']
        outFileName = outFileName.split('.')[0] + '.' + ml.json()['media'][-1]['fs'][-1]['n'].split('.')[1]
        with requests.get(url, stream=True) as request:
            request.raise_for_status()
            with open(outFileName, "wb") as f:
                for chunk in request.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True
    #
    #Download specified media file, from the specified directory
    #outFileName - name of file to which save the last taken picture (extension added/modified automatically)
    def mediaDownloadFile(self,dirname,fname,outFileName):
        url = self.base_url + '/videos/DCIM/' + dirname + "/" + fname
        outFileName = outFileName.split('.')[0] + '.' + fname.split('.')[1]
        with requests.get(url, stream=True) as request:
            request.raise_for_status()
            with open(outFileName, "wb") as f:
                for chunk in request.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True
        


