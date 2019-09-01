#!/usr/bin/env python
# -*- coding: utf-8 -*-
import codecs
import distutils.spawn
import os.path
import platform
import re
import sys
import subprocess
import time
import paramiko
import threading
from copy import deepcopy
from scp import SCPClient

from functools import partial
from collections import defaultdict

try:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *
except ImportError:
    # needed for py3+qt4
    # Ref:
    # http://pyqt.sourceforge.net/Docs/PyQt4/incompatible_apis.html
    # http://stackoverflow.com/questions/21217399/pyqt4-qtcore-qvariant-object-instead-of-a-string
    if sys.version_info.major >= 3:
        import sip
        sip.setapi('QVariant', 2)
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *

from libs.resources import *
from libs.constants import *
from libs.utils import *
from libs.settings import Settings
from libs.shape import Shape, DEFAULT_LINE_COLOR, DEFAULT_FILL_COLOR
from libs.stringBundle import StringBundle
from libs.canvas import Canvas
from libs.zoomWidget import ZoomWidget
from libs.labelDialog import LabelDialog
from libs.colorDialog import ColorDialog
from libs.labelFile import LabelFile, LabelFileError
from libs.toolBar import ToolBar
from libs.pascal_voc_io import PascalVocReader
from libs.pascal_voc_io import XML_EXT
from libs.yolo_io import YoloReader
from libs.yolo_io import TXT_EXT
from libs.ustr import ustr
from libs.hashableQListWidgetItem import HashableQListWidgetItem
from libs.hashableQListWidgetItem import HashableQListtWidgetItem

__appname__ = 'UMTRI Image Annotation Tool'
HOST = 'umtri.org'
USERNAME = 'test'
PASSWORD = 'testest'
CREATEING_HIERARCHY = False
PARENT_ID = -99
GLOBAL_ID = 0
PARENT_ITEM = HashableQListWidgetItem()
PLAYING = False
SLEEP_TIME = 0.05
CREATE_MODE = 1


class WindowMixin(object):

    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            addActions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName(u'%sToolBar' % title)
        # toolbar.setOrientation(Qt.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if actions:
            addActions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar


class MainWindow(QMainWindow, WindowMixin):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = list(range(3))

    def __init__(self, defaultFilename=None, defaultPrefdefClassFile=None, defaultSaveDir=None):
        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)
        # self.init_prompt()
        # Load setting in the main thread
        self.settings = Settings()
        self.settings.load()
        settings = self.settings

        # Load string bundle for i18n
        self.stringBundle = StringBundle.getBundle()
        getStr = lambda strId: self.stringBundle.getString(strId)

        # Save as Pascal voc xml
        self.defaultSaveDir = defaultSaveDir
        self.usingPascalVocFormat = True
        self.usingYoloFormat = False

        # For loading all image under a directory
        self.mImgList = []
        self.dirname = None
        self.labelHist = []
        self.lastOpenDir = None

        # Whether we need to save or not.
        self.dirty = False

        self.wen_jian_min = None
        os.chdir(os.path.dirname(os.path.realpath(__file__)))
        os.system('mkdir data')
        self.lu_jing = os.path.dirname(os.path.realpath(__file__)) + '/data/'
        

        self._noSelectionSlot = False
        self._beginner = True
        self.screencastViewer = self.getAvailableScreencastViewer()
        self.screencast = "https://youtu.be/p0nR2YsCY_U"

        # Load predefined classes to the list
        self.loadPredefinedClasses(defaultPrefdefClassFile)

        # Main widgets and related state.
        self.labelDialog = LabelDialog(parent=self, listItem=self.labelHist)

        self.itemsToShapes = {}
        self.shapesToItems = {}
        self.bookmark_to_filepath = {}
        self.itemsToBehaviors = {}
        self.behaviorsToItems = {}
        self.prevLabelText = ''

        listLayout = QVBoxLayout()
        listLayout.setContentsMargins(0, 0, 0, 0)

        # Create a widget for using default label
        self.useDefaultLabelCheckbox = QCheckBox(getStr('useDefaultLabel'))
        self.useDefaultLabelCheckbox.setChecked(False)
        self.defaultLabelTextLine = QLineEdit()
        useDefaultLabelQHBoxLayout = QHBoxLayout()
        useDefaultLabelQHBoxLayout.addWidget(self.useDefaultLabelCheckbox)
        useDefaultLabelQHBoxLayout.addWidget(self.defaultLabelTextLine)
        useDefaultLabelContainer = QWidget()
        useDefaultLabelContainer.setLayout(useDefaultLabelQHBoxLayout)

        # Create a widget for edit and diffc button
        self.diffcButton = QCheckBox(getStr('useDifficult'))
        self.diffcButton.setChecked(False)
        self.diffcButton.stateChanged.connect(self.btnstate)
        self.editButton = QToolButton()
        self.editButton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # Add some of widgets to listLayout
        # listLayout.addWidget(self.editButton)
        # listLayout.addWidget(self.diffcButton)
        listLayout.addWidget(useDefaultLabelContainer)

        # Create and add a widget for showing current label items
        # self.labelList = QListWidget()
        self.labelList = QTreeWidget()
        self.labelList.setColumnCount(3)
        self.labelList.setHeaderLabels(['Name', 'Start', 'End'])
        labelListContainer = QWidget()
        labelListContainer.setLayout(listLayout)
        self.labelList.itemActivated.connect(self.labelSelectionChanged)
        self.labelList.itemSelectionChanged.connect(self.labelSelectionChanged)
        self.labelList.itemDoubleClicked.connect(self.labelItemDoubleClicked)
        # Connect to itemChanged to detect checkbox changes.
        self.labelList.itemChanged.connect(self.labelItemChanged)
        listLayout.addWidget(self.labelList)

        self.dock = QDockWidget(getStr('boxLabelText'), self)
        self.dock.setObjectName(getStr('labels'))
        self.dock.setWidget(labelListContainer)

        # Bookmark stuff
        self.bookmarkListWidget = QListWidget()
        self.bookmarkListWidget.itemDoubleClicked.connect(self.bookmarkitemDoubleClicked)
        bookmark_layout = QVBoxLayout()
        bookmark_layout.setContentsMargins(0, 0, 0, 0)
        bookmark_layout.addWidget(self.bookmarkListWidget)
        bookmark_container = QWidget()
        bookmark_container.setLayout(bookmark_layout)
        self.bookmark_dock = QDockWidget('Bookmarks', self)
        self.bookmark_dock.setObjectName('Bookmark Widget')
        self.bookmark_dock.setWidget(bookmark_container)

        self.fileListWidget = QListWidget()
        self.fileListWidget.itemDoubleClicked.connect(self.fileitemDoubleClicked)
        filelistLayout = QVBoxLayout()
        filelistLayout.setContentsMargins(0, 0, 0, 0)
        filelistLayout.addWidget(self.fileListWidget)
        fileListContainer = QWidget()
        fileListContainer.setLayout(filelistLayout)
        self.filedock = QDockWidget(getStr('fileList'), self)
        self.filedock.setObjectName(getStr('files'))
        self.filedock.setWidget(fileListContainer)

        self.zoomWidget = ZoomWidget()
        self.colorDialog = ColorDialog(parent=self)

        self.canvas = Canvas(parent=self)
        self.canvas.zoomRequest.connect(self.zoomRequest)
        self.canvas.setDrawingShapeToSquare(settings.get(SETTING_DRAW_SQUARE, False))

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        self.scrollBars = {
            Qt.Vertical: scroll.verticalScrollBar(),
            Qt.Horizontal: scroll.horizontalScrollBar()
        }
        self.scrollArea = scroll
        self.canvas.scrollRequest.connect(self.scrollRequest)

        self.canvas.newShape.connect(self.newShape)
        self.canvas.shapeMoved.connect(self.setDirty)
        self.canvas.selectionChanged.connect(self.shapeSelectionChanged)
        self.canvas.drawingPolygon.connect(self.toggleDrawingSensitive)

        self.bookmarkListWidget.itemSelectionChanged.connect(self.bookmarkSelectionChanged)

        self.setCentralWidget(scroll)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.filedock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.bookmark_dock)
        self.dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.filedock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.bookmark_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)

        # self.dockFeatures = QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetFloatable
        # self.dock.setFeatures(self.dock.features() ^ self.dockFeatures)

        # Actions
        action = partial(newAction, self)
        quit = action(getStr('quit'), self.close,
                      'Ctrl+Q', 'quit', getStr('quitApp'))

        open = action(getStr('openFile'), self.openFile,
                      'Ctrl+O', 'open', getStr('openFileDetail'))

        retrieve_data = action(getStr('getData'), self.getData, 'Ctrl+r', 'download', getStr('retrieveDetail'))

        bookmark = action(getStr('bookmark'), self.add_to_bookmark, 'b', 'bookmark', getStr('bookmarkDetail'))

        set_sleep_time = action(getStr('setSleep'), self.adjust_sleep_time, 'Ctrl+p', 'clock', getStr('setSleepDetail'))

        submit_label = action(getStr('submitLabel'), self.submitLabel, 'Ctrl+M', 'upload', getStr('submitDetail'))

        opendir = action(getStr('openDir'), self.openDirDialog,
                         'Ctrl+u', 'open', getStr('openDir'))

        changeSavedir = action(getStr('changeSaveDir'), self.changeSavedirDialog,
                               'Ctrl+5', 'open', getStr('changeSavedAnnotationDir'))

        openAnnotation = action(getStr('openAnnotation'), self.openAnnotationDialog,
                                'Ctrl+Shift+O', 'open', getStr('openAnnotationDetail'))

        openNextImg = action(getStr('nextImg'), self.openNextImg,
                             'd', 'next', getStr('nextImgDetail'))

        openPrevImg = action(getStr('prevImg'), self.openPrevImg,
                             'a', 'prev', getStr('prevImgDetail'))

        openNext10Img = action(getStr('openNext10'), self.openNext10Img,
                             'right', 'next', getStr('openNext10'))

        openPrev10Img = action(getStr('openPrev10'), self.openPrev10Img,
                             'left', 'prev', getStr('openPrev10'))

        play_pause = action(getStr('play'), self.play_pause,
                             'space', 'play_icon', getStr('playDetail'))


        # verify = action(getStr('verifyImg'), self.createShape,
        #                 'space', 'verify', getStr('verifyImgDetail'))

        save = action(getStr('save'), self.saveFile,
                      'Ctrl+s', 'save', getStr('saveDetail'), enabled=False)

        save_format = action('&XML', self.change_format,
                      'Ctrl+', 'format_voc', getStr('changeSaveFormat'), enabled=True)

        saveAs = action(getStr('saveAs'), self.saveFileAs,
                        'Ctrl+Shift+S', 'save-as', getStr('saveAsDetail'), enabled=False)

        close = action(getStr('closeCur'), self.closeFile, 'Ctrl+W', 'close', getStr('closeCurDetail'))

        resetAll = action(getStr('resetAll'), self.resetAll, None, 'resetall', getStr('resetAllDetail'))

        color1 = action(getStr('boxLineColor'), self.chooseColor1,
                        'Ctrl+L', 'color_line', getStr('boxLineColorDetail'))

        createMode = action(getStr('crtBox'), self.setCreateMode,
                            'w', 'new', getStr('crtBoxDetail'), enabled=False)
        editMode = action('&Edit\nRectBox', self.setEditMode,
                          'Ctrl+J', 'edit', u'Move and edit Boxs', enabled=False)

        create = action('New Behavior', self.addBehavior,
                        'w', 'new', getStr('crtBoxDetail'), enabled=False)

        switch = action('Switch Mode', self.createShape,
                        'w', 'switch', 'Switch the Creation Mode', enabled=False)

        delete = action(getStr('delBox'), self.deleteSelectedShape,
                        'Delete', 'delete', getStr('delBoxDetail'), enabled=False)
        delete_bookmark = action('Delete Bookmark', self.deleteBookmark,
                        'Delete', 'delete', 'Remove This Bookmark', enabled=False)              
        copy = action(getStr('dupBox'), self.copySelectedShape,
                      'Ctrl+D', 'copy', getStr('dupBoxDetail'),
                      enabled=False)

        advancedMode = action(getStr('advancedMode'), self.toggleAdvancedMode,
                              'Ctrl+Shift+A', 'expert', getStr('advancedModeDetail'),
                              checkable=True)

        hideAll = action('&Hide\nRectBox', partial(self.togglePolygons, False),
                         'Ctrl+H', 'hide', getStr('hideAllBoxDetail'),
                         enabled=False)
        showAll = action('&Show\nRectBox', partial(self.togglePolygons, True),
                         'Ctrl+A', 'hide', getStr('showAllBoxDetail'),
                         enabled=False)

        help = action(getStr('tutorial'), self.showTutorialDialog, None, 'help', getStr('tutorialDetail'))
        showInfo = action(getStr('info'), self.showInfoDialog, None, 'help', getStr('info'))

        zoom = QWidgetAction(self)
        zoom.setDefaultWidget(self.zoomWidget)
        self.zoomWidget.setWhatsThis(
            u"Zoom in or out of the image. Also accessible with"
            " %s and %s from the canvas." % (fmtShortcut("Ctrl+[-+]"),
                                             fmtShortcut("Ctrl+Wheel")))
        self.zoomWidget.setEnabled(False)

        zoomIn = action(getStr('zoomin'), partial(self.addZoom, 10),
                        'Ctrl++', 'zoom-in', getStr('zoominDetail'), enabled=False)
        zoomOut = action(getStr('zoomout'), partial(self.addZoom, -10),
                         'Ctrl+-', 'zoom-out', getStr('zoomoutDetail'), enabled=False)
        zoomOrg = action(getStr('originalsize'), partial(self.setZoom, 100),
                         'Ctrl+=', 'zoom', getStr('originalsizeDetail'), enabled=False)
        fitWindow = action(getStr('fitWin'), self.setFitWindow,
                           'Ctrl+F', 'fit-window', getStr('fitWinDetail'),
                           checkable=True, enabled=False)
        fitWidth = action(getStr('fitWidth'), self.setFitWidth,
                          'Ctrl+Shift+F', 'fit-width', getStr('fitWidthDetail'),
                          checkable=True, enabled=False)
        # Group zoom controls into a list for easier toggling.
        zoomActions = (self.zoomWidget, zoomIn, zoomOut,
                       zoomOrg, fitWindow, fitWidth)
        self.zoomMode = self.MANUAL_ZOOM
        self.scalers = {
            self.FIT_WINDOW: self.scaleFitWindow,
            self.FIT_WIDTH: self.scaleFitWidth,
            # Set to one to scale to 100% when loading files.
            self.MANUAL_ZOOM: lambda: 1,
        }

        edit_bookmark = action('Edit Bookmark', self.editBookmark, 'Ctrl+E', 'edit', 'Change the name of bookmark', enabled=False)

        edit = action(getStr('editLabel'), self.editLabel,
                      'Ctrl+E', 'edit', getStr('editLabelDetail'),
                      enabled=False)

        add_part = action(getStr('addPart'), self.addPart,
                      'Ctrl+A', 'add', getStr('addPartDetail'),
                      enabled=False)

        set_start = action(getStr('setStart'), self.setStart,
                'Ctrl+A', 'start', getStr('setStartDetail'),
                enabled=False)

        set_end = action(getStr('setEnd'), self.setEnd,
                'Ctrl+A', 'end', getStr('setEndDetail'),
                enabled=False)


        self.editButton.setDefaultAction(edit)

        shapeLineColor = action(getStr('shapeLineColor'), self.chshapeLineColor,
                                icon='color_line', tip=getStr('shapeLineColorDetail'),
                                enabled=False)
        shapeFillColor = action(getStr('shapeFillColor'), self.chshapeFillColor,
                                icon='color', tip=getStr('shapeFillColorDetail'),
                                enabled=False)

        labels = self.dock.toggleViewAction()
        labels.setText(getStr('showHide'))
        labels.setShortcut('Ctrl+Shift+L')

        # Lavel list context menu.
        labelMenu = QMenu()
        addActions(labelMenu, (edit, delete, add_part, set_start, set_end))

        bookmarkMenu = QMenu()
        addActions(bookmarkMenu, (edit_bookmark, delete_bookmark))


        self.labelList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.labelList.customContextMenuRequested.connect(
            self.popLabelListMenu)

        self.bookmarkListWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.bookmarkListWidget.customContextMenuRequested.connect(
            self.popBookmarkListMenu)

        # Draw squares/rectangles
        self.drawSquaresOption = QAction('Draw Squares', self)
        self.drawSquaresOption.setShortcut('Ctrl+Shift+R')
        self.drawSquaresOption.setCheckable(True)
        self.drawSquaresOption.setChecked(settings.get(SETTING_DRAW_SQUARE, False))
        self.drawSquaresOption.triggered.connect(self.toogleDrawSquare)

        # Store actions for further handling.
        self.actions = struct(save=save, play_pause=play_pause, save_format=save_format, saveAs=saveAs, open=open, close=close, resetAll = resetAll,
                              lineColor=color1, create=create, delete=delete, add_part=add_part, set_start=set_start, set_end=set_end, edit=edit, copy=copy, edit_bookmark=edit_bookmark,
                              createMode=createMode, editMode=editMode, advancedMode=advancedMode, delete_bookmark=delete_bookmark,
                              shapeLineColor=shapeLineColor, shapeFillColor=shapeFillColor, switch=switch,
                              zoom=zoom, zoomIn=zoomIn, zoomOut=zoomOut, zoomOrg=zoomOrg,
                              fitWindow=fitWindow, fitWidth=fitWidth,
                              zoomActions=zoomActions,
                              fileMenuActions=(
                                  open, opendir, save, saveAs, close, resetAll, quit),
                              beginner=(), advanced=(),
                              editMenu=(edit, copy, delete,
                                        None, color1, self.drawSquaresOption),
                              beginnerContext=(create, edit, copy, delete),
                              advancedContext=(createMode, editMode, edit, copy,
                                               delete, shapeLineColor, shapeFillColor),
                              onLoadActive=(
                                  close, create, createMode, editMode),
                              onShapesPresent=(saveAs, hideAll, showAll))

        self.menus = struct(
            file=self.menu('&File'),
            edit=self.menu('&Edit'),
            view=self.menu('&View'),
            help=self.menu('&Help'),
            recentFiles=QMenu('Open &Recent'),
            labelList=labelMenu,
            bookmarkListWidget=bookmarkMenu)

        # Auto saving : Enable auto saving if pressing next
        self.autoSaving = QAction(getStr('autoSaveMode'), self)
        self.autoSaving.setCheckable(True)
        self.autoSaving.setChecked(settings.get(SETTING_AUTO_SAVE, False))
        # Sync single class mode from PR#106
        self.singleClassMode = QAction(getStr('singleClsMode'), self)
        self.singleClassMode.setShortcut("Ctrl+Shift+S")
        self.singleClassMode.setCheckable(True)
        self.singleClassMode.setChecked(settings.get(SETTING_SINGLE_CLASS, False))
        self.lastLabel = None
        # Add option to enable/disable labels being displayed at the top of bounding boxes
        self.displayLabelOption = QAction(getStr('displayLabel'), self)
        self.displayLabelOption.setShortcut("Ctrl+Shift+P")
        self.displayLabelOption.setCheckable(True)
        self.displayLabelOption.setChecked(settings.get(SETTING_PAINT_LABEL, False))
        self.displayLabelOption.triggered.connect(self.togglePaintLabelsOption)

        addActions(self.menus.file,
                   (open, opendir, changeSavedir, openAnnotation, self.menus.recentFiles, save, save_format, saveAs, close, resetAll, quit))
        addActions(self.menus.help, (help, showInfo))
        addActions(self.menus.view, (
            set_sleep_time,
            openNext10Img,
            openPrev10Img,
            self.autoSaving,
            self.singleClassMode,
            self.displayLabelOption,
            labels, advancedMode, None,
            hideAll, showAll, None,
            zoomIn, zoomOut, zoomOrg, None,
            fitWindow, fitWidth))

        self.menus.file.aboutToShow.connect(self.updateFileMenu)

        # Custom context menu for the canvas widget:
        addActions(self.canvas.menus[0], self.actions.beginnerContext)
        addActions(self.canvas.menus[1], (
            action('&Copy here', self.copyShape),
            action('&Move here', self.moveShape)))

        self.tools = self.toolbar('Tools')
        self.actions.beginner = (
            retrieve_data, save, submit_label, openNextImg, openPrevImg, play_pause, set_sleep_time, bookmark, save_format, None, create, switch, delete, None,
            zoomIn, zoom, zoomOut, fitWindow, fitWidth)

        self.actions.switch.setEnabled(True)

        self.actions.advanced = (
            open, opendir, changeSavedir, play_pause, save, save_format, None,
            createMode, editMode, None,
            hideAll, showAll)

        self.statusBar().showMessage('%s started.' % __appname__)
        self.statusBar().show()

        # Application state.
        self.image = QImage()
        self.filePath = ustr(defaultFilename)
        self.recentFiles = []
        self.maxRecent = 7
        self.lineColor = None
        self.fillColor = None
        self.zoom_level = 100
        self.fit_window = False
        # Add Chris
        self.difficult = False

        ## Fix the compatible issue for qt4 and qt5. Convert the QStringList to python list
        if settings.get(SETTING_RECENT_FILES):
            if have_qstring():
                recentFileQStringList = settings.get(SETTING_RECENT_FILES)
                self.recentFiles = [ustr(i) for i in recentFileQStringList]
            else:
                self.recentFiles = recentFileQStringList = settings.get(SETTING_RECENT_FILES)

        size = settings.get(SETTING_WIN_SIZE, QSize(600, 500))
        position = QPoint(0, 0)
        saved_position = settings.get(SETTING_WIN_POSE, position)
        # Fix the multiple monitors issue
        for i in range(QApplication.desktop().screenCount()):
            if QApplication.desktop().availableGeometry(i).contains(saved_position):
                position = saved_position
                break
        self.resize(size)
        self.move(position)
        saveDir = ustr(settings.get(SETTING_SAVE_DIR, None))
        self.lastOpenDir = ustr(settings.get(SETTING_LAST_OPEN_DIR, None))
        if self.defaultSaveDir is None and saveDir is not None and os.path.exists(saveDir):
            self.defaultSaveDir = saveDir
            self.statusBar().showMessage('%s started. Annotation will be saved to %s' %
                                         (__appname__, self.defaultSaveDir))
            self.statusBar().show()

        self.restoreState(settings.get(SETTING_WIN_STATE, QByteArray()))
        Shape.line_color = self.lineColor = QColor(settings.get(SETTING_LINE_COLOR, DEFAULT_LINE_COLOR))
        Shape.fill_color = self.fillColor = QColor(settings.get(SETTING_FILL_COLOR, DEFAULT_FILL_COLOR))
        self.canvas.setDrawingColor(self.lineColor)
        # Add chris
        Shape.difficult = self.difficult

        def xbool(x):
            if isinstance(x, QVariant):
                return x.toBool()
            return bool(x)

        if xbool(settings.get(SETTING_ADVANCE_MODE, False)):
            self.actions.advancedMode.setChecked(True)
            self.toggleAdvancedMode()

        # Populate the File menu dynamically.
        self.updateFileMenu()

        # Since loading the file may take some time, make sure it runs in the background.
        if self.filePath and os.path.isdir(self.filePath):
            self.queueEvent(partial(self.importDirImages, self.filePath or ""))
        elif self.filePath:
            self.queueEvent(partial(self.loadFile, self.filePath or ""))

        # Callbacks:
        self.zoomWidget.valueChanged.connect(self.paintCanvas)

        self.populateModeActions()

        # Display cursor coordinates at the right of status bar
        self.labelCoordinates = QLabel('')
        self.statusBar().addPermanentWidget(self.labelCoordinates)

        # Open Dir if deafult file
        if self.filePath and os.path.isdir(self.filePath):
            self.openDirDialog(dirpath=self.filePath)

    def init_prompt(self):
        # alert_box = QMessageBox.question(self, '⚠⚠ 免責聲明 :::: DISCLAIMER ⚠⚠', "The UMTRI Image Annotation Tool may or may not be stealing intellectual properties for the Chinese government.\n\nClick 'Yes' to continue at your own risk:", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        alert_box = QMessageBox.question(self, '⚠⚠ 免責聲明 :::: DISCLAIMER ⚠⚠', "The UMTRI Image Annotation Tool is provided by Shaun Luo as is and with all faults. Shaun Luo makes no representations or warranties of any kind concerning the stability, security, lack of viruses, inaccuracies, typographical errors, or other harmful components of this software. You are solely responsible for the protection of your OS and backup of your data. Shaun Luo will not be liable for any damages you may suffer in connection with using, modifying, or distributing this software.\n\nClick 'Yes' to contiune at your own risk:", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if alert_box == QMessageBox.Yes:
            print('Yes clicked.')
        else:
            print('No clicked.')
            exit(0)

        while(1):
            secret, ok = QInputDialog.getText(self, 'Authentication', 'Please enter your access code below:' )
            if ok: 
                if secret == "GoBlue2901":
                    break
            else:
                exit(0)
    
        server_info, ok = QInputDialog.getText(self, 'Server Info', 'Please enter the server info below (ip username password) \nleave blank to use default' )
        if ok: 
            if server_info == "":
                pass
            else:
                global HOST
                global USERNAME
                global PASSWORD
                HOST = server_info.split()[0]
                USERNAME = server_info.split()[1]
                PASSWORD = server_info.split()[2]


    def addPart(self):
        global CREATEING_HIERARCHY
        CREATEING_HIERARCHY=True
        # get the parent item 
        if not self.canvas.editing():
            return
        item = self.currentItem()
        if not item:
            return
        global PARENT_ITEM
        PARENT_ITEM = item
        self.createShape()

    def labelItemDoubleClicked(self):
        selected_item = self.labelList.currentItem()
        if selected_item in self.itemsToBehaviors:
            if selected_item.text(1) is None or selected_item.text(1) == "": 
                self.editLabel()
            else:
                behavior = self.itemsToBehaviors[selected_item]
                filepath = self.filePath.split('/')
                filepath[-1] = behavior.start_frame
                currIndex = self.mImgList.index(ustr('/'.join(filepath)))
                self.update_slider_value(currIndex)

    def setStart(self):
        selected_item = self.labelList.currentItem()
        if selected_item is not None:
            selected_behavior = self.itemsToBehaviors[selected_item]
            filename = self.filePath.split('/')[-1]
            frame_num = filename.split('-')[-1].split('.')[0]
            selected_behavior.start_frame = filename
            selected_item.setText(1, frame_num)
            self.setDirty()
            print('setting dirty')

    def setEnd(self):
        selected_item = self.labelList.currentItem()
        if selected_item is not None:
            selected_behavior = self.itemsToBehaviors[selected_item]
            filename = self.filePath.split('/')[-1]
            frame_num = filename.split('-')[-1].split('.')[0]
            selected_behavior.end_frame = filename
            selected_item.setText(2, frame_num)
            self.setDirty()

    def createShape(self):
        assert self.beginner()
        self.canvas.setEditing(False)
        self.actions.create.setEnabled(False)

    def progress(self, filename, size, sent):
        progress = float(sent)/float(size) * 100
        if progress != 100:
            self.progressBar.setValue(progress)

    def continuous_add(self):
        # while CREATEING_HIERARCHY:
        #     self.createShape()
            # self.openNextImg()
        return

    def run(self):
        while PLAYING:
            self.openNextImg()
            self.update_slider_value(self.slider.value() + 1)
            time.sleep(SLEEP_TIME)
            qApp.processEvents()

    def switch_mode(self):
        print("switch mode clicked")

    def adjust_sleep_time(self):
        global SLEEP_TIME
        dialogue = QDialog()

        b1 = QPushButton("0.25x",dialogue)
        b1.move(20,0)
        b2 = QPushButton("0.5x",dialogue)
        b2.move(120,0)
        b3 = QPushButton("1.0x",dialogue)
        b3.move(20,30)
        b4 = QPushButton("2.0x",dialogue)
        b4.move(120,30)
        b5 = QPushButton("4.0x",dialogue)
        b5.move(20,60)
        b6 = QPushButton("8.0x",dialogue)
        b6.move(120,60)

        buttons = [b1,b2,b3,b4,b5,b6]
        speeds = [0.05/0.25, 0.05/0.5, 0.05, 0.05/2, 0.05/4, 0.05/8]

        for i in range(len(buttons)):
            if SLEEP_TIME == speeds[i]:
                buttons[i].setDefault(True)
                break

        def b1_clicked(self):
            global SLEEP_TIME
            SLEEP_TIME = 0.05/0.25
            dialogue.done(0)

        def b2_clicked(self):
            global SLEEP_TIME
            SLEEP_TIME = 0.05/0.5
            dialogue.done(0)

        def b3_clicked(self):
            global SLEEP_TIME
            SLEEP_TIME = 0.05
            dialogue.done(0)

        def b4_clicked(self):
            global SLEEP_TIME
            SLEEP_TIME = 0.05/2
            dialogue.done(0)

        def b5_clicked(self):
            global SLEEP_TIME
            SLEEP_TIME = 0.05/4
            dialogue.done(0)

        def b6_clicked(self):
            global SLEEP_TIME
            SLEEP_TIME = 0.05/8
            dialogue.done(0)


        b1.clicked.connect(b1_clicked)
        b2.clicked.connect(b2_clicked)
        b3.clicked.connect(b3_clicked)
        b4.clicked.connect(b4_clicked)
        b5.clicked.connect(b5_clicked)
        b6.clicked.connect(b6_clicked)

        dialogue.setWindowTitle("Set Speed")
        dialogue.setWindowModality(Qt.ApplicationModal)
        dialogue.exec_()

    def start(self):
        global PLAYING
        PLAYING = True
        self.run()


    def pause(self):
        global PLAYING
        PLAYING = False

    def play_pause(self):
        if PLAYING:
            self.actions.play_pause.setText("Play")
            self.actions.play_pause.setIcon(newIcon("play_icon"))
            self.pause()
            
        else:
            self.actions.play_pause.setText("Pause")
            self.actions.play_pause.setIcon(newIcon("pause_icon"))
            self.start()

    def add_to_bookmark(self):
        if self.filePath is not None:
            frame_num = self.filePath.split('/')[-1].split('-')[-1].split('.')[0]
        else:
            return 

        bookmark_name = self.labelDialog.popUp(text=frame_num)

        if bookmark_name == "" or bookmark_name == None:
            return 

        if bookmark_name not in self.labelHist:
            self.labelHist.append(bookmark_name)

        item = HashableQListtWidgetItem()
        item.setText(bookmark_name)
        self.bookmarkListWidget.addItem(item)
        self.bookmark_to_filepath[item] = self.filePath



    def getData(self):
        self.progressBar = QProgressBar()
        self.progressBar.setValue(0)
        self.statusBar().addPermanentWidget(self.progressBar)
        self.statusBar().showMessage("Retrieving data set...")
        self.statusBar().show()

        #connect to the data server through ssh 
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(HOST, username=USERNAME, password=PASSWORD)
        except:
            alert_box = QMessageBox.warning(self, 'Request Incomplete', "This action was not performed correctly because: \n\nThe file server appears to be offline.", QMessageBox.Ok)
            return

        # get the name of the first file
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command('cd unlabeled/; ls | head -n 1') 

        if ssh_stderr.readlines() != []:
            alert_box = QMessageBox.warning(self, 'Request Incomplete', "This action was not performed correctly because: \n\nThe server has not been set up correctly.", QMessageBox.Ok)
            return

        pending_retrieval = str()
        try:
            for letter in ssh_stdout.readlines()[0]:
                if (letter != '\n'):
                    pending_retrieval += letter
                else:
                    break
        except:
            alert_box = QMessageBox.warning(self, 'Request Incomplete', "This action was not performed correctly because: \n\nThe unlabeled folder appears to be empty on the server.", QMessageBox.Ok)
            return

        # move top file to labeled folder
        mov_command = 'mv unlabeled/'+pending_retrieval+' labeled/'
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(mov_command)
        if ssh_stderr.readlines() != []:
            alert_box = QMessageBox.warning(self, 'Request Incomplete', "This action was not performed correctly because: \n\nThe server has not been set up correctly.", QMessageBox.Ok)
            return

        # get data and label from server through scp
        data_folder_path = self.lu_jing

        try:
            scp = SCPClient(ssh.get_transport(), progress = self.progress)
            scp.get('~/predefined_classes.txt', data_folder_path)
            scp.get('~/labeled/' + pending_retrieval, data_folder_path)
        except:
            alert_box = QMessageBox.warning(self, 'Request Incomplete', "This action was not performed correctly because: \n\nThe server has not been set up correctly.", QMessageBox.Ok)
            return
        
        # unpack pictures and remove zip
        os.system('unzip ' + data_folder_path + pending_retrieval + ' -d ' + data_folder_path)
        
        #open the folder in umtri_label
        self.wen_jian_min = str()
        for letter in pending_retrieval:
            if letter == '.':
                break
            self.wen_jian_min += letter
        self.loadPredefinedClasses(data_folder_path + 'predefined_classes.txt')
        self.importDirImages(data_folder_path + self.wen_jian_min)

        ssh.close()
        self.statusBar().removeWidget(self.progressBar)



    def submitLabel(self):
        if self.dirty is True:
            self.force_save()

        # remove all images from the folder
        data_folder_path = self.lu_jing
        try:
            if self.wen_jian_min == None:
                self.wen_jian_min = self.filePath.split('/')[-2]
            os.chdir(data_folder_path + self.wen_jian_min)
        except:
            return
        os.system('rm *.jpeg')
        os.system('rm *.jpg')
        os.system('rm *.png')

        #compress all label files
        os.chdir('..')
        zip_command = 'zip ' + self.wen_jian_min + '_labels.zip -r ' + self.wen_jian_min
        os.system(zip_command)

        #do upload stuff here
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(HOST, username=USERNAME, password=PASSWORD)
        except:
            alert_box = QMessageBox.warning(self, 'Request Incomplete', "This action was not performed correctly because: \n\nThe file server appears to be offline.", QMessageBox.Ok)
            return

        try:
            scp = SCPClient(ssh.get_transport())
            scp.put(self.wen_jian_min + '_labels.zip', remote_path = '~/labels')
        except:
            alert_box = QMessageBox.warning(self, 'Request Incomplete', "This action was not performed correctly because: \n\nThe server has not been set up correctly.", QMessageBox.Ok)
            return

        # clean up
        # It's your boi Fat Man and Little Boy coming to clean up your rubbish
        os.system('rm -rf *')
        os.system('rm *')

        result = QMessageBox.information(self, 'Request Completed', "Your labels have been submitted successfully", QMessageBox.Ok)


        self.statusBar().removeWidget(self.slider)

        

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.canvas.setDrawingShapeToSquare(False)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Control:
            # Draw rectangle if Ctrl is pressed
            self.canvas.setDrawingShapeToSquare(True)

    ## Support Functions ##
    def set_format(self, save_format):
        if save_format == FORMAT_PASCALVOC:
            self.actions.save_format.setText(FORMAT_PASCALVOC)
            self.actions.save_format.setIcon(newIcon("format_voc"))
            self.usingPascalVocFormat = True
            self.usingYoloFormat = False
            LabelFile.suffix = XML_EXT

        elif save_format == FORMAT_YOLO:
            self.actions.save_format.setText(FORMAT_YOLO)
            self.actions.save_format.setIcon(newIcon("format_yolo"))
            self.usingPascalVocFormat = False
            self.usingYoloFormat = True
            LabelFile.suffix = TXT_EXT

    def change_format(self):
        if self.usingPascalVocFormat: self.set_format(FORMAT_YOLO)
        elif self.usingYoloFormat: self.set_format(FORMAT_PASCALVOC)

    def noShapes(self):
        return not self.itemsToShapes

    def toggleAdvancedMode(self, value=True):
        self._beginner = not value
        self.canvas.setEditing(True)
        self.populateModeActions()
        self.editButton.setVisible(not value)
        if value:
            self.actions.createMode.setEnabled(True)
            self.actions.editMode.setEnabled(False)
            self.dock.setFeatures(self.dock.features() | self.dockFeatures)
        else:
            self.dock.setFeatures(self.dock.features() ^ self.dockFeatures)

    def populateModeActions(self):
        if self.beginner():
            tool, menu = self.actions.beginner, self.actions.beginnerContext
        else:
            tool, menu = self.actions.advanced, self.actions.advancedContext
        self.tools.clear()
        addActions(self.tools, tool)
        self.canvas.menus[0].clear()
        addActions(self.canvas.menus[0], menu)
        self.menus.edit.clear()
        actions = (self.actions.create,) if self.beginner()\
            else (self.actions.createMode, self.actions.editMode)
        addActions(self.menus.edit, actions + self.actions.editMenu)

    def setBeginner(self):
        self.tools.clear()
        addActions(self.tools, self.actions.beginner)

    def setAdvanced(self):
        self.tools.clear()
        addActions(self.tools, self.actions.advanced)

    def setDirty(self):
        self.dirty = True
        self.actions.save.setEnabled(True)

    def setClean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.create.setEnabled(True)

    def toggleActions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        for action in self.actions.onLoadActive:
            action.setEnabled(value)

    def queueEvent(self, function):
        QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def resetState(self):
        self.itemsToShapes.clear()
        self.shapesToItems.clear()
        self.labelList.clear()
        self.filePath = None
        self.imageData = None
        self.labelFile = None
        self.canvas.resetState()
        self.labelCoordinates.clear()

    def currentItem(self):
        items = self.labelList.selectedItems()
        if items:
            return items[0]
        return None

    def addRecentFile(self, filePath):
        if filePath in self.recentFiles:
            self.recentFiles.remove(filePath)
        elif len(self.recentFiles) >= self.maxRecent:
            self.recentFiles.pop()
        self.recentFiles.insert(0, filePath)

    def beginner(self):
        return self._beginner

    def advanced(self):
        return not self.beginner()

    def getAvailableScreencastViewer(self):
        osName = platform.system()

        if osName == 'Windows':
            return ['C:\\Program Files\\Internet Explorer\\iexplore.exe']
        elif osName == 'Linux':
            return ['xdg-open']
        elif osName == 'Darwin':
            return ['open']

    ## Callbacks ##
    def showTutorialDialog(self):
        subprocess.Popen(self.screencastViewer + [self.screencast])

    def showInfoDialog(self):
        msg = u'Name:{0} \nApp Version:{1} \n{2} '.format(__appname__, __version__, sys.version_info)
        QMessageBox.information(self, u'Information', msg)

    def old_create_shape(self):
        assert self.beginner()
        self.canvas.setEditing(False)
        self.actions.create.setEnabled(False)

    def toggleDrawingSensitive(self, drawing=True):
        """In the middle of drawing, toggling between modes should be disabled."""
        self.actions.editMode.setEnabled(not drawing)
        if not drawing and self.beginner():
            # Cancel creation.
            print('Cancel creation.')
            global CREATEING_HIERARCHY
            CREATEING_HIERARCHY = False
            self.canvas.setEditing(True)
            self.canvas.restoreCursor()
            self.actions.create.setEnabled(True)

    def toggleDrawMode(self, edit=True):
        self.canvas.setEditing(edit)
        self.actions.createMode.setEnabled(edit)
        self.actions.editMode.setEnabled(not edit)

    def setCreateMode(self):
        assert self.advanced()
        self.toggleDrawMode(False)

    def setEditMode(self):
        assert self.advanced()
        self.toggleDrawMode(True)
        self.labelSelectionChanged()

    def updateFileMenu(self):
        currFilePath = self.filePath

        def exists(filename):
            return os.path.exists(filename)
        menu = self.menus.recentFiles
        menu.clear()
        files = [f for f in self.recentFiles if f !=
                 currFilePath and exists(f)]
        for i, f in enumerate(files):
            icon = newIcon('labels')
            action = QAction(
                icon, '&%d %s' % (i + 1, QFileInfo(f).fileName()), self)
            action.triggered.connect(partial(self.loadRecent, f))
            menu.addAction(action)

    def popLabelListMenu(self, point):
        self.menus.labelList.exec_(self.labelList.mapToGlobal(point))

    def popBookmarkListMenu(self, point):
        self.menus.bookmarkListWidget.exec_(self.bookmarkListWidget.mapToGlobal(point))

    def editLabel(self):
        print('edit clicked')
        if not self.canvas.editing():
            return
        item = self.labelList.currentItem()
        # item = self.currentItem()
        if not item:
            return
        text = self.labelDialog.popUp(item.text(0))
        if text is not None:
            item.setText(0, text)

            item.setBackground(0, generateColorByText(text))
            item.setBackground(1, generateColorByText(text))
            item.setBackground(2, generateColorByText(text))
            self.setDirty()


    def editBookmark(self):
        item = self.bookmarkListWidget.selectedItems()[0]
        new_name = self.labelDialog.popUp(text=item.text())
        if new_name == "" or new_name == None:
            return
        item.setText(new_name)
        
    def deleteBookmark(self):
        item = self.bookmarkListWidget.selectedItems()[0]
        if item in self.bookmark_to_filepath:
            del self.bookmark_to_filepath[item]
        self.bookmarkListWidget.takeItem(self.bookmarkListWidget.row(item))

    # Tzutalin 20160906 : Add file list and dock to move faster
    def fileitemDoubleClicked(self, item=None):
        currIndex = self.mImgList.index(ustr(item.text()))
        if currIndex < len(self.mImgList):
            filename = self.mImgList[currIndex]
            if filename:
                self.update_slider_value(currIndex)

    # Add chris

    def bookmarkitemDoubleClicked(self):
        item = self.bookmarkListWidget.selectedItems()[0]
        if item is not None:
            currIndex = self.mImgList.index(ustr(self.bookmark_to_filepath[item]))
            self.update_slider_value(currIndex)

    def load_file_by_index(self, index):
        if index < len(self.mImgList):
            filename = self.mImgList[index]
            if filename:
                self.loadFile(filename)

    def btnstate(self, item= None):
        """ Function to handle difficult examples
        Update on each object """
        if not self.canvas.editing():
            return

        item = self.currentItem()
        if not item: # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count()-1)

        difficult = self.diffcButton.isChecked()

        try:
            shape = self.itemsToShapes[item]
        except:
            pass
        # Checked and Update
        try:
            if difficult != shape.difficult:
                shape.difficult = difficult
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    # React to canvas signals.
    def shapeSelectionChanged(self, selected=False):
        if self._noSelectionSlot:
            self._noSelectionSlot = False
        else:
            shape = self.canvas.selectedShape
            behavior = self.canvas.selectedBehavior
            if shape:
                self.shapesToItems[shape].setSelected(True)
            elif behavior:
                self.behaviorsToItems[behavior].setSelected(True)
            else:
                self.labelList.clearSelection()

        self.actions.set_start.setEnabled(selected)
        self.actions.set_end.setEnabled(selected)
        self.actions.add_part.setEnabled(selected)
        self.actions.edit.setEnabled(selected)
        self.actions.delete.setEnabled(selected)
        self.actions.copy.setEnabled(selected)
        self.actions.shapeLineColor.setEnabled(selected)
        self.actions.shapeFillColor.setEnabled(selected)

    def bookmarkSelectionChanged(self):
        if len(self.bookmarkListWidget.selectedItems()) == 0:
            self.actions.edit_bookmark.setEnabled(False)
            self.actions.delete_bookmark.setEnabled(False)
        elif len(self.bookmarkListWidget.selectedItems()) > 1:
            QMessageBox.information(self, 'Tell me how you triggered this', "親，一次只能更改一個書籤喔", QMessageBox.Ok)
            self.actions.edit_bookmark.setEnabled(False)
            self.actions.delete_bookmark.setEnabled(False)
        else:
            self.actions.edit_bookmark.setEnabled(True)
            self.actions.delete_bookmark.setEnabled(True)

    def addBehavior(self, behavior):
        global GLOBAL_ID

        # Get behavior name from user 
        self.labelDialog = LabelDialog(text="Enter object label", parent=self, listItem=self.labelHist)
        behavior_name = self.labelDialog.popUp(text=self.prevLabelText)
        if behavior_name not in self.labelHist:
                self.labelHist.append(behavior_name)
        if (behavior_name is None or behavior_name == ""):
            return
        behavior = self.canvas.new_behavior(behavior_name, GLOBAL_ID, generateColorByText(behavior_name))
        GLOBAL_ID += 1

        item = HashableQListWidgetItem()
        item.setText(0, behavior.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked)
        item.setBackground(0, behavior.parent_color)
        item.setBackground(1, behavior.parent_color)
        item.setBackground(2, behavior.parent_color)


        self.itemsToBehaviors[item] = behavior
        self.behaviorsToItems[behavior] = item
        self.labelList.addTopLevelItem(item)

        self.setDirty()
        # for action in self.actions.onShapesPresent:
        #     action.setEnabled(True)

    def addLabel(self, behavior, type="behavior"):
        if type == "shape":
            frame_number = behavior.filename.split('-')[-1].split('.')[0]
            item = HashableQListWidgetItem()
            item.setText(1, frame_number)
            item.setText(0, 'frame:')
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked)
            item.setBackground(0, behavior.line_color)
            item.setBackground(1, behavior.line_color)
            item.setBackground(2, behavior.line_color)

            self.itemsToShapes[item] = behavior
            self.shapesToItems[behavior] = item
            PARENT_ITEM.addChild(item)
            PARENT_ITEM.setExpanded(True)
            global CREATEING_HIERARCHY 
            CREATEING_HIERARCHY = False

            for action in self.actions.onShapesPresent:
                action.setEnabled(True)

            return

        item = HashableQListWidgetItem()
        item.setText(0, behavior.label)
        item.setText(1, behavior.start_frame.split('-')[-1].split('.')[0])
        item.setText(2, behavior.end_frame.split('-')[-1].split('.')[0])
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked)
        item.setBackground(0, behavior.parent_color)
        item.setBackground(1, behavior.parent_color)
        item.setBackground(2, behavior.parent_color)

        self.itemsToBehaviors[item] = behavior
        self.behaviorsToItems[behavior] = item
        self.labelList.addTopLevelItem(item)
        

    def addLabel_old(self, shape):
        shape.paintLabel = self.displayLabelOption.isChecked()
        global CREATEING_HIERARCHY
        item = HashableQListWidgetItem()
        item.setText(0, shape.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked)
        item.setBackground(0, generateColorByText(shape.label))
        self.itemsToShapes[item] = shape
        self.shapesToItems[shape] = item

        if CREATEING_HIERARCHY:
            PARENT_ITEM.addChild(item)
            PARENT_ITEM.setExpanded(True)
        else:
            self.labelList.addTopLevelItem(item)
        CREATEING_HIERARCHY = False

        for action in self.actions.onShapesPresent:
            action.setEnabled(True)



    def remLabel(self, shape):
        if shape is None:
            # print('rm empty label')
            return

        if shape in self.shapesToItems:
            item = self.shapesToItems[shape]
            while item.childCount() != 0:
                child = item.child(0)
                self.remLabel(self.itemsToShapes[child])

            del self.shapesToItems[shape]
            del self.itemsToShapes[item]

        else:
            item = self.behaviorsToItems[shape]
            print("delete bounding boxes")
            del self.behaviorsToItems[shape]
            del self.itemsToBehaviors[item]

        
        self.canvas.delete_shape(shape)


        root = self.labelList.invisibleRootItem()
        (item.parent() or root).removeChild(item)

    def search_tree(self, id):
        root = self.labelList.invisibleRootItem()
        for child_index in range(root.childCount()):
            if self.recursive_search_tree(root.child(child_index), id) == 0:
                break
    
    def recursive_search_tree(self, parent, id):
        if self.itemsToShapes[parent].self_id == id:
            global PARENT_ITEM 
            PARENT_ITEM = parent
            return 0
        else:
            for child_index in range(parent.childCount()):
                if self.recursive_search_tree(parent.child(child_index), id) == 0:
                    return 0

        return -1


    def loadLabels(self, behaviors):
        b = []

        for behavior_name, behavior_id, starting_frame, ending_frame in behaviors:
            behavior = self.canvas.new_behavior(behavior_name, GLOBAL_ID, generateColorByText(behavior_name))
            behavior.start_frame = starting_frame
            behavior.end_frame = ending_frame
            b.append(behavior)
            self.addLabel(behavior)
        
        self.canvas.loadBehaviors(b)

    def loadLabels_old(self, shapes):
        s = []
        for label, points, parents, children, self_id, line_color, fill_color, difficult in shapes:
            shape = Shape(label=label)
            if parents != []:
                # find the parent node and add this as child
                parent_id = parents[0]
                global CREATEING_HIERARCHY
                CREATEING_HIERARCHY = True
                self.search_tree(parent_id)

            
            for x, y in points:

                # Ensure the labels are within the bounds of the image. If not, fix them.
                x, y, snapped = self.canvas.snapPointToCanvas(x, y)
                if snapped:
                    self.setDirty()

                shape.addPoint(QPointF(x, y))
            shape.difficult = difficult
            shape.self_id = self_id
            shape.parents = parents
            shape.children = children
            shape.close()
            s.append(shape)

            if line_color:
                shape.line_color = QColor(*line_color)
            else:
                shape.line_color = generateColorByText(label)

            if fill_color:
                shape.fill_color = QColor(*fill_color)
            else:
                shape.fill_color = generateColorByText(label)

            self.addLabel(shape)

        self.canvas.loadShapes(s)

    def saveLabels(self, annotationFilePath):
        annotationFilePath = ustr(annotationFilePath)
        if self.labelFile is None:
            self.labelFile = LabelFile()
            self.labelFile.verified = self.canvas.verified

        def format_shape(s):
            return dict(label=s.label,
                        line_color=s.line_color.getRgb(),
                        fill_color=s.fill_color.getRgb(),
                        points=[(p.x(), p.y()) for p in s.points],
                       # add chris
                        difficult = s.difficult,
                        parents = s.parents,
                        self_id = s.self_id,
                        children = s.children)

        shapes = [format_shape(shape) for shape in self.canvas.shapes]
        # Can add differrent annotation formats here
        try:
            if self.usingPascalVocFormat is True:
                if annotationFilePath[-4:].lower() != ".xml":
                    annotationFilePath += XML_EXT
                self.labelFile.saveBehavior(self.canvas.behaviors, self.filePath)
                self.labelFile.savePascalVocFormat(annotationFilePath, shapes, self.filePath, self.imageData,
                                                   self.lineColor.getRgb(), self.fillColor.getRgb())
            elif self.usingYoloFormat is True:
                if annotationFilePath[-4:].lower() != ".txt":
                    annotationFilePath += TXT_EXT
                self.labelFile.saveYoloFormat(annotationFilePath, shapes, self.filePath, self.imageData, self.labelHist,
                                                   self.lineColor.getRgb(), self.fillColor.getRgb())
            else:
                self.labelFile.save(annotationFilePath, shapes, self.filePath, self.imageData,
                                    self.lineColor.getRgb(), self.fillColor.getRgb())
            print('Image:{0} -> Annotation:{1}'.format(self.filePath, annotationFilePath))
            return True
        except LabelFileError as e:
            self.errorMessage(u'Error saving label data', u'<b>%s</b>' % e)
            return False

    def copySelectedShape(self):
        self.addLabel(self.canvas.copySelectedShape())
        # fix copy and delete
        self.shapeSelectionChanged(True)

    def labelSelectionChanged(self):
        # item = self.currentItem()
        item = self.labelList.currentItem()
        if item and self.canvas.editing():
            self._noSelectionSlot = True
            if item in self.itemsToShapes:
                self.canvas.selectShape(self.itemsToShapes[item])
            else: 
                self.canvas.selectBehavior(self.itemsToBehaviors[item])


    def labelItemChanged(self, item):
        if item in self.itemsToShapes:
            shape = self.itemsToShapes[item]
            label = item.text(0)
            if label != shape.label:
                shape.label = item.text(0)
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState(0) == Qt.Checked)
                for i in range(item.childCount()):
                    self.recursive_change_visibility(item.child(i), item.checkState(0))
        
        else:
            behavior = self.itemsToBehaviors[item]
            label = item.text(0)
            if label != behavior.label:
                behavior.label = label
                behavior.parent_color = generateColorByText(label)
                self.setDirty()
            else:  # User probably changed item visibility
                for i in range(item.childCount()):
                    self.recursive_change_visibility(item.child(i), item.checkState(0))


    def recursive_change_visibility(self, item, parent_check_state):
        item.setCheckState(0, parent_check_state)
        shape = self.itemsToShapes[item]
        self.canvas.setShapeVisible(shape, parent_check_state)
        for i in range(item.childCount()):
            self.recursive_change_visibility(item.child(i), parent_check_state)

    # Callback functions:
    def newShape(self):

        filename = self.filePath.split('/')[-1]
        frame_num = filename.split('-')[-1].split('.')[0]
        text = frame_num 

        if text is not None:
            self.prevLabelText = text
            generate_color = self.itemsToBehaviors[PARENT_ITEM].parent_color
            shape = self.canvas.setLastLabel(text, generate_color, generate_color, filename)
            parent_behavior = self.itemsToBehaviors[PARENT_ITEM]
            parent_behavior.shapes.append(shape)

            self.addLabel(shape, "shape")
            if self.beginner():  # Switch to edit mode.
                self.canvas.setEditing(True)
                self.actions.create.setEnabled(True)
            else:
                self.actions.editMode.setEnabled(True)
            self.setDirty()

        else:
            # self.canvas.undoLastLine()
            self.canvas.resetAllLines()

    def scrollRequest(self, delta, orientation):
        units = - delta / (8 * 15)
        bar = self.scrollBars[orientation]
        bar.setValue(bar.value() + bar.singleStep() * units)

    def setZoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.MANUAL_ZOOM
        self.zoomWidget.setValue(value)

    def addZoom(self, increment=10):
        self.setZoom(self.zoomWidget.value() + increment)

    def zoomRequest(self, delta):
        # get the current scrollbar positions
        # calculate the percentages ~ coordinates
        h_bar = self.scrollBars[Qt.Horizontal]
        v_bar = self.scrollBars[Qt.Vertical]

        # get the current maximum, to know the difference after zooming
        h_bar_max = h_bar.maximum()
        v_bar_max = v_bar.maximum()

        # get the cursor position and canvas size
        # calculate the desired movement from 0 to 1
        # where 0 = move left
        #       1 = move right
        # up and down analogous
        cursor = QCursor()
        pos = cursor.pos()
        relative_pos = QWidget.mapFromGlobal(self, pos)

        cursor_x = relative_pos.x()
        cursor_y = relative_pos.y()

        w = self.scrollArea.width()
        h = self.scrollArea.height()

        # the scaling from 0 to 1 has some padding
        # you don't have to hit the very leftmost pixel for a maximum-left movement
        margin = 0.1
        move_x = (cursor_x - margin * w) / (w - 2 * margin * w)
        move_y = (cursor_y - margin * h) / (h - 2 * margin * h)

        # clamp the values from 0 to 1
        move_x = min(max(move_x, 0), 1)
        move_y = min(max(move_y, 0), 1)

        # zoom in
        units = delta / (8 * 15)
        scale = 10
        self.addZoom(scale * units)

        # get the difference in scrollbar values
        # this is how far we can move
        d_h_bar_max = h_bar.maximum() - h_bar_max
        d_v_bar_max = v_bar.maximum() - v_bar_max

        # get the new scrollbar values
        new_h_bar_value = h_bar.value() + move_x * d_h_bar_max
        new_v_bar_value = v_bar.value() + move_y * d_v_bar_max

        h_bar.setValue(new_h_bar_value)
        v_bar.setValue(new_v_bar_value)

    def setFitWindow(self, value=True):
        if value:
            self.actions.fitWidth.setChecked(False)
        self.zoomMode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjustScale()

    def setFitWidth(self, value=True):
        if value:
            self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjustScale()

    def togglePolygons(self, value):
        for item, shape in self.itemsToShapes.items():
            item.setCheckState(Qt.Checked if value else Qt.Unchecked)

    def loadFile(self, filePath=None):
        """Load the specified file, or the last opened file if None."""
        if self.dirty == True:
            self.force_save()
        # self.resetState()
        self.canvas.setEnabled(False)
        if filePath is None:
            filePath = self.settings.get(SETTING_FILENAME)

        # Make sure that filePath is a regular python string, rather than QString
        filePath = ustr(filePath)

        # Fix bug: An  index error after select a directory when open a new file.
        unicodeFilePath = ustr(filePath)
        unicodeFilePath = os.path.abspath(unicodeFilePath)
        # Tzutalin 20160906 : Add file list and dock to move faster
        # Highlight the file item
        if unicodeFilePath and self.fileListWidget.count() > 0:
            if unicodeFilePath in self.mImgList:
                index = self.mImgList.index(unicodeFilePath)
                fileWidgetItem = self.fileListWidget.item(index)
                self.fileListWidget.scrollToItem(fileWidgetItem, QAbstractItemView.PositionAtCenter)
                fileWidgetItem.setSelected(True)
            else:
                self.fileListWidget.clear()
                self.mImgList.clear()

        if unicodeFilePath and os.path.exists(unicodeFilePath):
            if LabelFile.isLabelFile(unicodeFilePath):
                try:
                    self.labelFile = LabelFile(unicodeFilePath)
                except LabelFileError as e:
                    self.errorMessage(u'Error opening file',
                                      (u"<p><b>%s</b></p>"
                                       u"<p>Make sure <i>%s</i> is a valid label file.")
                                      % (e, unicodeFilePath))
                    self.status("Error reading %s" % unicodeFilePath)
                    return False
                self.imageData = self.labelFile.imageData
                self.lineColor = QColor(*self.labelFile.lineColor)
                self.fillColor = QColor(*self.labelFile.fillColor)
                self.canvas.verified = self.labelFile.verified
            else:
                # Load image:
                # read data first and store for saving into label file.
                self.imageData = read(unicodeFilePath, None)
                self.labelFile = None
                self.canvas.verified = False

            image = QImage.fromData(self.imageData)
            if image.isNull():
                self.errorMessage(u'Error opening file',
                                  u"<p>Make sure <i>%s</i> is a valid image file." % unicodeFilePath)
                self.status("Error reading %s" % unicodeFilePath)
                return False
            self.status("Loaded %s" % os.path.basename(unicodeFilePath))
            self.image = image
            self.filePath = unicodeFilePath
            self.canvas.loadPixmap(QPixmap.fromImage(image))
            if self.labelFile:
                self.loadLabels(self.labelFile.shapes)
            self.setClean()
            self.canvas.setEnabled(True)
            self.adjustScale(initial=True)
            self.paintCanvas()
            self.addRecentFile(self.filePath)
            self.toggleActions(True)

            # Label xml file and show bound box according to its filename
            # if self.usingPascalVocFormat is True:
            if self.defaultSaveDir is not None:
                basename = os.path.basename(
                    os.path.splitext(self.filePath)[0])
                xmlPath = os.path.join(self.defaultSaveDir, basename + XML_EXT)
                txtPath = os.path.join(self.defaultSaveDir, basename + TXT_EXT)

                """Annotation file priority:
                PascalXML > YOLO
                """
                if os.path.isfile(xmlPath):
                    self.loadPascalXMLByFilename(xmlPath)
                elif os.path.isfile(txtPath):
                    self.loadYOLOTXTByFilename(txtPath)
            else:
                xmlPath = os.path.splitext(filePath)[0] + XML_EXT
                txtPath = os.path.splitext(filePath)[0] + TXT_EXT
                if os.path.isfile(xmlPath):
                    self.loadPascalXMLByFilename(xmlPath)
                elif os.path.isfile(txtPath):
                    self.loadYOLOTXTByFilename(txtPath)

            self.setWindowTitle(__appname__ + ' ' + filePath)

            # Default : select last item if there is at least one item
            # if self.labelList.count():
            #     self.labelList.setCurrentItem(self.labelList.item(self.labelList.count()-1))
            #     self.labelList.item(self.labelList.count()-1).setSelected(True)

            self.canvas.setFocus(True)
            return True
        return False

    def resizeEvent(self, event):
        if self.canvas and not self.image.isNull()\
           and self.zoomMode != self.MANUAL_ZOOM:
            self.adjustScale()
        super(MainWindow, self).resizeEvent(event)

    def paintCanvas(self):
        assert not self.image.isNull(), "cannot paint null image"
        self.canvas.scale = 0.01 * self.zoomWidget.value()
        self.canvas.adjustSize()
        self.canvas.update()

    def adjustScale(self, initial=False):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoomMode]()
        self.zoomWidget.setValue(int(100 * value))

    def scaleFitWindow(self):
        """Figure out the size of the pixmap in order to fit the main widget."""
        e = 2.0  # So that no scrollbars are generated.
        w1 = self.centralWidget().width() - e
        h1 = self.centralWidget().height() - e
        a1 = w1 / h1
        # Calculate a new scale value based on the pixmap's aspect ratio.
        w2 = self.canvas.pixmap.width() - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        a2 = w2 / h2
        return w1 / w2 if a2 >= a1 else h1 / h2

    def scaleFitWidth(self):
        # The epsilon does not seem to work too well here.
        w = self.centralWidget().width() - 2.0
        return w / self.canvas.pixmap.width()

    def closeEvent(self, event):
        if not self.mayContinue():
            event.ignore()
        settings = self.settings
        # If it loads images from dir, don't load it at the begining
        if self.dirname is None:
            settings[SETTING_FILENAME] = self.filePath if self.filePath else ''
        else:
            settings[SETTING_FILENAME] = ''

        settings[SETTING_WIN_SIZE] = self.size()
        settings[SETTING_WIN_POSE] = self.pos()
        settings[SETTING_WIN_STATE] = self.saveState()
        settings[SETTING_LINE_COLOR] = self.lineColor
        settings[SETTING_FILL_COLOR] = self.fillColor
        settings[SETTING_RECENT_FILES] = self.recentFiles
        settings[SETTING_ADVANCE_MODE] = not self._beginner
        if self.defaultSaveDir and os.path.exists(self.defaultSaveDir):
            settings[SETTING_SAVE_DIR] = ustr(self.defaultSaveDir)
        else:
            settings[SETTING_SAVE_DIR] = ''

        if self.lastOpenDir and os.path.exists(self.lastOpenDir):
            settings[SETTING_LAST_OPEN_DIR] = self.lastOpenDir
        else:
            settings[SETTING_LAST_OPEN_DIR] = ''

        settings[SETTING_AUTO_SAVE] = self.autoSaving.isChecked()
        settings[SETTING_SINGLE_CLASS] = self.singleClassMode.isChecked()
        settings[SETTING_PAINT_LABEL] = self.displayLabelOption.isChecked()
        settings[SETTING_DRAW_SQUARE] = self.drawSquaresOption.isChecked()
        settings.save()

    def loadRecent(self, filename):
        if self.mayContinue():
            self.loadFile(filename)

    def scanAllImages(self, folderPath):
        extensions = ['.%s' % fmt.data().decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()]
        images = []

        for root, dirs, files in os.walk(folderPath):
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    relativePath = os.path.join(root, file)
                    path = ustr(os.path.abspath(relativePath))
                    images.append(path)
        natural_sort(images, key=lambda x: x.lower())
        return images

    def changeSavedirDialog(self, _value=False):
        if self.defaultSaveDir is not None:
            path = ustr(self.defaultSaveDir)
        else:
            path = '.'

        dirpath = ustr(QFileDialog.getExistingDirectory(self,
                                                       '%s - Save annotations to the directory' % __appname__, path,  QFileDialog.ShowDirsOnly
                                                       | QFileDialog.DontResolveSymlinks))

        if dirpath is not None and len(dirpath) > 1:
            self.defaultSaveDir = dirpath

        self.statusBar().showMessage('%s . Annotation will be saved to %s' %
                                     ('Change saved folder', self.defaultSaveDir))
        self.statusBar().show()

    def openAnnotationDialog(self, _value=False):
        if self.filePath is None:
            self.statusBar().showMessage('Please select image first')
            self.statusBar().show()
            return

        path = os.path.dirname(ustr(self.filePath))\
            if self.filePath else '.'
        if self.usingPascalVocFormat:
            filters = "Open Annotation XML file (%s)" % ' '.join(['*.xml'])
            filename = ustr(QFileDialog.getOpenFileName(self,'%s - Choose a xml file' % __appname__, path, filters))
            if filename:
                if isinstance(filename, (tuple, list)):
                    filename = filename[0]
            self.loadPascalXMLByFilename(filename)

    def openDirDialog(self, _value=False, dirpath=None):
        if not self.mayContinue():
            return

        defaultOpenDirPath = dirpath if dirpath else '.'
        if self.lastOpenDir and os.path.exists(self.lastOpenDir):
            defaultOpenDirPath = self.lastOpenDir
        else:
            defaultOpenDirPath = os.path.dirname(self.filePath) if self.filePath else '.'

        targetDirPath = ustr(QFileDialog.getExistingDirectory(self,
                                                     '%s - Open Directory' % __appname__, defaultOpenDirPath,
                                                     QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks))
        self.importDirImages(targetDirPath)

    def importDirImages(self, dirpath):
        if not self.mayContinue() or not dirpath:
            return

        self.lastOpenDir = dirpath
        self.dirname = dirpath
        self.filePath = None
        self.fileListWidget.clear()
        self.loadPascalXMLByFilename(dirpath + "/behavior.xml")
        self.mImgList = self.scanAllImages(dirpath)
        self.openNextImg()
        for imgPath in self.mImgList:
            item = QListWidgetItem(imgPath)
            self.fileListWidget.addItem(item)
        self.init_slider()

    def init_slider(self):
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, self.fileListWidget.count() - 1)
        self.slider.valueChanged.connect(self.slider_value_changed)
        self.statusBar().addPermanentWidget(self.slider)
        self.statusBar().show()

    def slider_value_changed(self):
        if PLAYING == False:
            self.load_file_by_index(self.slider.value())

    def update_slider_value(self, new_value):

        self.slider.setValue(new_value)
        
    def verifyImg(self, _value=False):
        # Proceding next image without dialog if having any label
        if self.filePath is not None:
            try:
                self.labelFile.toggleVerify()
            except AttributeError:
                # If the labelling file does not exist yet, create if and
                # re-save it with the verified attribute.
                self.saveFile()
                if self.labelFile != None:
                    self.labelFile.toggleVerify()
                else:
                    return

            self.canvas.verified = self.labelFile.verified
            self.paintCanvas()
            self.saveFile()

    def openPrevImg(self, _value=False):
        # Proceding prev image without dialog if having any label
        if self.dirty is True:
                self.force_save()

        if not self.mayContinue():
            return

        if len(self.mImgList) <= 0:
            return

        if self.filePath is None:
            return

        currIndex = self.mImgList.index(self.filePath)
        if currIndex - 1 >= 0:
            filename = self.mImgList[currIndex - 1]
            if filename:
                self.loadFile(filename)

    def openPrev10Img(self, _value=False):
        # Proceding prev image without dialog if having any label
        if self.dirty is True:
                self.force_save()

        if not self.mayContinue():
            return

        if len(self.mImgList) <= 0:
            return

        if self.filePath is None:
            return

        currIndex = self.mImgList.index(self.filePath)
        if currIndex - 10 >= 0:
            filename = self.mImgList[currIndex - 10]
            if filename:
                self.loadFile(filename)

    def force_save(self, _value=False):
        imgFileDir = os.path.dirname(self.filePath)
        imgFileName = os.path.basename(self.filePath)
        savedFileName = os.path.splitext(imgFileName)[0]
        savedPath = os.path.join(imgFileDir, savedFileName)
        self._saveFile(savedPath)

    def openNext10Img(self, _value=False):

        if self.dirty is True:
            self.force_save()

        if not self.mayContinue():
            return

        if len(self.mImgList) <= 0:
            return

        filename = None
        if self.filePath is None:
            filename = self.mImgList[0]
        else:
            currIndex = self.mImgList.index(self.filePath)
            if currIndex + 10 < len(self.mImgList):
                filename = self.mImgList[currIndex + 10]
            else:
                result = QMessageBox.information(self, 'Request Incomplete', "This action was not performed successfully because:\n\nYou've reached the end of the data set. Click submit to upload your labels", QMessageBox.Ok)
        if filename:
            self.loadFile(filename)



    def openNextImg(self, _value=False):

        if self.dirty is True:
            self.force_save()

        if not self.mayContinue():
            return

        if len(self.mImgList) <= 0:
            return

        filename = None
        if self.filePath is None:
            filename = self.mImgList[0]
        else:
            currIndex = self.mImgList.index(self.filePath)
            if currIndex + 1 < len(self.mImgList):
                filename = self.mImgList[currIndex + 1]
            else:
                result = QMessageBox.information(self, 'Request Incomplete', "This action was not performed successfully because:\n\nYou've reached the end of the data set. Click submit to upload your labels", QMessageBox.Ok)
                global PLAYING
                PLAYING = False
        if filename:
            self.loadFile(filename)

    def openFile(self, _value=False):
        if not self.mayContinue():
            return
        path = os.path.dirname(ustr(self.filePath)) if self.filePath else '.'
        formats = ['*.%s' % fmt.data().decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()]
        filters = "Image & Label files (%s)" % ' '.join(formats + ['*%s' % LabelFile.suffix])
        filename = QFileDialog.getOpenFileName(self, '%s - Choose Image or Label file' % __appname__, path, filters)
        if filename:
            if isinstance(filename, (tuple, list)):
                filename = filename[0]
            self.loadFile(filename)

    def saveFile(self, _value=False):
        if self.defaultSaveDir is not None and len(ustr(self.defaultSaveDir)):
            if self.filePath:
                imgFileName = os.path.basename(self.filePath)
                savedFileName = os.path.splitext(imgFileName)[0]
                savedPath = os.path.join(ustr(self.defaultSaveDir), savedFileName)
                self._saveFile(savedPath)
        else:
            imgFileDir = os.path.dirname(self.filePath)
            imgFileName = os.path.basename(self.filePath)
            savedFileName = os.path.splitext(imgFileName)[0]
            savedPath = os.path.join(imgFileDir, savedFileName)
            self._saveFile(savedPath if self.labelFile
                           else self.saveFileDialog(removeExt=False))

    def saveFileAs(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        self._saveFile(self.saveFileDialog())

    def saveFileDialog(self, removeExt=True):
        caption = '%s - Choose File' % __appname__
        filters = 'File (*%s)' % LabelFile.suffix
        openDialogPath = self.currentPath()
        dlg = QFileDialog(self, caption, openDialogPath, filters)
        dlg.setDefaultSuffix(LabelFile.suffix[1:])
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        filenameWithoutExtension = os.path.splitext(self.filePath)[0]
        dlg.selectFile(filenameWithoutExtension)
        dlg.setOption(QFileDialog.DontUseNativeDialog, False)
        if dlg.exec_():
            fullFilePath = ustr(dlg.selectedFiles()[0])
            if removeExt:
                return os.path.splitext(fullFilePath)[0] # Return file path without the extension.
            else:
                return fullFilePath
        return ''

    def _saveFile(self, annotationFilePath):
        if annotationFilePath and self.saveLabels(annotationFilePath):
            self.setClean()
            self.statusBar().showMessage('Saved to  %s' % annotationFilePath)
            self.statusBar().show()

    def closeFile(self, _value=False):
        if not self.mayContinue():
            return
        self.resetState()
        self.setClean()
        self.toggleActions(False)
        self.canvas.setEnabled(False)
        self.actions.saveAs.setEnabled(False)

    def resetAll(self):
        self.settings.reset()
        self.close()
        proc = QProcess()
        proc.startDetached(os.path.abspath(__file__))

    def mayContinue(self):
        return not (self.dirty and not self.discardChangesDialog())

    def discardChangesDialog(self):
        yes, no = QMessageBox.Yes, QMessageBox.No
        msg = u'You have unsaved changes, proceed anyway?'
        return yes == QMessageBox.warning(self, u'Attention', msg, yes | no)

    def errorMessage(self, title, message):
        return QMessageBox.critical(self, title,
                                    '<p><b>%s</b></p>%s' % (title, message))

    def currentPath(self):
        return os.path.dirname(self.filePath) if self.filePath else '.'

    def chooseColor1(self):
        color = self.colorDialog.getColor(self.lineColor, u'Choose line color',
                                          default=DEFAULT_LINE_COLOR)
        if color:
            self.lineColor = color
            Shape.line_color = color
            self.canvas.setDrawingColor(color)
            self.canvas.update()
            self.setDirty()

    def deleteSelectedShape(self):
        # if len(self.canvas.selectedBehavior.shapes) != 0:
        if self.labelList.currentItem() in self.itemsToBehaviors:
            if len(self.canvas.selectedBehavior.shapes) != 0:
                alert_box = QMessageBox.question(self, '⚠⚠ ATTENTION ⚠⚠', "Removing this behavior will result in the removal of all its bounding boxes. \n\nDo you wish to continue?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if alert_box == QMessageBox.Yes:
                    pass
                else:
                    return

        self.remLabel(self.canvas.deleteSelected())
        self.setDirty()
        if self.noShapes():
            for action in self.actions.onShapesPresent:
                action.setEnabled(False)

    def chshapeLineColor(self):
        color = self.colorDialog.getColor(self.lineColor, u'Choose line color',
                                          default=DEFAULT_LINE_COLOR)
        if color:
            self.canvas.selectedShape.line_color = color
            self.canvas.update()
            self.setDirty()

    def chshapeFillColor(self):
        color = self.colorDialog.getColor(self.fillColor, u'Choose fill color',
                                          default=DEFAULT_FILL_COLOR)
        if color:
            self.canvas.selectedShape.fill_color = color
            self.canvas.update()
            self.setDirty()

    def copyShape(self):
        self.canvas.endMove(copy=True)
        self.addLabel(self.canvas.selectedShape)
        self.setDirty()

    def moveShape(self):
        self.canvas.endMove(copy=False)
        self.setDirty()

    def loadPredefinedClasses(self, predefClassesFile):
        if os.path.exists(predefClassesFile) is True:
            with codecs.open(predefClassesFile, 'r', 'utf8') as f:
                for line in f:
                    line = line.strip()
                    if self.labelHist is None:
                        self.labelHist = [line]
                    else:
                        if line not in self.labelHist:
                            self.labelHist.append(line)

    def loadPascalXMLByFilename(self, xmlPath):
        # if self.filePath is None:
        #     return
        if os.path.isfile(xmlPath) is False:
            return

        self.set_format(FORMAT_PASCALVOC)

        tVocParseReader = PascalVocReader(xmlPath)
        behaviors = tVocParseReader.getBehaviors()
        self.loadLabels(behaviors)
        self.canvas.verified = tVocParseReader.verified

    def loadYOLOTXTByFilename(self, txtPath):
        if self.filePath is None:
            return
        if os.path.isfile(txtPath) is False:
            return

        self.set_format(FORMAT_YOLO)
        tYoloParseReader = YoloReader(txtPath, self.image)
        shapes = tYoloParseReader.getShapes()
        print (shapes)
        self.loadLabels(shapes)
        self.canvas.verified = tYoloParseReader.verified

    def togglePaintLabelsOption(self):
        for shape in self.canvas.shapes:
            shape.paintLabel = self.displayLabelOption.isChecked()

    def toogleDrawSquare(self):
        self.canvas.setDrawingShapeToSquare(self.drawSquaresOption.isChecked())

def inverted(color):
    return QColor(*[255 - v for v in color.getRgb()])


def read(filename, default=None):
    try:
        with open(filename, 'rb') as f:
            return f.read()
    except:
        return default


def get_main_app(argv=[]):
    """
    Standard boilerplate Qt application code.
    Do everything but app.exec_() -- so that we can test the application in one thread
    """
    app = QApplication(argv)
    app.setApplicationName(__appname__)
    app.setWindowIcon(newIcon("logo"))
    # Tzutalin 201705+: Accept extra agruments to change predefined class file
    # Usage : labelImg.py image predefClassFile saveDir
    win = MainWindow(argv[1] if len(argv) >= 2 else None,
                     argv[2] if len(argv) >= 3 else os.path.join(
                         os.path.dirname(sys.argv[0]),
                         'data', 'predefined_classes.txt'),
                     argv[3] if len(argv) >= 4 else None)
    
    # win.setGeometry(0, 0, 1366, 768)
    win.showMaximized()
    return app, win


def main():
    '''construct main app and run it'''
    app, _win = get_main_app(sys.argv)
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main())
