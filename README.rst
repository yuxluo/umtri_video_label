
UMTRI Image Annotation Tool
========

.. image:: https://img.shields.io/pypi/v/labelimg.svg
        :target: https://pypi.python.org/pypi/labelimg

.. image:: https://img.shields.io/travis/tzutalin/labelImg.svg
        :target: https://travis-ci.org/tzutalin/labelImg

.. image:: /resources/icons/full_logo.png
    :align: center


UMTRI Video Annotation Tool is adapted from the UMTRI Image Annotation Tool and is being developed and maintained by Shaun Luo. Special thanks to Tzutalin for his initial work. 

The UMTRI VAT is written in Python and uses PyQt5 for its GUI. It allows users to define a behavior at track the object across frames.
Annotations are saved as XML files in PASCAL VOC format, the format used
by `ImageNet <http://www.image-net.org/>`__.  Besides, it also supports YOLO format.

.. image:: /demo/demo1.png
    :align: center

`Video Demo
<http://umtri.org/file/umtri_label_demo.mp4>`_

`Quick Start Guide
<http://umtri.org/file/v0.1.pdf>`_

ATTENTION
------------------
Only Linux(Ubuntu, Debian, Deepin) and macOS are officially supported at this moment. Binaries for macOS and Windows is scheduled to be released at a later date. 


Configuration
------------------
The UMTRI Image Annotation Tool requires two components to work properly -- a server and a client.

The client retrieves data sets hosted on the server and sends the labels back during submit

The Server
~~~~~~~~~~~~~~~~~
• The server hosts the data sets to be labeled. Server infomation is entered during the client's startup. 

• The server must support SSH and SCP. 

• The server must contain a file called 'predefined_classes.txt' at the root directory. This text file contains predefined labels that the client will fetch. 

• The server must also contain three folders 'labeled', 'unlabeled' and 'labels'.

• The .zip files of the data sets are placed in the unlabeled folder. 

• The .zip files must be a folder of the same name when inflated and contains supported image files (jpg, jpeg, png） within this inflated folders.


The Client
~~~~~~~~~~~~~~~~~
• Clone this repo.
.. code:: shell

    git clone https://github.com/yuxluo/umtri_label.git

• Install prerequisites (including pip3, pyqt5, pyqt5-dev-tools, lxml, paramiko, scp. This action may require root privilege)
.. code:: shell

    ./install.sh
    
• or this if you are using a mac
.. code:: shell

    ./install_macOS.sh
    
• make and run 
.. code:: shell

    ./run.sh

Usage
-----

1. Build and launch using the instructions above
2. Enter your access code and server information. Ask the project instructor if you are not sure
3. Click 'Retrieve'
4. Click 'Play'
5. Create New Behavior
6. Right click the behavior to give it a name, a start frame and a ending frame
7. Add one or more bounding boxes to the behavior (or not)
8. Click 'Submit'

The annotation will be saved automatically when you click next or sumbit

You can refer to the below hotkeys to speed up your workflow.


Hotkeys
~~~~~~~

+------------+--------------------------------------------+
| ?         | Skip ahead ten frames                      |
+------------+--------------------------------------------+
| ?         | Rewind ten frames                          |
+------------+--------------------------------------------+
| Ctrl + s   | Save                                       |
+------------+--------------------------------------------+
| Ctrl + d   | Copy the current label and rect box        |
+------------+--------------------------------------------+
| Space      | Flag the current image as verified         |
+------------+--------------------------------------------+
| w          | Create a rect box                          |
+------------+--------------------------------------------+
| d          | Next image                                 |
+------------+--------------------------------------------+
| a          | Previous image                             |
+------------+--------------------------------------------+
| del        | Delete the selected rect box               |
+------------+--------------------------------------------+
| Ctrl++     | Zoom in                                    |
+------------+--------------------------------------------+
| Ctrl--     | Zoom out                                   |
+------------+--------------------------------------------+
| ↑→↓←       | Keyboard arrows to move selected rect box  |
+------------+--------------------------------------------+



License
~~~~~~~
`Free software: MIT license <https://github.com/tzutalin/labelImg/blob/master/LICENSE>`_

Citation: Tzutalin. LabelImg. Git code (2015). https://github.com/tzutalin/labelImg

Changelog
-----
Alpha 0.1
~~~~~~~
• This ReadMe page
• Dynamic Play/Pause button
• Play the images as a video in the background thread
• Draggable slider to fast forward and backward 
• Sync slider with 'Play' and double click in fileList

Alpha 0.2
~~~~~~~
• Bookmark function
• Variable speed playback

Alpha 0.3
~~~~~~~
• Create behavior
• Add start, end and bounding boxes
• Save, load & reconstruct

Future Features
~~~~~~~
• ?


Known Bugs
~~~~~~~
• ?