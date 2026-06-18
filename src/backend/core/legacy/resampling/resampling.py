# -*- coding: utf-8 -*-
"""Resampling detection — Mahdian & Saic (IEEE TIFS 2008)."""
import numpy as np
import cv2
from scipy.signal import medfilt2d
from scipy.fftpack import fft2, ifft2
from skimage.transform import radon

# --- Cell 0 ---
image_file = '1.jpg'
imagem = io.imread(image_file)

# --- Cell 1 ---
#imagem = io.imread('./1.jpg')

#reamostragem(imagem)

# --- Cell 2 ---
#!pip install jupyter_bbox_widget --proxy http://proxy.ditec.pf.gov.br:3128

# --- Cell 3 ---
sprite1 = Image.from_file(image_file)

multi_canvas = MultiCanvas(2, width=imagem.shape[1]-1, height=imagem.shape[0]-1)

multi_canvas[1].stroke_style = "red"

multi_canvas[0].draw_image(sprite1)

multi_canvas
