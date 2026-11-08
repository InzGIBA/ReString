"""End-to-end quality acceptance tests.

These tests assert that the greedy string art algorithm actually recreates the
reference image, not merely that it runs. Quality is measured on deterministic
synthetic fixtures (the greedy path has no randomness, so numbers are stable
across runs). Every threshold was calibrated against the real pipeline — the
measured value is noted next to each threshold, with a ~25-35% safety margin.
"""

import matplotlib.image as mpimg
import numpy as np
from skimage.metrics import structural_similarity

from restring.canvas import init_canvas, pull_order_to_array_bw
from restring.cli import main
from restring.generator import Config, generate_bw, generate_rgb
from restring.image_transformations import rgb2gray
from restring.nails import create_circle_nail_positions

SHAPE = (64, 64)
NAILS = create_circle_nail_positions(SHAPE, nail_step=4)  # 44 nails

R, C = np.mgrid[0:64, 0:64]
DISK_MASK = (R - 32) ** 2 + (C - 32) ** 2 < 12 ** 2
BACKGROUND_MASK = (R - 32) ** 2 + (C - 32) ** 2 > 20 ** 2


def synthetic_disk():
    """Dark disk in the centre on a white background."""
    img = np.ones((64, 64, 3))
    img[DISK_MASK] = 0.2
    return img


def synthetic_two_blobs():
    """Two dark regions in opposite corners of the canvas."""
    img = np.ones((64, 64, 3))
    img[(R - 20) ** 2 + (C - 20) ** 2 < 9 ** 2] = 0.2   # top-left disk
    img[(R > 44) & (C > 40) & (C < 60)] = 0.2            # bottom-right bar
    return img


def synthetic_color():
    """Red disk on the left, blue disk on the right."""
    img = np.ones((64, 64, 3))
    img[(R - 32) ** 2 + (C - 20) ** 2 < 10 ** 2] = (0.9, 0.1, 0.1)
    img[(R - 32) ** 2 + (C - 44) ** 2 < 10 ** 2] = (0.1, 0.1, 0.9)
    return img


def mse(a, b):
    return float(np.mean((a - b) ** 2))


def render_random_order(order_length, seed):
    """Render a random nail sequence — what unguided thread pulling achieves."""
    rng = np.random.default_rng(seed)
    order = [0] + list(rng.integers(0, len(NAILS), size=order_length - 1))
    return pull_order_to_array_bw(order, init_canvas(SHAPE), NAILS, -0.1)


def test_bw_reduces_error_vs_blank():
    img = synthetic_disk()
    target = rgb2gray(img) * 0.9

    result, _ = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=100))

    blank_mse = mse(init_canvas(SHAPE), target)  # measured: 0.081
    assert mse(result, target) <= 0.45 * blank_mse  # measured: 0.027 (0.33x blank)


def test_bw_beats_random_baseline():
    img = synthetic_disk()
    target = rgb2gray(img) * 0.9

    result, order = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=150))
    greedy_mse = mse(result, target)  # measured: 0.033

    for seed in (0, 1, 2):
        random_mse = mse(render_random_order(len(order), seed), target)  # measured: 0.068-0.073
        assert greedy_mse <= 0.6 * random_mse, f"greedy failed to beat random baseline (seed={seed})"


def test_bw_ssim_above_threshold():
    img = synthetic_disk()
    target = rgb2gray(img) * 0.9

    # SSIM peaks at moderate pull counts: the render strength (0.1) is twice the
    # simulation strength (0.05), so over-pulling overshoots the target
    result, _ = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=30))

    assert structural_similarity(target, result, data_range=1.0) >= 0.30  # measured: 0.40


def test_bw_more_pulls_not_worse():
    img = synthetic_disk()
    target = rgb2gray(img) * 0.9

    result_30, _ = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=30))
    result_150, _ = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=150))

    assert mse(result_150, target) <= 0.8 * mse(result_30, target)  # measured: 0.033 vs 0.055


def test_bw_structure_preserved():
    img = synthetic_two_blobs()
    blob_1 = (R - 20) ** 2 + (C - 20) ** 2 < 9 ** 2
    blob_2 = (R > 44) & (C > 40) & (C < 60)
    corner_background = (R < 12) & (C > 52)

    result, _ = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=150))

    # both regions must render darker than untouched background — the picture is
    # spatially recognizable, not uniformly darkened
    # measured: blob means 0.39 / 0.57, background 1.00
    assert result[blob_1].mean() < result[corner_background].mean() - 0.25
    assert result[blob_2].mean() < result[corner_background].mean() - 0.25


def test_pull_order_is_valid():
    img = synthetic_disk()

    _, order = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=150))

    assert order[0] == 0
    assert all(0 <= idx < len(NAILS) for idx in order)
    assert all(a != b for a, b in zip(order, order[1:]))  # no zero-length pulls


def test_rgb_reduces_error_per_channel():
    img = synthetic_color()

    result, _ = generate_rgb(img, SHAPE, NAILS, Config(side_len=64, pull_amount=100))

    for channel in range(3):
        blank_mse = mse(np.ones(SHAPE), img[:, :, channel])
        # measured factors: R 0.51, G 0.46, B 0.51
        assert mse(result[:, :, channel], img[:, :, channel]) <= 0.7 * blank_mse, \
            f"channel {channel} failed quality acceptance"


def test_cli_bw_quality(tmp_path):
    img = synthetic_disk()
    input_file = tmp_path / "input.png"
    output_file = tmp_path / "output.png"
    mpimg.imsave(input_file, img)

    main(["-i", str(input_file), "-o", str(output_file), "-d", "64", "-n", "4", "-l", "150"])

    raw = mpimg.imread(output_file)
    assert raw.shape == (64, 64, 4)  # RGBA PNG
    assert 0.0 <= raw.min() and raw.max() <= 1.0

    result = rgb2gray(raw[..., :3])
    target = rgb2gray(img) * 0.9
    blank_mse = mse(np.ones(SHAPE), target)
    assert mse(result, target) <= 0.45 * blank_mse  # measured: 0.029 (0.36x blank)

    # the disk region must come out darker than the background
    assert result[DISK_MASK].mean() < result[BACKGROUND_MASK].mean() - 0.35  # measured gap: 0.54


def test_cli_rgb_quality(tmp_path):
    img = synthetic_color()
    input_file = tmp_path / "input.png"
    output_file = tmp_path / "output.png"
    mpimg.imsave(input_file, img)

    main(["-i", str(input_file), "-o", str(output_file), "-d", "64", "-n", "4", "-l", "100", "--rgb"])

    raw = mpimg.imread(output_file)
    assert raw.shape == (64, 64, 4)
    result = raw[..., :3]

    for channel in range(3):
        blank_mse = mse(np.ones(SHAPE), img[:, :, channel])
        # measured factors: R 0.58, G 0.57, B 0.61
        assert mse(result[:, :, channel], img[:, :, channel]) <= 0.75 * blank_mse, \
            f"channel {channel} failed quality acceptance"
