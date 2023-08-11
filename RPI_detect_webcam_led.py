# Credit to:
# Author: Evan Juras
# Date: 10/2/19
# link original here : https://github.com/EdjeElectronics/TensorFlow-Lite-Object-Detection-on-Android-and-Raspberry-Pi

# Adding fps and write output to show in frame by : Kiena
# Adding led as output for each class
# Adding multithread for LED and LCD
# Only 5 class here: bus, motorcycle, truck, person, car
# LCD 16x2 output CPU and Temp of Raspberry Pi
# If you want to save video, Uncomment code below comment in "Uncomment code below to save the video"

# Import packages
import os
import argparse
import cv2
import numpy as np
import sys
import RPi.GPIO as GPIO
import importlib.util
import time
import re
import drivers
from time import sleep
from threading import Thread
import psutil
import smbus
import threading

# Define VideoStream class to handle streaming of video from webcam in separate processing thread
# Source - Adrian Rosebrock, PyImageSearch: https://www.pyimagesearch.com/2015/12/28/increasing-raspberry-pi-fps-with-python-and-opencv/
class VideoStream:
    """Camera object that controls video streaming from the Picamera"""
    def __init__(self,resolution=(640,480),framerate=30):
        # Initialize the PiCamera and the camera image stream
        self.stream = cv2.VideoCapture(0)
        ret = self.stream.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        ret = self.stream.set(3,resolution[0])
        ret = self.stream.set(4,resolution[1])
            
        # Read first frame from the stream
        (self.grabbed, self.frame) = self.stream.read()

	# Variable to control when the camera is stopped
        self.stopped = False

    def start(self):
	# Start the thread that reads frames from the video stream
        Thread(target=self.update,args=()).start()
        return self

    def update(self):
        # Keep looping indefinitely until the thread is stopped
        while True:
            # If the camera is stopped, stop the thread
            if self.stopped:
                # Close camera resources
                self.stream.release()
                return

            # Otherwise, grab the next frame from the stream
            (self.grabbed, self.frame) = self.stream.read()

    def read(self):
	# Return the most recent frame
        return self.frame

    def stop(self):
	# Indicate that the camera and thread should be stopped
        self.stopped = True

class lcd:
    def __init__(self):
        # Initialize lcd
        self.bus = smbus.SMBus(1)
        time.sleep(1)
        self.lcd = drivers.Lcd()
        # self.cpu_thread = threading.Thread(target=self.usagecpu)

        self.cpu_thread = None
        self.running = True

    # Fungsi untuk menampilkan penggunaan CPU dan suhu
    def usagecpu(self):
        while self.running:
            cpuusage = str(psutil.cpu_percent()) + '%'
            cputemp = os.popen("vcgencmd measure_temp").readline()
            celsius = re.sub("[^0123456789\.]", "", cputemp)

            self.lcd.lcd_display_string("CPU  : {}".format(cpuusage), 1)
            self.lcd.lcd_display_string("Suhu : {} C".format(celsius), 2)
            sleep(1)

    # Fungsi thread untuk memulai usagecpu
    def start_threads(self):
        try:
            self.running = True 
            self.cpu_thread = threading.Thread(target=self.usagecpu)
            self.cpu_thread.start()
        except KeyboardInterrupt:
            self.cleanup()

   # def stop(self):
      #  self.stopped = True

    def cleanup(self):
        self.running = False # Set the flag to False to stop the thread
        self.cpu_thread.join() # Wait for the thread to finish
        self.lcd.lcd_clear() # Clear the LCD display
        self.lcd.lcd_backlight(0) # Close the LCD connection

# Fungsi untuk mengontrol lampu LED berdasarkan kelas objek
def control_led(object_name):
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    # Konfigurasi pin LED
    red_pin = 17
    green_pin = 18
    yellow_pin = 23
    rgb_pin = 27
    white_pin = 22

    # Set output tiap LED
    GPIO.setup(red_pin, GPIO.OUT)
    GPIO.setup(green_pin, GPIO.OUT)
    GPIO.setup(yellow_pin, GPIO.OUT)
    GPIO.setup(rgb_pin, GPIO.OUT)
    GPIO.setup(white_pin, GPIO.OUT)

    # Jika Kondisi terpenuhi lakukan kode ini
    if object_name == "car":
        GPIO.output(red_pin, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(red_pin, GPIO.LOW)
    elif object_name == "person":
        GPIO.output(green_pin, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(green_pin, GPIO.LOW)
    elif object_name == "truck":
        GPIO.output(yellow_pin, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(yellow_pin, GPIO.LOW)
    elif object_name == "bus":
        GPIO.output(rgb_pin, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(rgb_pin, GPIO.LOW)
    elif object_name == "motorbike":
        GPIO.output(white_pin, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(white_pin, GPIO.LOW)
    else:
        GPIO.output(red_pin, GPIO.LOW)
        GPIO.output(white_pin, GPIO.LOW)
        GPIO.output(green_pin, GPIO.LOW)
        GPIO.output(rgb_pin, GPIO.LOW)
        GPIO.output(yellow_pin, GPIO.LOW)

# Define and parse input arguments
parser = argparse.ArgumentParser()
parser.add_argument('--modeldir', help='Folder the .tflite file is located in',
                    required=True)
parser.add_argument('--graph', help='Name of the .tflite file, if different than detect.tflite',
                    default='detect.tflite')
parser.add_argument('--labels', help='Name of the labelmap file, if different than labelmap.txt',
                    default='labelmap.txt')
parser.add_argument('--threshold', help='Minimum confidence threshold for displaying detected objects',
                    default=0.5)
parser.add_argument('--resolution', help='Desired webcam resolution in WxH. If the webcam does not support the resolution entered, errors may occur.',
                    default='1280x720')
parser.add_argument('--edgetpu', help='Use Coral Edge TPU Accelerator to speed up detection',
                    action='store_true')

# Uncomment code below to save the video
# parser.add_argument('--outvideo', help='Name of output video file',
#                             default='save_video.avi')

args = parser.parse_args()

MODEL_NAME = args.modeldir
GRAPH_NAME = args.graph
LABELMAP_NAME = args.labels
min_conf_threshold = float(args.threshold)
resW, resH = args.resolution.split('x')
# imW, imH = int(resW), int(resH)
imW = 416
imH = 416
use_TPU = args.edgetpu

# Uncomment code below to save the video
# OUTPUT_VIDEO_NAME = args.outvideo

# Inisialisasi LCD
# Memulai thread yang terkait dengan objek LCD
LCD = lcd()
LCD.start_threads()

# Import TensorFlow libraries
# If tflite_runtime is installed, import interpreter from tflite_runtime, else import from regular tensorflow
# If using Coral Edge TPU, import the load_delegate library
pkg = importlib.util.find_spec('tflite_runtime')
if pkg:
    from tflite_runtime.interpreter import Interpreter
    if use_TPU:
        from tflite_runtime.interpreter import load_delegate
else:
    from tensorflow.lite.python.interpreter import Interpreter
    if use_TPU:
        from tensorflow.lite.python.interpreter import load_delegate

# If using Edge TPU, assign filename for Edge TPU model
if use_TPU:
    # If user has specified the name of the .tflite file, use that name, otherwise use default 'edgetpu.tflite'
    if (GRAPH_NAME == 'detect.tflite'):
        GRAPH_NAME = 'edgetpu.tflite'       

# Get path to current working directory
CWD_PATH = os.getcwd()

# Path to .tflite file, which contains the model that is used for object detection
PATH_TO_CKPT = os.path.join(CWD_PATH,MODEL_NAME,GRAPH_NAME)

# Path to label map file
PATH_TO_LABELS = os.path.join(CWD_PATH,MODEL_NAME,LABELMAP_NAME)

# Uncomment code below to save the video
# FOURCC = cv2.VideoWriter_fourcc(*'XVID')

# Load the label map
with open(PATH_TO_LABELS, 'r') as f:
    labels = [line.strip() for line in f.readlines()]

# Have to do a weird fix for label map if using the COCO "starter model" from
# https://www.tensorflow.org/lite/models/object_detection/overview
# First label is '???', which has to be removed.
if labels[0] == '???':
    del(labels[0])

# Load the Tensorflow Lite model.
# If using Edge TPU, use special load_delegate argument
if use_TPU:
    interpreter = Interpreter(model_path=PATH_TO_CKPT,
                              experimental_delegates=[load_delegate('libedgetpu.so.1.0')])
    print(PATH_TO_CKPT)
else:
    interpreter = Interpreter(model_path=PATH_TO_CKPT)

interpreter.allocate_tensors()

# Get model details
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()
height = input_details[0]['shape'][1]
width = input_details[0]['shape'][2]

floating_model = (input_details[0]['dtype'] == np.float32)

input_mean = 127.5
input_std = 127.5

# Check output layer name to determine if this model was created with TF2 or TF1,
# because outputs are ordered differently for TF2 and TF1 models
outname = output_details[0]['name']

if ('StatefulPartitionedCall' in outname): # This is a TF2 model
    boxes_idx, classes_idx, scores_idx = 1, 3, 0
else: # This is a TF1 model
    boxes_idx, classes_idx, scores_idx = 0, 1, 2

# Initialize frame rate calculation
frame_rate_calc = 1
freq = cv2.getTickFrequency()

# Initialize video stream
videostream = VideoStream(resolution=(imW,imH),framerate=30).start()
time.sleep(1)

#for frame1 in camera.capture_continuous(rawCapture, format="bgr",use_video_port=True):
while True:

    # Start timer (for calculating frame rate)
    t1 = cv2.getTickCount()

    # Grab frame from video stream
    frame1 = videostream.read()

    # Uncomment code below to save the video
    # Save the video file
    # out = cv2.VideoWriter(OUTPUT_VIDEO_NAME, FOURCC, 20.0, (int(imW), int(imH)))

    # Acquire frame and resize to expected shape [1xHxWx3]
    frame = frame1.copy()
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame_resized = cv2.resize(frame_rgb, (width, height))
    input_data = np.expand_dims(frame_resized, axis=0)

    # Normalize pixel values if using a floating model (i.e. if model is non-quantized)
    if floating_model:
        input_data = (np.float32(input_data) - input_mean) / input_std

    # Perform the actual detection by running the model with the image as input
    interpreter.set_tensor(input_details[0]['index'],input_data)
    interpreter.invoke()

    # Retrieve detection results
    boxes = interpreter.get_tensor(output_details[boxes_idx]['index'])[0] # Bounding box coordinates of detected objects
    classes = interpreter.get_tensor(output_details[classes_idx]['index'])[0] # Class index of detected objects
    scores = interpreter.get_tensor(output_details[scores_idx]['index'])[0] # Confidence of detected objects

    # Loop over all detections and draw detection box if confidence is above minimum threshold
    for i in range(len(scores)):
        if ((scores[i] > min_conf_threshold) and (scores[i] <= 1.0)):

            # Get bounding box coordinates and draw box
            # Interpreter can return coordinates that are outside of image dimensions, need to force them to be within image using max() and min()
            ymin = int(max(1,(boxes[i][0] * imH)))
            xmin = int(max(1,(boxes[i][1] * imW)))
            ymax = int(min(imH,(boxes[i][2] * imH)))
            xmax = int(min(imW,(boxes[i][3] * imW)))
            
            cv2.rectangle(frame, (xmin,ymin), (xmax,ymax), (10, 255, 0), 2)

            # Draw label
            object_name = labels[int(classes[i])] # Look up object name from "labels" array using class index
            label = '%s: %d%%' % (object_name, int(scores[i]*100)) # Example: 'person: 72%'
            labelSize, baseLine = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2) # Get font size
            label_ymin = max(ymin, labelSize[1] + 10) # Make sure not to draw label too close to top of window
            cv2.rectangle(frame, (xmin, label_ymin-labelSize[1]-10), (xmin+labelSize[0], label_ymin+baseLine-10), (255, 255, 255), cv2.FILLED) # Draw white box to put label text in
            cv2.putText(frame, label, (xmin, label_ymin-7), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2) # Draw label text
            
            # Turn-on LED
            # Membuat thread baru untuk menjalankan fungsi control_led dengan argumen object_name
            threading.Thread(target=control_led, args=(object_name,)).start()

    # Draw framerate in corner of frame
    cv2.putText(frame,'FPS: {0:.2f}'.format(frame_rate_calc),(30,50),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,0),2,cv2.LINE_AA)

    # Uncomment code below to save the video
    # Whenever we encounter an object that we want to detect, add code to record the current frame
    # out.write(frame)

    # All the results have been drawn on the frame, so it's time to display it.
    cv2.imshow('Object detector', frame)

    # Calculate framerate
    t2 = cv2.getTickCount()
    time1 = (t2-t1)/freq
    frame_rate_calc= 1/time1

    # Press 'q' to quit
    if cv2.waitKey(1) == ord('q'):
        break

# Uncomment code below to save the video
# out.release()

# Clean up
cv2.destroyAllWindows()
videostream.stop()
LCD.cleanup()
