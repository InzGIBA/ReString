"""Shared test helpers: Pillow-based image I/O."""

from pathlib import Path

import numpy as np
from PIL import Image


def save_image(path, array):
    """Save a float 0..1 array (2D gray or HxWx3) to PNG."""
    data = (np.clip(array, 0, 1) * 255).astype(np.uint8)
    mode = "L" if array.ndim == 2 else "RGB"
    Image.fromarray(data, mode=mode).save(Path(path))


def load_rgb(path):
    """Load an image as float 0..1 RGB (mirrors restring.cli input handling)."""
    return np.asarray(Image.open(path).convert("RGB"), dtype=float) / 255


def load_gray(path):
    """Load an image as float 0..1 grayscale."""
    return np.asarray(Image.open(path).convert("L"), dtype=float) / 255
