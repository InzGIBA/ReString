"""Image quality metrics — delegated to the Rust core (no dependencies)."""

from restring import _core


def ssim(a, b, data_range=1.0, win_size=7):
    """Structural similarity with a uniform window (restring.metrics port)."""
    return _core.ssim(a, b)


def blurred_ssim(a, b, radius=2):
    """SSIM after a box blur on both images. Thin dark lines on white defeat
    plain SSIM's local statistics; the blur restores them, so the value
    tracks perceived quality along a pull series instead of peaking early
    (docs/research/pull-count-quality.md)."""
    return _core.ssim_blur(a, b, radius)


def mse(a, b):
    return _core.mse(a, b)


def corr(a, b):
    return _core.corr(a, b)
