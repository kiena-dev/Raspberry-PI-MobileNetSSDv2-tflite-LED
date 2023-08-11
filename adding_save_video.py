# Import packages
import os
import argparse
import threading
import cv2
import numpy as np
import importlib.util
import time
import re
import RPi.GPIO as GPIO
import drivers
from time import sleep
import psutil
import smbus
# from threading import Threa

class lcd:
    def __init__(self):
        # Initialize lcd
        self.bus = smbus.SMBus(1)
        time.sleep(1)
        self.lcd = drivers.Lcd()
        # self.cpu_thread = threading.Thread(target=self.usagecpu)

        self.cpu_thread = None
        self.running = True

    def usagecpu(self):
        while self.running:
            cpuusage = str(psutil.cpu_percent()) + '%'
            cputemp = os.popen("vcgencmd measure_temp").readline()
            celsius = re.sub("[^0123456789\.]", "", cputemp)

            self.lcd.lcd_display_string("CPU  : {}".format(cpuusage), 1)
            self.lcd.lcd_display_string("Suhu : {} C".format(celsius), 2)
            sleep(1)

    def start_threads(self):
        try:
            self.running = True 
            self.cpu_thread = threading.Thread(target=self.usagecpu)
            self.cpu_thread.start()
        except KeyboardInterrupt:
            self.cleanup()

    def cleanup(self):
        self.running = False # Set the flag to False to stop the thread
        self.cpu_thread.join() # Wait for the thread to finish
        self.lcd.lcd_clear() # Clear the LCD display
        self.lcd.lcd_backlight(0) # Close the LCD connection

def control_led(object_name):
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    red_pin = 17
    green_pin = 18
    yellow_pin = 23
    rgb_pin = 27
    white_pin = 22

    GPIO.setup(red_pin, GPIO.OUT)
    GPIO.setup(green_pin, GPIO.OUT)
    GPIO.setup(yellow_pin, GPIO.OUT)
    GPIO.setup(rgb_pin, GPIO.OUT)
    GPIO.setup(white_pin, GPIO.OUT)

    # Kondisi
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
    elif object_name == "motorcycle":
        GPIO.output(white_pin, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(white_pin, GPIO.LOW)
    else:
        GPIO.output(red_pin, GPIO.LOW)
        GPIO.output(white_pin, GPIO.LOW)
        GPIO.output(green_pin, GPIO.LOW)
        GPIO.output(rgb_pin, GPIO.LOW)
        GPIO.output(yellow_pin, GPIO.LOW)
        
class tflite_detection:
    def __init__(self):
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
        parser.add_argument('--video', help='Name of the video file',
                            default='test.mp4')
        parser.add_argument('--edgetpu', help='Use Coral Edge TPU Accelerator to speed up detection',
                            action='store_true')
        parser.add_argument('--outvideo', help='Name of output video file',
                            default='save_video.avi')

        args = parser.parse_args()

        self.MODEL_NAME = args.modeldir
        self.GRAPH_NAME = args.graph
        self.LABELMAP_NAME = args.labels
        self.VIDEO_NAME = args.video
        self.min_conf_threshold = float(args.threshold)
        self.use_TPU = args.edgetpu
        self.OUTPUT_VIDEO_NAME = args.outvideo

        self.LCD = lcd()
        self.LCD.start_threads()

        # Import TensorFlow libraries
        # If tflite_runtime is installed, import interpreter from tflite_runtime, else import from regular tensorflow
        # If using Coral Edge TPU, import the load_delegate library
        pkg = importlib.util.find_spec('tflite_runtime')
        if pkg:
            from tflite_runtime.interpreter import Interpreter
            if self.use_TPU:
                from tflite_runtime.interpreter import load_delegate
        else:
            from tensorflow.lite.python.interpreter import Interpreter
            if self.use_TPU:
                from tensorflow.lite.python.interpreter import load_delegate

        # If using Edge TPU, assign filename for Edge TPU model
        if self.use_TPU:
            # If user has specified the name of the .tflite file, use that name, otherwise use default 'edgetpu.tflite'
            if (self.GRAPH_NAME == 'detect.tflite'):
                self.GRAPH_NAME = 'edgetpu.tflite' 

        # Get path to current working directory
        self.CWD_PATH = os.getcwd()

        # Path to video file
        self.VIDEO_PATH = os.path.join(self.CWD_PATH, self.VIDEO_NAME)

        # Path to .tflite file, which contains the model that is used for object detection
        self.PATH_TO_CKPT = os.path.join(self.CWD_PATH, self.MODEL_NAME, self.GRAPH_NAME)

        # Path to label map file
        self.PATH_TO_LABELS = os.path.join(self.CWD_PATH, self.MODEL_NAME, self.LABELMAP_NAME)

        # Uncomment code below to save the video
        # self.FOURCC = cv2.VideoWriter_fourcc(*'XVID')

        # Load the label map
        with open(self.PATH_TO_LABELS, 'r') as f:
            self.labels = [line.strip() for line in f.readlines()]

        if self.labels[0] == '???':
            del(self.labels[0])

        # Load the Tensorflow Lite model.
        # If using Edge TPU, use special load_delegate argument
        if self.use_TPU:
            self.interpreter = Interpreter(model_path=self.PATH_TO_CKPT,
                                    experimental_delegates=[load_delegate('libedgetpu.so.1.0')])
            print(self.PATH_TO_CKPT)
        else:
            self.interpreter = Interpreter(model_path=self.PATH_TO_CKPT)
        self.interpreter.allocate_tensors()

        # Get model details
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
        self.height = self.input_details[0]['shape'][1]
        self.width = self.input_details[0]['shape'][2]

        self.floating_model = (self.input_details[0]['dtype'] == np.float32)

        self.input_mean = 127.5
        self.input_std = 127.5

        # Check output layer name to determine if this model was created with TF2 or TF1,
        # because outputs are ordered differently for TF2 and TF1 models
        outname = self.output_details[0]['name']
        if ('StatefulPartitionedCall' in outname): # This is a TF2 model
            self.boxes_idx, self.classes_idx, self.scores_idx = 1, 3, 0
        else: # This is a TF1 model
            self.boxes_idx, self.classes_idx, self.scores_idx = 0, 1, 2

    def detect_objects(self):
        # Initialize frame rate calculation
        frame_rate_calc = 1
        freq = cv2.getTickFrequency()

        # Open video file
        video = cv2.VideoCapture(self.VIDEO_PATH)
        imW = video.get(cv2.CAP_PROP_FRAME_WIDTH)
        imH = video.get(cv2.CAP_PROP_FRAME_HEIGHT)

        # Uncomment code below to save the video
        # Save the video file
        # out = cv2.VideoWriter(self.OUTPUT_VIDEO_NAME, self.FOURCC, 20.0, (int(imW), int(imH)))

        while(video.isOpened()):

            # Start timer (for calculating frame rate)
            t1 = cv2.getTickCount()

            # Acquire frame and resize to expected shape [1xHxWx3]
            ret, frame = video.read()
            if not ret:
                print('Reached the end of the video!')
                break
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_resized = cv2.resize(frame_rgb, (self.width, self.height))
            input_data = np.expand_dims(frame_resized, axis=0)

            # Normalize pixel values if using a floating model (i.e. if model is non-quantized)
            if self.floating_model:
                input_data = (np.float32(input_data) - self.input_mean) / self.input_std

            # Perform the actual detection by running the model with the image as input
            self.interpreter.set_tensor(self.input_details[0]['index'],input_data)
            self.interpreter.invoke()

            # Retrieve detection results
            boxes = self.interpreter.get_tensor(self.output_details[self.boxes_idx]['index'])[0] # Bounding box coordinates of detected objects
            classes = self.interpreter.get_tensor(self.output_details[self.classes_idx]['index'])[0] # Class index of detected objects
            scores = self.interpreter.get_tensor(self.output_details[self.scores_idx]['index'])[0] # Confidence of detected objects

            # Loop over all detections and draw detection box if confidence is above minimum threshold
            for i in range(len(scores)):
                if ((scores[i] > self.min_conf_threshold) and (scores[i] <= 1.0)):
                    # Get bounding box coordinates and draw box
                    # Interpreter can return coordinates that are outside of image dimensions, need to force them to be within image using max() and min()
                    ymin = int(max(1,(boxes[i][0] * imH)))
                    xmin = int(max(1,(boxes[i][1] * imW)))
                    ymax = int(min(imH,(boxes[i][2] * imH)))
                    xmax = int(min(imW,(boxes[i][3] * imW)))
                    cv2.rectangle(frame, (xmin,ymin), (xmax,ymax), (10, 255, 0), 4)

                    # Draw label
                    object_name = self.labels[int(classes[i])] # Look up object name from "labels" array using class index
                    label = '%s: %d%%' % (object_name, int(scores[i]*100)) # Example: 'person: 72%'
                    labelSize, baseLine = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2) # Get font size
                    label_ymin = max(ymin, labelSize[1] + 10) # Make sure not to draw label too close to top of window
                    cv2.rectangle(frame, (xmin, label_ymin-labelSize[1]-10), (xmin+labelSize[0], label_ymin+baseLine-10), (255, 255, 255), cv2.FILLED) # Draw white box to put label text in
                    cv2.putText(frame, label, (xmin, label_ymin-7), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2) # Draw label text

                    # Turn-on LED
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
        video.release()
        GPIO.cleanup()
        cv2.destroyAllWindows()
        self.LCD.cleanup()

detek = tflite_detection()
threading.Thread(target=detek.detect_objects(), args=()).start()