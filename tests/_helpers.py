"""Shared test helpers: dependency-free image I/O via the Rust core."""

import os

import numpy as np

from restring import _core


def image_from_numpy(array):
    """numpy array (h x w or h x w x 3, float 0..1) -> core Image."""
    return _core.Image.from_nested(np.asarray(array, dtype=float).tolist())


def image_to_numpy(image):
    """core Image -> numpy array (h x w or h x w x 3)."""
    return np.asarray(image.tolist(), dtype=float)


def save_image(path, array):
    """Save a float 0..1 numpy array (2D gray or HxWx3) to PNG."""
    image_from_numpy(array).save_png(os.fspath(path))


def load_rgb(path):
    """Load an image as a float 0..1 RGB numpy array."""
    return image_to_numpy(_core.Image.load(os.fspath(path)))


def load_gray(path):
    """Load an image as a float 0..1 grayscale numpy array."""
    img = _core.Image.load(os.fspath(path))
    if img.shape()[2] == 3:
        img = img.gray(1.0)
    return image_to_numpy(img)
