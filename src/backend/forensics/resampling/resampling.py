# -*- coding: utf-8 -*-
"""Resampling detection — Mahdian & Saic (IEEE TIFS 2008)."""
import numpy as np
import cv2
from scipy.signal import medfilt2d
from scipy.fftpack import fft2, ifft2
from skimage.transform import radon
