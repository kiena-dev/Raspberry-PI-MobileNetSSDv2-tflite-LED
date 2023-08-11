import tensorflow as tf
import os
import argparse

# Define and parse input arguments
parser = argparse.ArgumentParser()
parser.add_argument('--modeldir', help='Name of the .tflite file, if different than detect.tflite',
                    default='detect.tflite')

args = parser.parse_args()

MODEL_NAME = args.modeldir 

# Get path to current working directory
CWD_PATH = os.getcwd()

# Path to .tflite file, which contains the model that is used for object detection
PATH_TO_CKPT = os.path.join(CWD_PATH,MODEL_NAME)

# Load the TFLite model and allocate tensors.
interpreter = tf.lite.Interpreter(model_path=PATH_TO_CKPT)
interpreter.allocate_tensors()

# Get input, output tensors and signatures.
input_details = interpreter.get_input_details()
print(input_details)
output_details = interpreter.get_output_details()
print(output_details)
signature_lists = interpreter.get_signature_list()
print(signature_lists)