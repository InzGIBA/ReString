"""Image-space transformations — thin wrappers over the Rust core."""



def rgb2gray(image):
    """Grayscale via the standard luminance weights (RGB Image -> gray Image)."""
    return image.gray(1.0)


def largest_square(image):
    """Central largest square crop."""
    return image.largest_square()


def resize(image, out_shape):
    """Anti-aliased resample: box filter down / bilinear up."""
    h, w = out_shape[:2]
    return image.resize(w, h)
