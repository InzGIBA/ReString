"""Image quality metrics — delegated to the Rust core (no dependencies)."""

from restring import _core


def ssim(a, b, data_range=1.0, win_size=7):
    """Structural similarity with a uniform window (restring.metrics port)."""
    return _core.ssim(a, b)


def mse(a, b):
    return _core.mse(a, b)


def corr(a, b):
    return _core.corr(a, b)
