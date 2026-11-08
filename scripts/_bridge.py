"""numpy <-> core Image bridge for analysis scripts (numpy is a dev dependency)."""

import numpy as np

from restring import _core


def image_from_numpy(array):
    return _core.Image.from_nested(np.asarray(array, dtype=float).tolist())


def image_to_numpy(image):
    return np.asarray(image.tolist(), dtype=float)
