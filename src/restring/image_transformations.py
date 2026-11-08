import numpy as np


def rgb2gray(rgb):
    return np.dot(rgb[..., :3], [0.2989, 0.5870, 0.1140])


def _bin_weights(n_in, n_out):
    """Resample weights, one row per output pixel (rows sum to 1).

    Downscaling uses exact area overlap (anti-aliased box filter); upscaling
    uses bilinear interpolation between pixel centers, which keeps synthetic
    targets smooth instead of blocky.
    """
    if n_out >= n_in:  # bilinear on pixel centers
        src = (np.arange(n_out) + 0.5) * (n_in / n_out) - 0.5
        i0 = np.floor(src).astype(int)
        frac = src - i0
        weights = np.zeros((n_out, n_in))
        for k in range(n_out):
            lo = np.clip(i0[k], 0, n_in - 1)
            hi = np.clip(i0[k] + 1, 0, n_in - 1)
            weights[k, lo] += 1.0 - frac[k]
            weights[k, hi] += frac[k]
        return weights
    edges = np.linspace(0.0, n_in, n_out + 1)  # anti-aliased box
    idx = np.arange(n_in, dtype=float)
    weights = np.empty((n_out, n_in))
    for k in range(n_out):
        weights[k] = np.clip(np.minimum(idx + 1, edges[k + 1]) - np.maximum(idx, edges[k]), 0, None)
    return weights / weights.sum(axis=1, keepdims=True)


def resize(image: np.ndarray, out_shape) -> np.ndarray:
    """Anti-aliased box resample — replacement for skimage.transform.resize.

    Supports 2D and (H, W, C) inputs; output has exactly out_shape leading dims.
    """
    h_out, w_out = out_shape
    row_w = _bin_weights(image.shape[0], h_out)
    col_w = _bin_weights(image.shape[1], w_out)
    if image.ndim == 2:
        return row_w @ image @ col_w.T
    # (H_o, W_i, C) then fold columns -> (H_o, C, W_o) -> (H_o, W_o, C)
    tmp = np.tensordot(row_w, image, axes=([1], [0]))
    return np.tensordot(tmp, col_w, axes=([1], [1])).transpose(0, 2, 1)


def largest_square(image: np.ndarray) -> np.ndarray:
    short_edge = np.argmin(image.shape[:2])  # 0 = vertical <= horizontal; 1 = otherwise
    short_edge_half = image.shape[short_edge] // 2
    long_edge_center = image.shape[1 - short_edge] // 2
    if short_edge == 0:
        return image[:, long_edge_center - short_edge_half: long_edge_center + short_edge_half]
    if short_edge == 1:
        return image[long_edge_center - short_edge_half: long_edge_center + short_edge_half, :]
