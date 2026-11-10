"""Image-space transformations — thin wrappers over the Rust core."""

from restring import _core


def rgb2gray(image):
    """Grayscale via the standard luminance weights (RGB Image -> gray Image)."""
    return image.gray(1.0)


def largest_square(image):
    """Central largest square crop."""
    return image.largest_square()


def largest_rect(image, aspect):
    """Central largest crop with the given width/height aspect (w over h)."""
    h, w = image.shape()[:2]
    rows = image.tolist()
    current = w / h
    if current > aspect:  # too wide: crop columns
        new_w = max(1, int(round(h * aspect)))
        c0 = (w - new_w) // 2
        rows = [row[c0:c0 + new_w] for row in rows]
    else:  # too tall: crop rows
        new_h = max(1, int(round(w / aspect)))
        r0 = (h - new_h) // 2
        rows = rows[r0:r0 + new_h]
    return _core.Image.from_nested(rows)


def resize(image, out_shape):
    """Anti-aliased resample: box filter down / bilinear up."""
    h, w = out_shape[:2]
    return image.resize(w, h)
