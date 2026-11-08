"""Image quality metrics — self-contained, numpy only."""

import numpy as np


def _box_mean(x, size):
    """Mean over a uniform size x size window at every valid position."""
    c = np.pad(np.cumsum(np.cumsum(x, axis=0), axis=1), ((1, 0), (1, 0)))
    s = c[size:, size:] - c[:-size, size:] - c[size:, :-size] + c[:-size, :-size]
    return s / (size * size)


def ssim(a, b, data_range=1.0, win_size=7):
    """Structural similarity with a uniform window (no external dependencies).

    Same classic formula as skimage.metrics.structural_similarity with
    gaussian_weights=False.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    c1 = (0.01 * data_range) ** 2
    c2 = (0.03 * data_range) ** 2

    mu_a = _box_mean(a, win_size)
    mu_b = _box_mean(b, win_size)
    var_a = _box_mean(a * a, win_size) - mu_a ** 2
    var_b = _box_mean(b * b, win_size) - mu_b ** 2
    cov = _box_mean(a * b, win_size) - mu_a * mu_b

    num = (2 * mu_a * mu_b + c1) * (2 * cov + c2)
    den = (mu_a ** 2 + mu_b ** 2 + c1) * (var_a + var_b + c2)
    return float(np.mean(num / den))
