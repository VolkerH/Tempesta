# -*- coding: utf-8 -*-
"""
Created on Mon Jun 16 18:19:24 2014

@authors: Federico Barabas, Luciano Masullo
"""

import subprocess
import sys
import numpy as np
import os
import datetime
import time
import re
import ctypes
import matplotlib.pyplot as plt

from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph as pg
import pyqtgraph.ptime as ptime
from pyqtgraph.parametertree import Parameter, ParameterTree
from pyqtgraph.dockarea import Dock, DockArea
from pyqtgraph.console import ConsoleWidget

from tkinter import Tk, filedialog, messagebox
import h5py as hdf
import tifffile as tiff     # http://www.lfd.uci.edu/~gohlke/pythonlibs/#vlfd
from lantz import Q_

# tormenta imports
import control.lasercontrol as lasercontrol
import control.SignalGen as SignalGen
import control.Scan as Scan
import control.focus as focus
import control.align as align
import control.molecules_counter as moleculesCounter
import control.ontime as ontime
import control.guitools as guitools
from control import libnidaqmx

#Widget to control image or sequence recording. Recording only possible when liveview active.
#StartRecording called when "Rec" presset. Creates recording thread with RecWorker, recording is then 
#done in this seperate thread.

class RecordingWidget(QtGui.QFrame):

    def __init__(self, main, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.main = main
        self.dataname = 'data'      # In case I need a QLineEdit for this

        self.recworkers = [None, None]
        self.recthreads = [None, None]

        startdir = r'F:\Tempesta\DefaultDataFolderSSD\%s'
        newfolderpath =  startdir % time.strftime('%Y-%m-%d')
        if not os.path.exists(newfolderpath):
            os.mkdir(newfolderpath)

        self.z_stack  = []
        self.rec_mode = 1;
        self.initialDir = newfolderpath
        
        self.filesizewar = QtGui.QMessageBox()
        self.filesizewar.setText("File size is very big!")
        self.filesizewar.setInformativeText("Are you sure you want to continue?")
        self.filesizewar.setStandardButtons(QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
        
        # Title
        recTitle = QtGui.QLabel('<h2><strong>Recording</strong></h2>')
        recTitle.setTextFormat(QtCore.Qt.RichText)
        self.setFrameStyle(QtGui.QFrame.Panel | QtGui.QFrame.Raised)
        
        # Folder and filename fields
        self.folderEdit = QtGui.QLineEdit(self.initialDir)
#        openFolderButton = QtGui.QPushButton('Open')
#        openFolderButton.clicked.connect(self.openFolder)
#        loadFolderButton = QtGui.QPushButton('Load...')
#        loadFolderButton.clicked.connect(self.loadFolder)
        self.specifyfile = QtGui.QCheckBox('Specify file name')
        self.specifyfile.clicked.connect(self.specFile)
        self.filenameEdit = QtGui.QLineEdit('Current_time')

        # Snap and recording buttons
        self.showZgraph = QtGui.QCheckBox('Show Z-graph')
        self.showZproj = QtGui.QCheckBox('Show Z-projection')
        self.showBead_scan = QtGui.QCheckBox('Show bead scan')
        self.DualCam = QtGui.QCheckBox('Two-cam rec')
        self.snapTIFFButton = QtGui.QPushButton('Snap')
        self.snapTIFFButton.setStyleSheet("font-size:16px")
        self.snapTIFFButton.setSizePolicy(QtGui.QSizePolicy.Preferred,
                                          QtGui.QSizePolicy.Expanding)
        self.snapTIFFButton.clicked.connect(self.snapTIFF)
        self.recButton = QtGui.QPushButton('REC')
        self.recButton.setStyleSheet("font-size:16px")
        self.recButton.setCheckable(True)
        self.recButton.setSizePolicy(QtGui.QSizePolicy.Preferred,
                                     QtGui.QSizePolicy.Expanding)
        self.recButton.clicked.connect(self.startRecording)

        # Number of frames and measurement timing
        self.specifyFrames = QtGui.QRadioButton('Nr of frames')
        self.specifyFrames.clicked.connect(self.specFrames)
        self.specifyTime = QtGui.QRadioButton('Time to rec (sec)')
        self.specifyTime.clicked.connect(self.specTime)
        self.untilSTOPbtn = QtGui.QRadioButton('Run until STOP')
        self.untilSTOPbtn.clicked.connect(self.untilStop)
        self.timeToRec = QtGui.QLineEdit('1')
        self.timeToRec.setFixedWidth(45)
        self.timeToRec.textChanged.connect(self.filesizeupdate)
        self.currentTime = QtGui.QLabel('0 /')
        self.currentTime.setAlignment((QtCore.Qt.AlignRight |
                                        QtCore.Qt.AlignVCenter))
        self.currentFrame = QtGui.QLabel('0 /')
        self.currentFrame.setAlignment((QtCore.Qt.AlignRight |
                                        QtCore.Qt.AlignVCenter))
        self.currentFrame.setFixedWidth(45)
        self.numExpositionsEdit = QtGui.QLineEdit('100')
        self.numExpositionsEdit.setFixedWidth(45)
        self.tRemaining = QtGui.QLabel()
        self.tRemaining.setAlignment((QtCore.Qt.AlignCenter |
                                      QtCore.Qt.AlignVCenter))
        self.numExpositionsEdit.textChanged.connect(self.filesizeupdate)
#        self.updateRemaining()

        self.progressBar = QtGui.QProgressBar()
        self.progressBar.setTextVisible(False)
        
        self.filesizeBar = QtGui.QProgressBar()
        self.filesizeBar.setTextVisible(False)
        self.filesizeBar.setRange(0, 2000000000)

        # Layout
        buttonWidget = QtGui.QWidget()
        buttonGrid = QtGui.QGridLayout()
        buttonWidget.setLayout(buttonGrid)
        buttonGrid.addWidget(self.snapTIFFButton, 0, 0)
#        buttonGrid.addWidget(self.snapHDFButton, 0, 1)
        buttonWidget.setSizePolicy(QtGui.QSizePolicy.Preferred,
                                   QtGui.QSizePolicy.Expanding)
        buttonGrid.addWidget(self.recButton, 0, 2)

        recGrid = QtGui.QGridLayout()
        self.setLayout(recGrid)

# Graphically adding the labels and fields etc to the gui. Four numbers specify row, column, rowspan
# and columnspan.
        recGrid.addWidget(recTitle, 0, 0, 1, 3)
        recGrid.addWidget(QtGui.QLabel('Folder'), 2, 0)
        recGrid.addWidget(self.showZgraph, 1, 0)
        recGrid.addWidget(self.showZproj, 1, 1)
        recGrid.addWidget(self.showBead_scan, 1, 2)
        recGrid.addWidget(self.DualCam, 1, 3)
#        recGrid.addWidget(loadFolderButton, 1, 5)
#        recGrid.addWidget(openFolderButton, 1, 4)
        recGrid.addWidget(self.folderEdit, 2, 1, 1, 5)
        recGrid.addWidget(self.specifyfile, 3, 0, 1, 5)
        recGrid.addWidget(self.filenameEdit, 3, 2, 1, 4)
        recGrid.addWidget(self.specifyFrames, 4, 0, 1, 5)
        recGrid.addWidget(self.currentFrame, 4, 1)
        recGrid.addWidget(self.numExpositionsEdit, 4, 2)
#        recGrid.addWidget(QtGui.QLabel('File size'), 4, 3, 1, 2)
#        recGrid.addWidget(self.filesizeBar, 4, 4, 1, 2)
        recGrid.addWidget(self.specifyTime, 5, 0, 1, 5)
        recGrid.addWidget(self.currentTime, 5, 1)
        recGrid.addWidget(self.timeToRec, 5, 2)
        recGrid.addWidget(self.tRemaining, 5, 3, 1, 2)
#        recGrid.addWidget(self.progressBar, 5, 4, 1, 2)
        recGrid.addWidget(self.untilSTOPbtn, 6, 0, 1, 5)
        recGrid.addWidget(buttonWidget, 7, 0, 1, 0)

        recGrid.setColumnMinimumWidth(0, 70)
        recGrid.setRowMinimumHeight(6, 40)

# Initial condition of fields and checkboxes.
        self.writable = True
        self.readyToRecord = False
        self.filenameEdit.setEnabled(False)
        self.specifyTime.setChecked(True)
        self.specTime()
        self.filesizeupdate()

    @property
    def readyToRecord(self):
        return self._readyToRecord

    @readyToRecord.setter
    def readyToRecord(self, value):
        self.snapTIFFButton.setEnabled(value)
#        self.snapHDFButton.setEnabled(value)
        self.recButton.setEnabled(value)
        self._readyToRecord = value

    @property
    def writable(self):
        return self._writable

# Setter for the writable property. If Nr of frame is checked only the frames field is
# set active and vice versa.

    @writable.setter
    def writable(self, value):
        if value:
            if self.specifyFrames.isChecked():
                self.specFrames()
            elif self.specifyTime.isChecked():
                self.specTime()
            else:
                self.untilStop()
        else:
            self.numExpositionsEdit.setEnabled(False)
            self.timeToRec.setEnabled(False)
#        self.folderEdit.setEnabled(value)
#        self.filenameEdit.setEnabled(value)
        self._writable = value

    def specFile(self):
        
        if self.specifyfile.checkState():
            self.filenameEdit.setEnabled(True)
            self.filenameEdit.setText('Filename')
        else:
            self.filenameEdit.setEnabled(False)
            self.filenameEdit.setText('Current time')

# Functions for changing between choosing frames or time or "Run until stop" when recording.
            
    def specFrames(self):
        
        self.numExpositionsEdit.setEnabled(True)
        self.timeToRec.setEnabled(False)
        self.filesizeBar.setEnabled(True)
        self.progressBar.setEnabled(True)
        self.rec_mode = 1
        self.filesizeupdate()
    
    def specTime(self):
        self.numExpositionsEdit.setEnabled(False)
        self.timeToRec.setEnabled(True)
        self.filesizeBar.setEnabled(True)
        self.progressBar.setEnabled(True)
        self.rec_mode = 2
        self.filesizeupdate()
        
    def untilStop(self):
        self.numExpositionsEdit.setEnabled(False)
        self.timeToRec.setEnabled(False)
        self.filesizeBar.setEnabled(False)
        self.progressBar.setEnabled(False)
        self.rec_mode = 3
            
# For updating the appriximated file size of and eventual recording. Called when frame dimensions
# or frames to record is changed.            
            
    def filesizeupdate(self):
        if self.specifyFrames.isChecked():
            frames = int(self.numExpositionsEdit.text())
        else:
            frames = int(self.timeToRec.text()) / self.main.RealExpPar.value()

        self.filesize = 2 * frames * max(self.main.shapes[0][0] * self.main.shapes[0][1], self.main.shapes[1][0] * self.main.shapes[1][1])
        self.filesizeBar.setValue(min(2000000000, self.filesize)) #Percentage of 2 GB
        self.filesizeBar.setFormat(str(self.filesize/1000))

    def n(self):
        text = self.numExpositionsEdit.text()
        if text == '':
            return 0
        else:
            return int(text)

# Function that returns the time to record in order to record the correct number of frames.
            
    def getTimeOrFrames(self):
        
        if self.specifyFrames.isChecked():
            return int(self.numExpositionsEdit.text())
        else:
            return int(self.timeToRec.text())

    def openFolder(self, path):
        if sys.platform == 'darwin':
            subprocess.check_call(['open', '', self.folderEdit.text()])
        elif sys.platform == 'linux':
            subprocess.check_call(['gnome-open', '', self.folderEdit.text()])
        elif sys.platform == 'win32':
            os.startfile(self.folderEdit.text())

    def loadFolder(self):
        try:
            root = Tk()
            root.withdraw()
            folder = filedialog.askdirectory(parent=root,
                                             initialdir=self.initialDir)
            root.destroy()
            if folder != '':
                self.folderEdit.setText(folder)
        except OSError:
            pass

    # Attributes saving
    def getAttrs(self):
        self.main.AbortROI()
        attrs = self.main.tree.attrs()

        for laserControl in self.main.laserWidgets.controls:
            name = re.sub('<[^<]+?>', '', laserControl.name.text())
            attrs.append((name, laserControl.laser.power))

        for key in self.main.scanWidget.scan_par_values:
            attrs.append((key, self.main.scanWidget.scan_par_values[key]))    
            
        attrs.append(('Scan mode', self.main.scanWidget.Scan_Mode.currentText()))
        attrs.append(('True_if_scanning', self.main.scanWidget.scanRadio.isChecked())) 
        
        for key in self.main.scanWidget.pixel_par_values:
            attrs.append((key, self.main.scanWidget.pixel_par_values[key]))
            
        attrs.extend([('element_size_um', [1, 0.066, 0.066]),
                      ('Date', time.strftime("%Y-%m-%d")),
                      ('Saved at', time.strftime("%H:%M:%S")),
                      ('NA', 1.42)])
            
        return attrs

    def snapHDF(self):

        folder = self.folderEdit.text()
        if os.path.exists(folder):

            image = self.main.image

            name = os.path.join(folder, self.getFileName())
            savename = guitools.getUniqueName(name + '.hdf5')
            store_file = hdf.File(savename)
            store_file.create_dataset(name=self.dataname, data=image)
            for item in self.getAttrs():
                if item[1] is not None:
                    store_file[self.dataname].attrs[item[0]] = item[1]
            store_file.close()

        else:
            self.folderWarning()
            
    def getFileName(self):
        
        if self.specifyfile.checkState():
            filename = self.filenameEdit.text()
            
        else:
            filename = time.strftime('%Hh%Mm%Ss')
            
        return filename
        
    def snapTIFF(self):
        folder = self.folderEdit.text()
        if os.path.exists(folder):

#            image = self.main.andor.most_recent_image16(self.main.shape)
            time.sleep(0.01)
            savename = (os.path.join(folder, self.getFileName()) +
                        '_snap.tiff')
            savename = guitools.getUniqueName(savename)
#            tiff.imsave(savename, np.flipud(image.astype(np.uint16)),
#                        description=self.dataname, software='Tormenta')
            tiff.imsave(savename, self.main.latest_image.astype(np.uint16),
                        description=self.dataname, software='Tormenta')
            guitools.attrsToTxt(os.path.splitext(savename)[0], self.getAttrs())

        else:
            self.folderWarning()

    def folderWarning(self):
        root = Tk()
        root.withdraw()
        messagebox.showwarning(title='Warning', message="Folder doesn't exist")
        root.destroy()

    def updateGUI(self):
        pass
#        eSecs = self.worker.timerecorded
#        nframe = self.worker.frames_recorded
#        rSecs = self.getTimeOrFrames() - eSecs
#        rText = '{}'.format(datetime.timedelta(seconds=max(0, rSecs)))
#        self.tRemaining.setText(rText)
#        self.currentFrame.setText(str(nframe) + ' /')
#        self.currentTime.setText(str(int(eSecs)) + ' /')
#        self.progressBar.setValue(100*(1 - rSecs / (eSecs + rSecs)))

# This funciton is called when "Rec" button is pressed. 

    def startRecording(self):
        if self.recButton.isChecked():  
            ret = QtGui.QMessageBox.Yes
            if self.filesize > 1500000000:  # Checks if estimated file size is dangourusly large, > 1,5GB-.
                ret = self.filesizewar.exec_()
                
            folder = self.folderEdit.text()
            if os.path.exists(folder) and ret == QtGui.QMessageBox.Yes:
                    
                self.writable = False # Sets Recording widget to not be writable during recording.
                self.readyToRecord = False
                self.recButton.setEnabled(True)
                self.recButton.setText('STOP')
                self.main.tree.writable = False # Sets camera parameters to not be writable during recording.
                self.main.liveviewButton.setEnabled(False)
#                self.main.liveviewStop() # Stops liveview from updating



                self.startTime = ptime.time() # Saves the time when started to calculate remaining time.

                if self.DualCam.checkState():                
                    self.nr_cameras = 2
                else:
                    self.nr_cameras = 1
                
                for i in range(0, self.nr_cameras):
                    ind = np.mod(self.main.curr_cam_ind + i, 2)
                    print('Starting recording on camera ' + str(ind+1))
                    self.savename = (os.path.join(folder, self.getFileName()) + '_rec_cam_' + str(ind+1) + '.hdf5') # Sets name for final output file
                    self.savename = guitools.getUniqueName(self.savename) # If same  filename exists it is appended by (1) or (2) etc.

                    self.recworkers[ind] = RecWorker(self.main.cameras[ind], self.rec_mode, self.getTimeOrFrames(), self.main.shapes[ind], self.main.lvworkers[ind],  #Creates an instance of RecWorker class.
                                            self.main.RealExpPar, self.savename,
                                            self.dataname, self.getAttrs())
                    self.recworkers[ind].updateSignal.connect(self.updateGUI)    # Connects the updatesignal that is continously emitted from recworker to updateGUI function.
                    self.recworkers[ind].doneSignal.connect(self.endRecording) # Connects the donesignal emitted from recworker to endrecording function.
                    self.recthreads[ind] = QtCore.QThread() # Creates a new thread
                    self.recworkers[ind].moveToThread(self.recthreads[ind]) # moves the worker object to this thread. 
                    self.recthreads[ind].started.connect(self.recworkers[ind].start)
                    
                for i in range(0, self.nr_cameras):
                    print('Starting recordings')
                    ind = np.mod(self.main.curr_cam_ind + i, 2)
                    self.recthreads[ind].start()

            else:
                self.recButton.setChecked(False)
                self.folderWarning()

        else:
            for i in range(0, self.nr_cameras):
                ind = np.mod(self.main.curr_cam_ind + i, 2)
                print('Terminating recording on camera index ' + str(ind))
                print(self.recworkers)
                self.recworkers[ind].pressed = False

# Function called when recording finishes to reset relevent parameters.

    def endRecording(self):
        if self.nr_cameras == 2 and (not self.recworkers[0].done or not self.recworkers[1].done):
            print('In first endRecordig "skip me" if')
        else:
            print('In endRecording')
            print('Show bead scan state is: ', self.showBead_scan.checkState())
            ind = self.main.curr_cam_ind
            if self.showZgraph.checkState():
                plt.figure()
                plt.plot(self.recworkers[ind].z_stack)
            if self.showZproj.checkState():
                plt.imshow(self.recworkers[ind].Z_projection, cmap='gray')
            if self.showBead_scan.checkState():
                data = self.recworkers[ind].z_stack
                print('Length of data = ', len(data))
                try:
                    data = self.recworkers[ind].z_stack
                    if not np.floor(np.sqrt(len(data))) == np.sqrt(len(data)):
                        del data[0]
                    imside = int(np.sqrt(np.size(data)))
                    print('Imside = ', imside)
                    data = np.reshape(data, [imside, imside])
                    data[::2] = np.fliplr(data[::2])
                    plt.figure()
                    plt.imshow(data, interpolation = 'none', cmap=plt.get_cmap('afmhot'))
                except:
                    pass
            for i in range(0, self.nr_cameras):
                ind = np.mod(self.main.curr_cam_ind + i, 2)
                self.recthreads[ind].terminate()
                self.main.lvworkers[ind].reset() # Same as done in Liveviewrun()
                self.main.cameras[ind].startAcquisition()
    #        converterFunction = lambda: guitools.TiffConverterThread(self.savename)
    #        self.main.exportlastAction.triggered.connect(converterFunction)
    #        self.main.exportlastAction.setEnabled(True)
            print('After terminating recording thread')
            self.writable = True
            self.readyToRecord = True
            self.recButton.setText('REC')
            self.recButton.setChecked(False)
            self.main.tree.writable = True
        
            self.main.liveviewButton.setEnabled(True)
    #        self.main.liveviewStart()
            self.progressBar.setValue(0)
            self.currentTime.setText('0 /')
            self.currentFrame.setText('0 /')
            


class RecWorker(QtCore.QObject):

    updateSignal = QtCore.pyqtSignal()
    doneSignal = QtCore.pyqtSignal()

    def __init__(self, camera, rec_mode, timeorframes, shape, lvworker, t_exp, savename, dataname, attrs,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.camera = camera
        self.rec_mode = rec_mode  # 1=frames, 2=time, 3=until stop
        print(self.rec_mode)
        self.timeorframes = timeorframes #Nr of seconds or frames to record depending on bool_ToF.
        self.shape = shape # Shape of one frame
        self.lvworker = lvworker
        self.t_exp = t_exp
        self.savename = savename
        self.dataname = dataname
        self.attrs = attrs
        self.pressed = True
        self.done = False


    def start(self):
        #Set initial values
        self.timerecorded = 0
        self.frames_recorded = 0

        time.sleep(0.1)
        
        #Find what the index of the first recorded frame will be
        last_f = self.lvworker.f_ind
        if last_f == None:
            start_f = 0 # If camera has not recorded any frames yet, start index will be zero
        else:
            start_f = last_f + 1 # index of first frame is one more then provious frame.
            
        self.starttime = time.time()
     
        # Main loop for waiting until recording is finished and sending update signal
        f_ind = start_f
        if self.rec_mode == 1:
            while self.frames_recorded < self.timeorframes and self.pressed:
                self.frames_recorded = self.lvworker.f_ind - start_f
                time.sleep(0.01)
                self.updateSignal.emit()
                
        elif self.rec_mode == 2:
            while self.timerecorded < self.timeorframes and self.pressed:
                self.timerecorded = time.time() - self.starttime
                time.sleep(0.01)
                self.updateSignal.emit()
        else:
            while self.pressed:
                self.timerecorded = time.time() - self.starttime
                time.sleep(0.01)
                self.updateSignal.emit()           
            
        self.camera.stopAcquisition()   # To avoid camera overwriting buffer while saving recording
        end_f = self.lvworker.f_ind # Get index of the last acquired frame
        
        if end_f == None: #If no frames are acquired during recording, 
            end_f = -1
            
        if end_f >= start_f - 1:
            f_range = range(start_f, end_f + 1)
        else:
            buffer_size = self.camera.number_image_buffers
            f_range = np.append(range(start_f, buffer_size), range(0, end_f + 1))
            
        print('Start_f = :', start_f)
        print('End_f = :', end_f)
        f_ind = len(f_range)
        data = [];
        for i in f_range:
            data.append(self.camera.hcam_data[i].getData())

        datashape = (f_ind, self.shape[1], self.shape[0])     # Adapted for ImageJ data read shape

        print('Savename = ', self.savename)
        self.store_file = hdf.File(self.savename, "w")
        print('File opened')
        self.store_file.create_dataset(name=self.dataname, shape=datashape, maxshape=datashape, dtype=np.uint16)
        print('Created dataset')
        dataset = self.store_file[self.dataname]

            
        reshapeddata = np.reshape(data, datashape, order='C')
        t = time.time()
        dataset[...] = reshapeddata
        elapsed = time.time() - t
        print('Data written, time to write: ', elapsed)
        self.z_stack = []
        for i in range(0, f_ind):
            self.z_stack.append(np.mean(reshapeddata[i,:,:]))
        
        self.Z_projection = np.flipud(np.sum(reshapeddata, 0))
        # Saving parameters
        for item in self.attrs:
            if item[1] is not None:
                dataset.attrs[item[0]] = item[1]
     
        self.store_file.close() 
        self.done = True
        self.doneSignal.emit()
        print('doneSignal emitted from thread')

class FileWarning(QtGui.QMessageBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class CamParamTree(ParameterTree):
    """ Making the ParameterTree for configuration of the camera during imaging
    """

    def __init__(self, orcaflash, *args, **kwargs):
        super().__init__(*args, **kwargs)

        BinTip = ("Sets binning mode. Binning mode specifies if and how many \n"
                    "pixels are to be read out and interpreted as a single pixel value.")
                    

        # Parameter tree for the camera configuration
        params = [{'name': 'Camera', 'type': 'str',
                   'value': orcaflash.camera_id},
                  {'name': 'Image frame', 'type': 'group', 'children': [
                      {'name': 'Binning', 'type': 'list', 
                                  'values': [1, 2, 4], 'tip': BinTip},
{'name': 'Mode', 'type': 'list', 'values': ['Full Widefield', 'Full chip', 'Minimal line', 'Microlenses v2', 'Microlenses v3', 'Fast ROI v2', 'Fast ROI v3', 'Custom']},
{'name': 'X0', 'type': 'int', 'value': 0, 'limits': (0, 2044)},
{'name': 'Y0', 'type': 'int', 'value': 0, 'limits': (0, 2044)},
{'name': 'Width', 'type': 'int', 'value': 2048, 'limits': (1, 2048)},
{'name': 'Height', 'type': 'int', 'value': 2048, 'limits': (1, 2048)}, 
                                  {'name': 'Apply', 'type': 'action'},
{'name': 'New ROI', 'type': 'action'}, {'name': 'Abort ROI', 'type': 'action', 'align': 'right'}]},
                  {'name': 'Timings', 'type': 'group', 'children': [
                      {'name': 'Set exposure time', 'type': 'float',
                       'value': 0.03, 'limits': (0,
                                                9999),
                       'siPrefix': True, 'suffix': 's'},
                      {'name': 'Real exposure time', 'type': 'float',
                       'value': 0, 'readonly': True, 'siPrefix': True,
                       'suffix': ' s'},
                      {'name': 'Internal frame interval', 'type': 'float',
                       'value': 0, 'readonly': True, 'siPrefix': True,
                       'suffix': ' s'},
                      {'name': 'Readout time', 'type': 'float',
                       'value': 0, 'readonly': True, 'siPrefix': True,
                       'suffix': 's'},
                      {'name': 'Internal frame rate', 'type': 'float',
                       'value': 0, 'readonly': True, 'siPrefix': False,
                       'suffix': ' fps'}]}, 
                       {'name': 'Acquisition mode', 'type': 'group', 'children': [
                      {'name': 'Trigger source', 'type': 'list',
                       'values': ['Internal trigger', 'External "Start-trigger"', 'External "frame-trigger"'],
                       'siPrefix': True, 'suffix': 's'}]}]

        self.p = Parameter.create(name='params', type='group', children=params)
        self.setParameters(self.p, showTop=False)
        self._writable = True

    def enableCropMode(self):
        value = self.frameTransferParam.value()
        if value:
            self.cropModeEnableParam.setWritable(True)
        else:
            self.cropModeEnableParam.setValue(False)
            self.cropModeEnableParam.setWritable(False)

    @property
    def writable(self):
        return self._writable

    @writable.setter
    def writable(self, value):
        """
        property to set basically the whole parameters tree as writable
        (value=True) or not writable (value=False)
        useful to set it as not writable during recording
        """
        self._writable = value
        framePar = self.p.param('Image frame')
        framePar.param('Binning').setWritable(value)
        framePar.param('Mode').setWritable(value)
        framePar.param('X0').setWritable(value)
        framePar.param('Y0').setWritable(value)
        framePar.param('Width').setWritable(value)
        framePar.param('Height').setWritable(value)
#       WARNING: If Apply and New ROI button are included here they will emit status changed signal
        # and their respective functions will be called... -> problems.
        
        timingPar = self.p.param('Timings')
        timingPar.param('Set exposure time').setWritable(value)

    def attrs(self):
        attrs = []
        for ParName in self.p.getValues():
            print(ParName)
            Par = self.p.param(str(ParName))
            if not(Par.hasChildren()):
                attrs.append((str(ParName), Par.value()))
            else:
                for sParName in Par.getValues():
                    sPar = Par.param(str(sParName))
                    if sPar.type() != 'action':
                        if not(sPar.hasChildren()):
                            attrs.append((str(sParName), sPar.value()))
                        else:
                            for ssParName in sPar.getValues():
                                ssPar = sPar.param(str(ssParName))
                                attrs.append((str(ssParName), ssPar.value()))
        return attrs


class LVWorker(QtCore.QObject):
    
    def __init__(self, main, ind, orcaflash, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main = main
        self.ind = ind
        self.orcaflash = orcaflash
        self.running = False
        self.f_ind = None
        self.mem = 0  # Memory variable to keep track of if update has been run many times in a row with camera trigger source as internal trigger
                        # If so the GUI trigger mode should also be set to internal trigger. Happens when using external start tigger.
    def run(self):
        
        self.vtimer = QtCore.QTimer()
        self.vtimer.timeout.connect(self.update)
        self.running = True
        self.f_ind = None # Should maybe be f_ind
        self.vtimer.start(30)
        print('f_ind when started = ',self.f_ind)
        
    def update(self):

        if self.running:
            self.f_ind = self.orcaflash.newFrames()[-1]
#            print('f_ind = :', self.f_ind)
            frame = self.orcaflash.hcam_data[self.f_ind].getData()
            self.image = np.reshape(frame, (self.orcaflash.frame_x, self.orcaflash.frame_y), 'F')
            self.main.latest_images[self.ind] = self.image
            
            """Following is causing problems with two cameras..."""
#            trigger_source = self.orcaflash.getPropertyValue('trigger_source')[0]
#            print('Trigger source = ', trigger_source)
#            if trigger_source == 1:
#                if self.mem == 3:
#                    self.main.trigsourceparam.setValue('Internal trigger')
#                    self.mem = 0
#                else:
#                    self.mem = self.mem + 1

        
    def stop(self):
        if self.running:
            self.running = False
            print('Acquisition stopped')
        else:
            print('Cannot stop when not running (from LVThread)')
            
    def reset(self):
        self.f_ind = None
        print('LVworker reset, f_ind = ', self.f_ind)

# The main GUI class.



class TormentaGUI(QtGui.QMainWindow):

    liveviewStarts = QtCore.pyqtSignal()
    liveviewEnds = QtCore.pyqtSignal()

    def __init__(self, bluelaser, bluelaser2, greenlaser, violetlaser, uvlaser, scanZ, daq, orcaflashV2, orcaflashV3,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.cameras = [orcaflashV2, orcaflashV3]        
        
        self.orcaflash = self.cameras[0]
        self.changeParameter(lambda: self.cameras[0].setPropertyValue('trigger_polarity', 2))
        self.changeParameter(lambda: self.cameras[1].setPropertyValue('trigger_polarity', 2))
        self.changeParameter(lambda: self.cameras[0].setPropertyValue('trigger_global_exposure', 5)) # 3:DELAYED, 5:GLOBAL RESET
        self.changeParameter(lambda: self.cameras[1].setPropertyValue('trigger_global_exposure', 5)) # 3:DELAYED, 5:GLOBAL RESET
#        self.changeParameter(lambda: self.orcaflash.setPropertyValue('defect_correct_mode', 2)) # 1:OFF, 2:ON
#        self.orcaflash.setPropertyValue('readout_speed', 1)
#        self.changeParameter(lambda: self.orcaflash.setPropertyValue('trigger_mode', 6))
        self.changeParameter(lambda: self.cameras[0].setPropertyValue('trigger_active', 2)) # 1: EGDE, 2: LEVEL, 3:SYNCHREADOUT
        self.changeParameter(lambda: self.cameras[1].setPropertyValue('trigger_active', 2)) # 1: EGDE, 2: LEVEL, 3:SYNCHREADOUT        
        self.shapes = [(self.cameras[0].getPropertyValue('image_height')[0], self.cameras[0].getPropertyValue('image_width')[0]),
                        (self.cameras[1].getPropertyValue('image_height')[0], self.cameras[1].getPropertyValue('image_width')[0])]
        self.frameStart = (0, 0)
        self.scanZ = scanZ
        self.daq = daq
        self.nidaq = libnidaqmx.Device('Dev1')
        self.lvworkers = [None, None]
        self.lvthreads = [None, None]
        self.curr_cam_ind = 0
        self.latest_images = [np.zeros(self.shapes[self.curr_cam_ind]), np.zeros(self.shapes[self.curr_cam_ind])]
        
        self.filewarning = FileWarning()

        self.s = Q_(1, 's')
        self.lastTime = time.clock()
        self.fps = None

        # Actions and menubar
        # Shortcut only
        self.liveviewAction = QtGui.QAction(self)
        self.liveviewAction.setShortcut('Ctrl+Space')
        QtGui.QShortcut(QtGui.QKeySequence('Ctrl+Space'), self,
                        self.liveviewKey)
        self.liveviewAction.triggered.connect(self.liveviewKey)
        self.liveviewAction.setEnabled(False)

        # Actions in menubar
        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&File')

        self.savePresetAction = QtGui.QAction('Save configuration...', self)
        self.savePresetAction.setShortcut('Ctrl+S')
        self.savePresetAction.setStatusTip('Save camera & recording settings')
        savePresetFunction = lambda: guitools.savePreset(self)
        self.savePresetAction.triggered.connect(savePresetFunction)
        fileMenu.addAction(self.savePresetAction)
        fileMenu.addSeparator()

#        self.shuttersAction = QtGui.QAction(('Close shutters when recording '
#                                             'is over'), self, checkable=True)
#        self.shuttersAction.setChecked(True)
#        self.shuttersAction.setStatusTip(('Close all laser shutters when the '
#                                          'recording session is over'))
#        fileMenu.addAction(self.shuttersAction)
#        fileMenu.addSeparator()

#        snapMenu = fileMenu.addMenu('Snap format')
#        self.snapTiffAction = QtGui.QAction('TIFF', self, checkable=True)
#        snapMenu.addAction(self.snapTiffAction)
#        self.snapHdf5Action = QtGui.QAction('HDF5', self, checkable=True)
#        snapMenu.addAction(self.snapHdf5Action)
        self.exportTiffAction = QtGui.QAction('Export HDF5 to Tiff...', self)
        self.exportTiffAction.setShortcut('Ctrl+E')
        self.exportTiffAction.setStatusTip('Export HDF5 file to Tiff format')
        self.exportTiffAction.triggered.connect(guitools.TiffConverterThread)
        fileMenu.addAction(self.exportTiffAction)

        self.exportlastAction = QtGui.QAction('Export last recording to Tiff',
                                              self)
        self.exportlastAction.setEnabled(False)
        self.exportlastAction.setShortcut('Ctrl+L')
        self.exportlastAction.setStatusTip('Export last recording to Tiff ' +
                                           'format')
        fileMenu.addAction(self.exportlastAction)
        fileMenu.addSeparator()

        exitAction = QtGui.QAction(QtGui.QIcon('exit.png'), '&Exit', self)
        exitAction.setShortcut('Ctrl+Q')
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(QtGui.QApplication.closeAllWindows)
        fileMenu.addAction(exitAction)

        self.tree = CamParamTree(self.orcaflash)

        # Indicator for loading frame shape from a preset setting 
        # Currently not used.
        self.customFrameLoaded = False
        self.cropLoaded = False

        # Camera binning signals. Defines seperate variables for each parameter and connects the signal
        # emitted when they've been changed to a function that actually changes the parameters on the camera
        # or other appropriate action.
        self.framePar = self.tree.p.param('Image frame')
        self.binPar = self.framePar.param('Binning')
        self.binPar.sigValueChanged.connect(self.setBinning)
        self.FrameMode = self.framePar.param('Mode')
        self.FrameMode.sigValueChanged.connect(self.updateFrame)
        self.X0par= self.framePar.param('X0')
        self.Y0par= self.framePar.param('Y0')
        self.Widthpar= self.framePar.param('Width')
        self.Heightpar= self.framePar.param('Height')
        self.applyParam = self.framePar.param('Apply')
        self.NewROIParam = self.framePar.param('New ROI')
        self.AbortROIParam = self.framePar.param('Abort ROI')
        self.applyParam.sigStateChanged.connect(self.applyfcn)  #WARNING: This signal is emitted whenever anything about the status of the parameter changes eg is set writable or not.
        self.NewROIParam.sigStateChanged.connect(self.updateFrame)
        self.AbortROIParam.sigStateChanged.connect(self.AbortROI)


        
        # Exposition signals
        timingsPar = self.tree.p.param('Timings')
        self.EffFRPar = timingsPar.param('Internal frame rate')
        self.expPar = timingsPar.param('Set exposure time')
        self.expPar.sigValueChanged.connect(self.setExposure)
        self.ReadoutPar = timingsPar.param('Readout time')
        self.RealExpPar = timingsPar.param('Real exposure time')
        self.FrameInt = timingsPar.param('Internal frame interval')
        self.RealExpPar.setOpts(decimals = 5)
        self.setExposure()    # Set default values
        
        #Acquisition signals
        acquisParam = self.tree.p.param('Acquisition mode')
        self.trigsourceparam = acquisParam.param('Trigger source')
        self.trigsourceparam.sigValueChanged.connect(self.ChangeTriggerSource)

        # Gain signals
#        self.PreGainPar = self.tree.p.param('Gain').param('Pre-amp gain')
#        updateGain = lambda: self.setGain
#        self.PreGainPar.sigValueChanged.connect(updateGain)
#        self.GainPar = self.tree.p.param('Gain').param('EM gain')
#        self.GainPar.sigValueChanged.connect(updateGain)
#        updateGain()        # Set default values

        # Camera settings widget
        cameraWidget = QtGui.QFrame()
        cameraWidget.setFrameStyle(QtGui.QFrame.Panel | QtGui.QFrame.Raised)
        cameraTitle = QtGui.QLabel('<h2><strong>Camera settings</strong></h2>')
        cameraTitle.setTextFormat(QtCore.Qt.RichText)
        cameraGrid = QtGui.QGridLayout()
        cameraWidget.setLayout(cameraGrid)
        cameraGrid.addWidget(cameraTitle, 0, 0)
        cameraGrid.addWidget(self.tree, 1, 0)

        self.presetsMenu = QtGui.QComboBox()
        self.presetDir = r'C:\Users\Usuario\Documents\Data\Presets'
        if not(os.path.isdir(self.presetDir)):
            self.presetDir = os.path.join(os.getcwd(), 'control/Presets')
        for preset in os.listdir(self.presetDir):
            self.presetsMenu.addItem(preset)
        self.loadPresetButton = QtGui.QPushButton('Load preset')
        loadPresetFunction = lambda: guitools.loadPreset(self)
        self.loadPresetButton.pressed.connect(loadPresetFunction)

        # Liveview functionality
        self.liveviewButton = QtGui.QPushButton('LIVEVIEW')
        self.liveviewButton.setStyleSheet("font-size:18px")
        self.liveviewButton.setCheckable(True)
        self.liveviewButton.setSizePolicy(QtGui.QSizePolicy.Preferred,
                                          QtGui.QSizePolicy.Expanding)
        self.liveviewButton.clicked.connect(self.liveview)      #Link button click to funciton liveview
        self.liveviewButton.setEnabled(True)
        self.viewtimer1 = QtCore.QTimer()
        self.viewtimer1.timeout.connect(self.updateView)
        self.viewtimer2 = QtCore.QTimer()
        self.viewtimer2.timeout.connect(self.updateView)
        self.viewtimers = [self.viewtimer1, self.viewtimer2]
        
        self.liveviewrunning = [False, False]        
        
        self.alignmentON = False
        
        # RESOLFT rec
        
        self.resolftRecButton = QtGui.QPushButton('RESOLFT REC')
        self.resolftRecButton.setStyleSheet("font-size:18px")
        self.resolftRecButton.clicked.connect(self.resolftRec)
        
        self.ToggleCamButton = QtGui.QPushButton('Toggle camera')
        self.ToggleCamButton.setStyleSheet("font-size:18px")
        self.ToggleCamButton.clicked.connect(self.toggle_camera)
        self.CamLabel = QtGui.QLabel('OrcaFlash V2')
        self.CamLabel.setStyleSheet("font-size:18px")
        
        # viewBox custom Tools
#        self.gridButton = QtGui.QPushButton('Grid')
#        self.gridButton.setCheckable(True)
#        self.gridButton.setEnabled(False)
#        self.grid2Button = QtGui.QPushButton('Two-color grid')
#        self.grid2Button.setCheckable(True)
#        self.grid2Button.setEnabled(False)
#        self.crosshairButton = QtGui.QPushButton('Crosshair')
#        self.crosshairButton.setCheckable(True)
#        self.crosshairButton.setEnabled(False)

#        self.flipperButton = QtGui.QPushButton('x1000')
#        self.flipperButton.setStyleSheet("font-size:16px")
#        self.flipperButton.setCheckable(True)
#        self.flipperButton.clicked.connect(self.daq.toggleFlipper)

        self.viewCtrl = QtGui.QWidget()
        self.viewCtrlLayout = QtGui.QGridLayout()
        self.viewCtrl.setLayout(self.viewCtrlLayout)
        self.viewCtrlLayout.addWidget(self.liveviewButton, 0, 0, 1, 3)
        self.viewCtrlLayout.addWidget( self.resolftRecButton, 1, 0, 1, 3)
        self.viewCtrlLayout.addWidget( self.ToggleCamButton, 2, 0, 1, 2)
        self.viewCtrlLayout.addWidget( self.CamLabel, 2, 2, 1, 1)
#        self.viewCtrlLayout.addWidget(self.gridButton, 1, 0)
#        self.viewCtrlLayout.addWidget(self.grid2Button, 1, 1)
#        self.viewCtrlLayout.addWidget(self.crosshairButton, 1, 2)
#        self.viewCtrlLayout.addWidget(self.flipperButton, 2, 0, 1, 3)

        self.fpsBox = QtGui.QLabel()
        self.fpsBox.setText('0 fps')
        self.statusBar().addPermanentWidget(self.fpsBox)
        self.tempStatus = QtGui.QLabel()
        self.statusBar().addPermanentWidget(self.tempStatus)
        self.temp = QtGui.QLabel()
        self.statusBar().addPermanentWidget(self.temp)
        self.cursorPos = QtGui.QLabel()
        self.cursorPos.setText('0, 0')
        self.statusBar().addPermanentWidget(self.cursorPos)

        # Temperature stabilization functionality
#        self.tempSetPoint = Q_(-50, 'degC')
#        self.stabilizer = TemperatureStabilizer(self)
#        self.stabilizerThread = QtCore.QThread()
#        self.stabilizer.moveToThread(self.stabilizerThread)
#        self.stabilizerThread.started.connect(self.stabilizer.start)
#        self.stabilizerThread.start()
#        self.liveviewStarts.connect(self.stabilizer.stop)
#        self.liveviewEnds.connect(self.stabilizer.start)

        # Recording settings widget
        self.recWidget = RecordingWidget(self)

        # Image Widget
        imageWidget = pg.GraphicsLayoutWidget()
        self.vb = imageWidget.addViewBox(row=1, col=1)
        self.vb.setMouseMode(pg.ViewBox.RectMode)
        self.img = pg.ImageItem()
        self.lut = guitools.cubehelix()
        self.img.setLookupTable(self.lut)
        self.img.translate(-0.5, -0.5)
#        self.img.setPxMode(True)
        self.vb.addItem(self.img)
        self.vb.setAspectLocked(True)
        self.hist = pg.HistogramLUTItem(image=self.img)
#        self.hist.vb.setLimits(yMin=0, yMax=2048)
        imageWidget.addItem(self.hist, row=1, col=2)
        self.ROI = guitools.ROI((0, 0), self.vb, (0, 0),
                                handlePos=(1, 0), handleCenter=(0, 1), 
                                color='y', scaleSnap=True, translateSnap=True)
        self.ROI.sigRegionChangeFinished.connect(self.ROIchanged)
        self.ROI.hide()
        
        # x and y profiles
        xPlot = imageWidget.addPlot(row=0, col=1)
        xPlot.hideAxis('left')
        xPlot.hideAxis('bottom')
        self.xProfile = xPlot.plot()
        imageWidget.ci.layout.setRowMaximumHeight(0, 40)
        xPlot.setXLink(self.vb)
        yPlot = imageWidget.addPlot(row=1, col=0)
        yPlot.hideAxis('left')
        yPlot.hideAxis('bottom')
        self.yProfile = yPlot.plot()
        self.yProfile.rotate(90)
        imageWidget.ci.layout.setColumnMaximumWidth(0, 40)
        yPlot.setYLink(self.vb)

        # Initial camera configuration taken from the parameter tree
        self.orcaflash.setPropertyValue('exposure_time', self.expPar.value())
        self.adjustFrame()
        self.toggle_camera()
        self.adjustFrame()

        # Dock widget
        dockArea = DockArea()

        laserDock = Dock("Laser Control", size=(1, 1))
        self.lasers = (bluelaser, bluelaser2, greenlaser, violetlaser, uvlaser)
        self.laserWidgets = lasercontrol.LaserWidget(self.lasers, self.daq)
        laserDock.addWidget(self.laserWidgets)
        dockArea.addDock(laserDock)

        scanDock = Dock('Scan')
        self.scanWidget = Scan.ScanWidget(self.nidaq)
        scanDock.addWidget(self.scanWidget)
        dockArea.addDock(scanDock)
        
#        # Console widget
#        consoleDock = Dock("Console", size=(600, 200))
#        console = ConsoleWidget(namespace={'pg': pg, 'np': np})
#        consoleDock.addWidget(console)
#        dockArea.addDock(consoleDock, 'above', scanDock)
#        
        # Line Alignment Tool
        alignmentDock = Dock("Alignment Tool", size=(50,50))
        self.alignmentWidget = QtGui.QWidget()
        alignmentDock.addWidget(self.alignmentWidget)
        dockArea.addDock(alignmentDock)
        
        alignmentLayout = QtGui.QGridLayout()
        self.alignmentWidget.setLayout(alignmentLayout)
        
        self.angleLabel = QtGui.QLabel('Line Angle')
        self.angleEdit = QtGui.QLineEdit('30')
        self.alignmentLineMakerButton = QtGui.QPushButton('Make Alignment Line')
        self.angle = np.float(self.angleEdit.text())
            
        self.alignmentLineMakerButton.clicked.connect(self.alignmentToolAux)
        
        self.alignmentCheck = QtGui.QCheckBox('Show Alignment Tool')
        
        alignmentLayout.addWidget(self.angleLabel, 0, 0, 1, 1)
        alignmentLayout.addWidget(self.angleEdit, 0, 1, 1, 1)
        alignmentLayout.addWidget(self.alignmentLineMakerButton, 1, 0, 1, 1)
        alignmentLayout.addWidget(self.alignmentCheck, 1, 1, 1, 1)
        
##         Z Align widget
        ZalignDock = Dock("Axial Alignment Tool", size=(1, 1))
        self.ZalignWidget = align.AlignWidgetAverage(self)
        ZalignDock.addWidget(self.ZalignWidget)
        dockArea.addDock(ZalignDock, 'above', scanDock)
        
        ##         Z Align widget
        RotalignDock = Dock("Rotational Alignment Tool", size=(1, 1))
        self.RotalignWidget = align.AlignWidgetXYProject(self)
        RotalignDock.addWidget(self.RotalignWidget)
        dockArea.addDock(RotalignDock, 'above', ZalignDock)



##         Focus lock widget
#        focusDock = Dock("Focus Control", size=(1, 1))
##        self.focusWidget = FocusWidget(DAQ, scanZ, self.recWidget)
#        self.focusWidget = focus.FocusWidget(scanZ, self.recWidget)
##        self.focusThread = QtCore.QThread()
##        self.focusWidget.moveToThread(self.focusThread)
##        self.focusThread.started.connect(self.focusWidget)
##        self.focusThread.start()
#        focusDock.addWidget(self.focusWidget)
#        dockArea.addDock(focusDock)
#        
#        
#        # Signal generation widget
#        signalDock = Dock('Signal Generator')
#        self.signalWidget = SignalGen.SigGenWidget(self.nidaq)
#        signalDock.addWidget(self.signalWidget)
#        dockArea.addDock(signalDock, 'above', laserDock)
        
        

        self.setWindowTitle('Tempesta')
        self.cwidget = QtGui.QWidget()
        self.setCentralWidget(self.cwidget)

        # Widgets' layout
        layout = QtGui.QGridLayout()
        self.cwidget.setLayout(layout)
        layout.setColumnMinimumWidth(0, 350)
        layout.setColumnMinimumWidth(2, 600)
        layout.setColumnMinimumWidth(3, 200)
        layout.setRowMinimumHeight(1, 550)
        layout.setRowMinimumHeight(2, 100)
        layout.setRowMinimumHeight(3, 300)
        layout.addWidget(self.presetsMenu, 0, 0)
        layout.addWidget(self.loadPresetButton, 0, 1)
        layout.addWidget(cameraWidget, 1, 0, 1, 2)
        layout.addWidget(self.viewCtrl, 2, 0, 1, 2)
        layout.addWidget(self.recWidget, 3, 0, 2, 2)
        layout.addWidget(imageWidget, 0, 2, 5, 1)
        layout.addWidget(dockArea, 0, 3, 5, 1)

        layout.setRowMinimumHeight(2, 40)
        layout.setColumnMinimumWidth(2, 1000)
        
        
    def testfunction(self):
        pass
    
    def toggle_camera(self):

        if self.orcaflash == self.cameras[1]:
            self.orcaflash = self.cameras[0]
            self.CamLabel.setText('OrcaFlash V2')
        else:
            self.orcaflash = self.cameras[1]
            self.CamLabel.setText('OrcaFlash V3')
        
         
        self.curr_cam_ind = np.mod(self.curr_cam_ind + 1, 2)  
        self.liveviewButton.setChecked(self.liveviewrunning[self.curr_cam_ind])
        self.updateTimings()
        self.expPar.setValue(self.RealExpPar.value())
        
    def applyfcn(self):
        print('Apply pressed')
        self.adjustFrame()

    def mouseMoved(self, pos):
        if self.vb.sceneBoundingRect().contains(pos):
            mousePoint = self.vb.mapSceneToView(pos)
            x, y = int(mousePoint.x()), int(self.shapes[self.curr_cam_ind][1] - mousePoint.y())
            self.cursorPos.setText('{}, {}'.format(x, y))

    def flipperInPath(self, value):
        pass
#        self.flipperButton.setChecked(not(value))
#        self.daq.flipper = value


    def changeParameter(self, function):
        """ This method is used to change those camera properties that need
        the camera to be idle to be able to be adjusted.
        """
        try:
            function()
        except:
            self.liveviewPause()
            function()
            self.liveviewRun()


    def ChangeTriggerSource(self):
        print('In ChangeTriggerSource with parameter value: ', self.trigsourceparam.value())
        if self.trigsourceparam.value() == 'Internal trigger':
            print('Changing to internal trigger')
            self.changeParameter(lambda: self.cameras[self.curr_cam_ind].setPropertyValue('trigger_source', 1))
#            self.RealExpPar.Enable(True)
#            self.EffFRPar.Enable(True)
            
        elif self.trigsourceparam.value() == 'External "Start-trigger"':
            print('Changing to external start trigger')
            self.changeParameter(lambda: self.cameras[self.curr_cam_ind].setPropertyValue('trigger_source', 2))
            self.changeParameter(lambda: self.cameras[self.curr_cam_ind].setPropertyValue('trigger_mode', 6))
            print(self.cameras[self.curr_cam_ind].getPropertyValue('trigger_mode'))
#            self.RealExpPar.Enable(False)
#            self.EffFRPar.Enable(False)
        
        elif self.trigsourceparam.value() == 'External "frame-trigger"':
            print('Changing to external trigger')
            self.changeParameter(lambda: self.cameras[self.curr_cam_ind].setPropertyValue('trigger_source', 2))
            self.changeParameter(lambda: self.cameras[self.curr_cam_ind].setPropertyValue('trigger_mode', 1))
            
        else:
            pass
                

    def updateLevels(self, image):
        std = np.std(image)
        self.hist.setLevels(np.min(image) - std, np.max(image) + std)

    def setBinning(self):
        
        """Method to change the binning of the captured frame"""

        binning = str(self.binPar.value())

        binstring = binning+'x'+binning
        coded = binstring.encode('ascii')
        

        self.changeParameter(lambda: self.orcaflash.setPropertyValue('binning', coded))


            
        
#    def setNrrows(self):
#        
#        """Method to change the number of rows of the captured frame"""
#        self.changeParameter(lambda: self.orcaflash.setPropertyValue('subarray_vsize', 8))
#
#    def setNrcols(self):
#        
#        """Method to change the number of rows of the captured frame"""
#        self.changeParameter(lambda: self.orcaflash.setPropertyValue('subarray_hsize', self.nrcolPar.value()))

    def setGain(self):
        """ Method to change the pre-amp gain and main gain of the EMCCD
        """
        pass
#        PreAmpGain = self.PreGainPar.value()
#        n = np.where(self.andor.PreAmps == PreAmpGain)[0][0]
#        # The (2 - n) accounts for the difference in order between the options
#        # in the GUI and the camera settings
#        self.andor.preamp = 2 - n
#        self.andor.EM_gain = self.GainPar.value()

    def setExposure(self):
        """ Method to change the exposure time setting
        """
        self.orcaflash.setPropertyValue('exposure_time', self.expPar.value())
        print('Exp time set to:', self.orcaflash.getPropertyValue('exposure_time'))
#        self.andor.frame_transfer_mode = self.FTMPar.value()
#        hhRatesArr = np.array([item.magnitude for item in self.andor.HRRates])
#        n_hrr = np.where(hhRatesArr == self.HRRatePar.value().magnitude)[0][0]
#        # The (3 - n) accounts for the difference in order between the options
#        # in the GUI and the camera settings
#        self.andor.horiz_shift_speed = 3 - n_hrr
#
#        n_vss = np.where(np.array([item.magnitude
#                                  for item in self.andor.vertSpeeds])
#                         == self.vertShiftSpeedPar.value().magnitude)[0][0]
#        self.andor.vert_shift_speed = n_vss
#
#        n_vsa = np.where(np.array(self.andor.vertAmps) ==
#                         self.vertShiftAmpPar.value())[0][0]
#        self.andor.set_vert_clock(n_vsa)
#
        self.updateTimings()
        
    def cropOrca(self, hpos, vpos, hsize, vsize):
        """Method to crop the frame read out by Orcaflash """
#       Round to closest "divisable by 4" value.
        t1 = time.time()
        print('cropping camera' + str(self.curr_cam_ind))
        self.cameras[self.curr_cam_ind].setPropertyValue('subarray_vpos', 0)
        self.cameras[self.curr_cam_ind].setPropertyValue('subarray_hpos', 0)
        self.cameras[self.curr_cam_ind].setPropertyValue('subarray_vsize', 2048)
        self.cameras[self.curr_cam_ind].setPropertyValue('subarray_hsize', 2048)

 
        vpos = int(4*np.ceil(vpos/4))
        hpos = int(4*np.ceil(hpos/4))
        vsize = int(min(2048 - vpos, 4*np.ceil(vsize/4)))
        hsize = int(min(2048 - hpos, 128*np.ceil(hsize/128))) # The v3 camera seems to only be able to take multiples of 128 in this dimension.
        
        
        self.cameras[self.curr_cam_ind].setPropertyValue('subarray_vsize', vsize)
        self.cameras[self.curr_cam_ind].setPropertyValue('subarray_hsize', hsize)
        self.cameras[self.curr_cam_ind].setPropertyValue('subarray_vpos', vpos)
        self.cameras[self.curr_cam_ind].setPropertyValue('subarray_hpos', hpos)
        
        self.frameStart = (hpos, vpos) # This should be the only place where self.frameStart is changed
        self.shapes[self.curr_cam_ind] = (hsize, vsize)     # Only place self.shapes is changed
        print('time after beginning of cropOrca= ', time.time())
        print('orca has been cropped to: ', vpos, hpos, vsize, hsize)

    def adjustFrame(self):
        """ Method to change the area of the sensor to be used and adjust the
        image widget accordingly. It needs a previous change in self.shape
        and self.frameStart)
        """

        binning = self.binPar.value()

        self.changeParameter(lambda: self.cropOrca(binning*self.X0par.value(), binning*self.Y0par.value(), binning*self.Widthpar.value(), self.Heightpar.value()))
        
        self.updateTimings()
        self.recWidget.filesizeupdate()
        self.ROI.hide()

    def updateFrame(self):
        """ Method to change the image frame size and position in the sensor
        """
        print('Update frame called')
        frameParam = self.tree.p.param('Image frame')
        if frameParam.param('Mode').value() == 'Custom':
            self.X0par.setWritable(True)
            self.Y0par.setWritable(True)
            self.Widthpar.setWritable(True)
            self.Heightpar.setWritable(True)

#            if not(self.customFrameLoaded):
#            ROIsize = (int(0.2 * self.vb.viewRect().width()), int(0.2 * self.vb.viewRect().height()))
            ROIsize = (int(0.2 * self.vb.viewRect().height()), int(0.2 * self.vb.viewRect().height()))
            ROIcenter = (int(self.vb.viewRect().center().x()), int(self.vb.viewRect().center().y()))
            ROIpos = (ROIcenter[0] - 0.5*ROIsize[0], ROIcenter[1] - 0.5*ROIsize[1])
            
#            try:
            self.ROI.setPos(ROIpos)
            self.ROI.setSize(ROIsize)
            self.ROI.show()
#            except:
#                self.ROI = guitools.ROI(ROIsize, self.vb, ROIpos,
#                                        handlePos=(1, 0), handleCenter=(0, 1),
#scaleSnap=True, translateSnap=True)
                
            self.ROIchanged()
            
        else:
            self.X0par.setWritable(False)
            self.Y0par.setWritable(False)
            self.Widthpar.setWritable(False)
            self.Heightpar.setWritable(False)

            
            if frameParam.param('Mode').value() == 'Full Widefield':
                print('Full widefield')
                self.X0par.setValue(650)
                self.Y0par.setValue(650)
                self.Widthpar.setValue(800)
                self.Heightpar.setValue(800)
                self.adjustFrame()

                self.ROI.hide()

            elif frameParam.param('Mode').value() == 'Full chip':
                print('Full chip')
                self.X0par.setValue(0)
                self.Y0par.setValue(0)
                self.Widthpar.setValue(2048)
                self.Heightpar.setValue(2048)
                self.adjustFrame()

                self.ROI.hide()

            elif frameParam.param('Mode').value() == 'Microlenses v2':
                print('Full chip')
                self.X0par.setValue(622)
                self.Y0par.setValue(697)
                self.Widthpar.setValue(635)
                self.Heightpar.setValue(635)
                self.adjustFrame()

                self.ROI.hide()
                
            elif frameParam.param('Mode').value() == 'Microlenses v3':
                print('Full chip')
                self.X0par.setValue(923)
                self.Y0par.setValue(728)
                self.Widthpar.setValue(735)
                self.Heightpar.setValue(735)
                self.adjustFrame()

                self.ROI.hide()
                
            elif frameParam.param('Mode').value() == 'Fast ROI v2':
                print('Full chip')
                self.X0par.setValue(750)
                self.Y0par.setValue(1010)
                self.Widthpar.setValue(600)
                self.Heightpar.setValue(25)
                self.adjustFrame()

                self.ROI.hide()
                
            elif frameParam.param('Mode').value() == 'Fast ROI v3':
                print('Full chip')
                self.X0par.setValue(750) #1010
                self.Y0par.setValue(1010)
                self.Widthpar.setValue(600)
                self.Heightpar.setValue(75)
                self.adjustFrame()

                self.ROI.hide()
                
                
            elif frameParam.param('Mode').value() == 'Minimal line':
                print('Full chip')
                self.X0par.setValue(0)
                self.Y0par.setValue(1020)
                self.Widthpar.setValue(2048)
                self.Heightpar.setValue(8)
                self.adjustFrame()

                self.ROI.hide()




#        else:
#            pass
#            side = int(frameParam.param('Mode').value().split('x')[0])
#            self.shape = (side, side)
#            start = int(0.5*(self.andor.detector_shape[0] - side) + 1)
#            self.frameStart = (start, start)
#
#            self.changeParameter(self.adjustFrame)
##            self.applyParam.disable()

    def ROIchanged(self):

        self.X0par.setValue(self.frameStart[0] + int(self.ROI.pos()[0]))
        self.Y0par.setValue(self.frameStart[1] + int(self.ROI.pos()[1]))

        self.Widthpar.setValue(int(self.ROI.size()[0])) # [0] is Width
        self.Heightpar.setValue(int(self.ROI.size()[1])) # [1] is Height
        
        
    def AbortROI(self):
        
        self.ROI.hide()
        
        self.X0par.setValue(self.frameStart[0])
        self.Y0par.setValue(self.frameStart[1])

        self.Widthpar.setValue(self.shapes[self.curr_cam_ind][0]) # [0] is Width
        self.Heightpar.setValue(self.shapes[self.curr_cam_ind][1]) # [1] is Height    

    def updateTimings(self):
        """ Update the real exposition and accumulation times in the parameter
        tree.
        """
#        timings = self.orcaflash.getPropertyValue('exposure_time') 
#        self.t_exp_real, self.t_acc_real, self.t_kin_real = timings
        self.RealExpPar.setValue(self.orcaflash.getPropertyValue('exposure_time')[0])
        self.FrameInt.setValue(self.orcaflash.getPropertyValue('internal_frame_interval')[0])
        self.ReadoutPar.setValue(self.orcaflash.getPropertyValue('timing_readout_time')[0])
        self.EffFRPar.setValue(self.orcaflash.getPropertyValue('internal_frame_rate')[0])
#        RealExpPar.setValue(self.orcaflash.getPropertyValue('exposure_time')[0])
#        RealAccPar.setValue(self.orcaflash.getPropertyValue('accumulation_time')[0])
#        EffFRPar.setValue(1 / self.orcaflash.getPropertyValue('accumulation_time')[0])

    # This is the function triggered by the liveview shortcut
    def liveviewKey(self):

        if self.liveviewButton.isChecked():
            self.liveviewStop()
            self.liveviewButton.setChecked(False)

        else:
            self.liveviewStart(True)
            self.liveviewButton.setChecked(True)

    # This is the function triggered by pressing the liveview button
    def liveview(self):
        """ Image live view when not recording
        """
        if self.liveviewButton.isChecked():
            self.liveviewStart()

        else:
            self.liveviewStop()
            
# Threading below  is done in this way since making LVThread a QThread resulted in QTimer
# not functioning in the thread. Image is now also saved as latest_image in 
# TormentaGUI class since setting image in GUI from thread resultet in 
# issues when interacting with the viewbox from GUI. Maybe due to 
# simultaious manipulation of viewbox from GUI and thread. 

    def liveviewStart(self):

#        self.orcaflash.startAcquisition()
#        time.sleep(0.3)
#        time.sleep(np.max((5 * self.t_exp_real.magnitude, 1)))

        self.updateFrame()
        self.vb.scene().sigMouseMoved.connect(self.mouseMoved)
        self.recWidget.readyToRecord = True
        
        self.lvworkers[self.curr_cam_ind] = LVWorker(self, self.curr_cam_ind, self.cameras[self.curr_cam_ind])
        self.lvthreads[self.curr_cam_ind] = QtCore.QThread()
        self.lvworkers[self.curr_cam_ind].moveToThread(self.lvthreads[self.curr_cam_ind])
        self.lvthreads[self.curr_cam_ind].started.connect(self.lvworkers[self.curr_cam_ind].run)
        self.lvthreads[self.curr_cam_ind].start()
        self.viewtimers[self.curr_cam_ind].start(30)
            
        self.liveviewRun()


    def liveviewStop(self):
        

        self.lvworkers[self.curr_cam_ind].stop()
        self.lvthreads[self.curr_cam_ind].terminate()
        # Turn off camera, close shutter
            
        self.viewtimers[self.curr_cam_ind].stop()
        self.recWidget.readyToRecord = False

        self.img.setImage(np.zeros(self.shapes[self.curr_cam_ind]), autoLevels=False)
        self.liveviewPause()
            


    def liveviewRun(self):
#       

        self.lvworkers[self.curr_cam_ind].reset() # Needed if parameter is changed during liveview since that causes camera to start writing to buffer place zero again.      
        self.cameras[self.curr_cam_ind].startAcquisition()
        self.liveviewrunning[self.curr_cam_ind] = True
    
    def liveviewPause(self):
        
        self.cameras[self.curr_cam_ind].stopAcquisition()
        self.liveviewrunning[self.curr_cam_ind] = False

    def updateView(self):
        """ Image update while in Liveview mode
        """
#        print('In update view')
        self.img.setImage(self.latest_images[self.curr_cam_ind], autoLevels=False, autoDownsample = False) 
        
        if self.alignmentON == True:
            if self.alignmentCheck.isChecked(): 
                self.vb.addItem(self.alignmentLine)
            else:
                self.vb.removeItem(self.alignmentLine)
            
    def alignmentToolAux(self):
        self.angle = np.float(self.angleEdit.text())
        return self.alignmentToolMaker(self.angle) 
        
    def alignmentToolMaker(self, angle):

        # alignmentLine
        try:
            self.vb.removeItem(self.alignmentLine) 
        except:
            pass
        
        pen = pg.mkPen(color=(255, 255, 0), width=0.5,
                             style=QtCore.Qt.SolidLine, antialias=True)
        self.alignmentLine = pg.InfiniteLine(pen=pen, angle=angle, movable=True)
        self.alignmentON = True
        
    def resolftRec(self):
        self.trigsourceparam.setValue('External "frame-trigger"')
        self.recWidget.untilSTOPbtn.setChecked(True)
        self.recWidget.untilStop()
        self.recWidget.recButton.setChecked(True)
        self.recWidget.startRecording()
        self.laserWidgets.DigCtrl.DigitalControlButton.setChecked(True)
        self.laserWidgets.DigCtrl.GlobalDigitalMod()


    def fpsMath(self):
        now = ptime.time()
        dt = now - self.lastTime
        self.lastTime = now
        if self.fps is None:
            self.fps = 1.0/dt
        else:
            s = np.clip(dt * 3., 0, 1)
            self.fps = self.fps * (1 - s) + (1.0/dt) * s
        self.fpsBox.setText('{} fps'.format(int(self.fps)))

    def closeEvent(self, *args, **kwargs):

        # Stop running threads
        self.viewtimer[0].stop()
        self.viewtimer[1].stop()

#        self.stabilizer.timer.stop()
#        self.stabilizerThread.terminate()
        try:
            self.lvthreads[0].terminate()
            self.lvthreads[1].terminate()
        except:
            pass
            
        # Turn off camera, close shutter and flipper
#        if self.andor.status != 'Camera is idle, waiting for instructions.':
#            self.andor.abort_acquisition()
#        self.andor.shutter(0, 2, 0, 0, 0)
        self.cameras[0].shutdown()
        self.cameras[1].shutdown()
        self.daq.flipper = True
#        if self.signalWidget.running:
#            self.signalWidget.StartStop()

        self.nidaq.reset()        
        self.laserWidgets.closeEvent(*args, **kwargs)
        self.ZalignWidget.closeEvent(*args, **kwargs)
        self.RotalignWidget.closeEvent(*args, **kwargs)        
        self.scanWidget.closeEvent(*args, **kwargs)
#        self.focusWidget.closeEvent(*args, **kwargs)
#        self.signalWidget.closeEvent(*args, **kwargs)

        super().closeEvent(*args, **kwargs)
