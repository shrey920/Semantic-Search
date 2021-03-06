from keras.models import Model
from keras.layers import Input
from keras.layers import Dense
from keras.layers import Lambda
from keras.layers.normalization import BatchNormalization
from keras.callbacks import RemoteMonitor
import keras
from time import time, sleep
import keras.backend as K 
import h5py
import sys, ipdb
import math, os, sys
from extract_features_and_dump import data_generator
import numpy as np
from keras.callbacks import TensorBoard
import cv2
from validation_script import ValidCallBack
import ConfigParser
import matplotlib.pyplot as plt


config = ConfigParser.RawConfigParser()
config.read('local.cfg')

PATH_h5 		= config.get("h5", "h5_training")
MARGIN 			= config.getfloat("training", "MARGIN")
INCORRECT_BATCH = config.getint("training", "INCORRECT_BATCH")
BATCH 			= INCORRECT_BATCH + 1
IMAGE_DIM 		= config.getint("training", "IMAGE_DIM")
WORD_DIM 		= config.getint("training", "WORD_DIM")
TRAINING_CLASS_RANGES = config.get("other", "TRAINING_CLASS_RANGES")

class DelayCallback(keras.callbacks.Callback):
	def on_train_begin(self, logs={}):
		pass

	def on_batch_end(self, batch, logs={}):
		sleep(0.05)

class EpochCheckpoint(keras.callbacks.Callback):
	def __init__(self, folder):
		super(EpochCheckpoint, self).__init__()
		assert folder is not None, "Err. Please specify a folder where models will be saved"
		self.folder = folder
		print "[LOG] EpochCheckpoint: folder to save models: "+self.folder

	def on_epoch_end(self, epoch, logs={}):
		print "Saving model..."
		self.model.save(os.path.join(self.folder+"epoch_"+str(epoch)+".hdf5"))


def get_num_train_images():
	'''
	get the number of training images in processed_features/features.h5
	'''
	
	hf = h5py.File(PATH_h5, "r")
	x_h5 = hf["data/features"]
	num_train = x_h5.shape[0]
	hf.close()

	return num_train


def linear_transformation(a):
	""" 
	Takes a 4096-dim vector, applies linear transformation to get WORD_DIM vector.
	"""
	b = Dense(WORD_DIM, name='transform')(a)
	c = BatchNormalization()(b)
	return c

def hinge_rank_loss(word_vectors, image_vectors, TESTING=False):
	"""
	Custom hinge loss per (image, label) example - Page4.
	word_vectors is y_true
	image_vectors is y_pred
	"""
	slice_first = lambda x: x[0:1 , :]
	slice_but_first = lambda x: x[1:, :]

	# separate correct/wrong images
	correct_image = Lambda(slice_first, output_shape=(1, WORD_DIM))(image_vectors)
	wrong_images = Lambda(slice_but_first, output_shape=(INCORRECT_BATCH, WORD_DIM))(image_vectors)

	# separate correct/wrong words
	correct_word = Lambda(slice_first, output_shape=(1, WORD_DIM))(word_vectors)
	wrong_words = Lambda(slice_but_first, output_shape=(INCORRECT_BATCH, WORD_DIM))(word_vectors)

	# l2 norm
	l2 = lambda x: K.sqrt(K.sum(K.square(x), axis=1, keepdims=True))
	l2norm = lambda x: x/l2(x)

	# tiling to replicate correct_word and correct_image
	correct_words = K.tile(correct_word, (INCORRECT_BATCH,1))
	correct_images = K.tile(correct_image, (INCORRECT_BATCH,1))

	# converting to unit vectors
	correct_words = l2norm(correct_words)
	wrong_words = l2norm(wrong_words)
	correct_images = l2norm(correct_images)
	wrong_images = l2norm(wrong_images)

	# correct_image VS incorrect_words | Note the singular/plurals
	# cost_images = MARGIN - K.sum(correct_images * correct_words, 1) + K.sum(correct_images * wrong_words, 1) 
	# cost_images = K.maximum(cost_images, 0.0)
	
	# correct_word VS incorrect_images | Note the singular/plurals
	cost_words = MARGIN - K.sum(correct_words * correct_images, axis=1) + K.sum(correct_words * wrong_images, axis=1) 
	cost_words = K.maximum(cost_words, 0.0)

	# currently cost_words and cost_images are vectors - need to convert to scalar
	# cost_images = K.sum(cost_images, axis=-1)
	cost_words  = K.sum(cost_words, axis=-1)

	if TESTING:
		# ipdb.set_trace()
		assert K.eval(wrong_words).shape[0] == INCORRECT_BATCH
		assert K.eval(correct_words).shape[0] == INCORRECT_BATCH
		assert K.eval(wrong_images).shape[0] == INCORRECT_BATCH
		assert K.eval(correct_images).shape[0] == INCORRECT_BATCH
		assert K.eval(correct_words).shape==K.eval(correct_images).shape
		assert K.eval(wrong_words).shape==K.eval(wrong_images).shape
		assert K.eval(correct_words).shape==K.eval(wrong_images).shape
	
	# return cost_words + cost_images
	return cost_words/INCORRECT_BATCH
	

def build_model(image_features, word_features=None):
	image_vector = linear_transformation(image_features)

	mymodel = Model(inputs=image_features, outputs=image_vector)
	mymodel.compile(optimizer="adam", loss=hinge_rank_loss)
	return mymodel

def main():

	image_features = Input(shape=(4096,))
	model = build_model(image_features)
	print model.summary()

	# number of training images 
	_num_train = get_num_train_images()

	# Callbacks 
	# remote_cb = RemoteMonitor(root='http://localhost:9000')
	tensorboard = TensorBoard(log_dir="logs/{}".format(time()))
	epoch_cb    = EpochCheckpoint(folder="./epochs/")
	valid_cb	= ValidCallBack()

	# fit generator
	steps_per_epoch = math.ceil(_num_train/float(BATCH))
	print "Steps per epoch i.e number of iterations: ",steps_per_epoch
	
	train_datagen = data_generator(batch_size=INCORRECT_BATCH, image_class_ranges=TRAINING_CLASS_RANGES)
	history = model.fit_generator(
			train_datagen,
			steps_per_epoch=steps_per_epoch,
			epochs=250,
			callbacks=[tensorboard, valid_cb, epoch_cb]
		)
	print history.history.keys()
	plt.figure(1)  
	# summarize history for loss  
	
	plt.plot(history.history['loss'])  
	# plt.plot(history.history['val_loss'])  
	plt.title('model loss')  
	plt.ylabel('loss')  
	plt.xlabel('epoch')  
	plt.legend(['train', 'test'], loc='upper left')  
	plt.show() 
	plt.savefig('plots/loss.png') 


	K.clear_session()

if __name__=="__main__":
	main()
