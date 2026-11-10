"""E2E quality acceptance tests.

These tests assert that the greedy string art algorithm actually recreates the
reference image, not merely that it runs. Quality is measured on deterministic
synthetic fixtures (the greedy path has no randomness, so numbers are stable
across runs). Every threshold was calibrated against the real pipeline — the
measured value is noted next to each threshold, with a ~25-35% safety margin.
"""

import math

import numpy as np

from _helpers import image_from_numpy, image_to_numpy, load_gray, load_rgb, save_image
from restring.canvas import init_canvas, pull_order_to_array_bw
from restring.cli import main
from restring.generator import Config, generate_bw, generate_rgb
from restring.image_transformations import rgb2gray
from restring.metrics import ssim
from restring.nails import create_circle_nail_positions

SHAPE = (64, 64)
NAILS = create_circle_nail_positions(SHAPE, nail_step=4)  # 44 nails

R, C = np.mgrid[0:64, 0:64]
DISK_MASK = (R - 32) ** 2 + (C - 32) ** 2 < 12 ** 2
BACKGROUND_MASK = (R - 32) ** 2 + (C - 32) ** 2 > 20 ** 2


def synthetic_disk():
    img = np.ones((64, 64, 3))
    img[DISK_MASK] = 0.2
    return image_from_numpy(img)


def synthetic_two_blobs():
    img = np.ones((64, 64, 3))
    img[(R - 20) ** 2 + (C - 20) ** 2 < 9 ** 2] = 0.2   # top-left disk
    img[(R > 44) & (C > 40) & (C < 60)] = 0.2            # bottom-right bar
    return image_from_numpy(img)


def synthetic_color():
    img = np.ones((64, 64, 3))
    img[(R - 32) ** 2 + (C - 20) ** 2 < 10 ** 2] = (0.9, 0.1, 0.1)
    img[(R - 32) ** 2 + (C - 44) ** 2 < 10 ** 2] = (0.1, 0.1, 0.9)
    return image_from_numpy(img)


def gray_target(img_image):
    return image_to_numpy(rgb2gray(img_image)) * 0.9


def mse(a, b):
    return float(np.mean((a - b) ** 2))


def render_random_order(order_length, seed):
    """Render a random nail sequence — what unguided thread pulling achieves."""
    rng = np.random.default_rng(seed)
    order = [0] + list(rng.integers(0, len(NAILS), size=order_length - 1))
    return image_to_numpy(pull_order_to_array_bw(order, init_canvas(SHAPE), NAILS, -0.1))


def test_bw_reduces_error_vs_blank():
    img = synthetic_disk()
    target = gray_target(img)

    # pinned to the historical default 0.1: these thresholds are calibrated
    # for it. The 1/L auto fit targets the 300 px grid (see docs/tuning.md).
    result, _ = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=100,
                                                      export_strength=0.1))

    blank_mse = mse(np.ones(SHAPE), target)  # measured: 0.081
    assert mse(image_to_numpy(result), target) <= 0.45 * blank_mse  # measured: 0.027


def test_bw_beats_random_baseline():
    img = synthetic_disk()
    target = gray_target(img)

    # pinned to 0.1: the random baseline below renders at -0.1 too
    result, order = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=150,
                                                          export_strength=0.1))
    greedy_mse = mse(image_to_numpy(result), target)  # measured: 0.033

    for seed in (0, 1, 2):
        random_mse = mse(render_random_order(len(order), seed), target)  # measured: 0.068-0.073
        assert greedy_mse <= 0.6 * random_mse, f"greedy failed to beat random baseline (seed={seed})"


def test_bw_ssim_above_threshold():
    img = synthetic_disk()
    target = gray_target(img)

    # SSIM peaks at moderate pull counts: the render strength (0.1) is twice the
    # simulation strength (0.05), so over-pulling overshoots the target
    result, _ = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=30,
                                                      export_strength=0.1))

    assert ssim(image_from_numpy(target), result) >= 0.30


def test_bw_more_pulls_not_worse():
    img = synthetic_disk()
    target = gray_target(img)

    # pinned to 0.1 so the comparison isolates the pull count
    result_30, _ = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=30,
                                                         export_strength=0.1))
    result_150, _ = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=150,
                                                          export_strength=0.1))

    assert mse(image_to_numpy(result_150), target) <= 0.8 * mse(image_to_numpy(result_30), target)


def test_bw_structure_preserved():
    img = synthetic_two_blobs()
    blob_1 = (R - 20) ** 2 + (C - 20) ** 2 < 9 ** 2
    blob_2 = (R > 44) & (C > 40) & (C < 60)
    corner_background = (R < 12) & (C > 52)

    result, _ = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=150))
    arr = image_to_numpy(result)

    # both regions must render darker than untouched background — the picture is
    # spatially recognizable, not uniformly darkened
    assert arr[blob_1].mean() < arr[corner_background].mean() - 0.25
    assert arr[blob_2].mean() < arr[corner_background].mean() - 0.25


def test_pull_order_is_valid():
    img = synthetic_disk()

    _, order = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=150))

    assert order[0] == 0
    assert all(0 <= idx < len(NAILS) for idx in order)
    assert all(a != b for a, b in zip(order, order[1:]))  # no zero-length pulls


def test_rgb_reduces_error_per_channel():
    img = synthetic_color()
    reference = image_to_numpy(img)

    # pinned to the historical default 0.1 (thresholds calibrated for it)
    result, _ = generate_rgb(img, SHAPE, NAILS, Config(side_len=64, pull_amount=100,
                                                       export_strength=0.1))

    for channel in range(3):
        blank_mse = mse(np.ones(SHAPE), reference[:, :, channel])
        # measured factors: R 0.51, G 0.46, B 0.51
        assert mse(image_to_numpy(result)[:, :, channel], reference[:, :, channel]) \
            <= 0.7 * blank_mse, f"channel {channel} failed quality acceptance"


def test_cli_bw_quality(tmp_path):
    img = synthetic_disk()
    input_file = tmp_path / "input.png"
    output_file = tmp_path / "output.png"
    save_image(input_file, image_to_numpy(img))

    # -s 0.1: thresholds calibrated for the historical default (auto 1/L fit
    # targets the 300 px grid, see docs/tuning.md)
    main(["-i", str(input_file), "-o", str(output_file), "-d", "64", "-n", "4", "-l", "150",
          "-s", "0.1"])

    result = load_gray(output_file)
    assert result.shape == (64, 64)
    assert 0.0 <= result.min() and result.max() <= 1.0

    target = gray_target(img)
    blank_mse = mse(np.ones(SHAPE), target)
    assert mse(result, target) <= 0.45 * blank_mse  # measured: 0.029 (0.36x blank)

    # the disk region must come out darker than the background
    assert result[DISK_MASK].mean() < result[BACKGROUND_MASK].mean() - 0.35


def test_cli_rgb_quality(tmp_path):
    img = synthetic_color()
    input_file = tmp_path / "input.png"
    output_file = tmp_path / "output.png"
    save_image(input_file, image_to_numpy(img))

    main(["-i", str(input_file), "-o", str(output_file), "-d", "64", "-n", "4", "-l", "100",
          "--rgb", "-s", "0.1"])

    result = load_rgb(output_file)
    assert result.shape == (64, 64, 3)

    reference = image_to_numpy(img)
    for channel in range(3):
        blank_mse = mse(np.ones(SHAPE), reference[:, :, channel])
        # measured factors: R 0.58, G 0.57, B 0.61
        assert mse(result[:, :, channel], reference[:, :, channel]) <= 0.75 * blank_mse, \
            f"channel {channel} failed quality acceptance"


def test_cli_weight_flag_concentrates_threads(tmp_path):
    """--weight must pull threads toward the image center. Fixture: one blob
    at the center, one bar at the corner. Weighting serves the center blob
    and starves the corner bar. Measured: disk 0.0545 -> 0.0216, bar
    0.3639 -> 0.4660 (brighter = less ink)."""
    img = synthetic_two_blobs()
    input_file = tmp_path / "input.png"
    save_image(input_file, image_to_numpy(img))

    plain_file = tmp_path / "plain.png"
    weighted_file = tmp_path / "weighted.png"
    main(["-i", str(input_file), "-o", str(plain_file), "-d", "64", "-n", "4", "-l", "300"])
    main(["-i", str(input_file), "-o", str(weighted_file), "-d", "64", "-n", "4", "-l", "300",
          "--weight", "3"])

    plain = load_gray(plain_file)
    weighted = load_gray(weighted_file)

    # central blob stays at least as dark, corner bar loses ink
    blob = (R - 20) ** 2 + (C - 20) ** 2 < 9 ** 2
    bar = (R > 44) & (C > 40) & (C < 60)
    assert weighted[blob].mean() < plain[blob].mean()
    assert weighted[bar].mean() > plain[bar].mean() + 0.05


def test_min_chord_removes_short_chords():
    """min_chord must ban sub-threshold chords from the pull order. Fixture:
    seeded noise on the 44-nail circle, threshold 40 px (the unfiltered
    order reaches down to a 30.8 px chord, so the ban changes the sequence).
    No dead ends occur on this layout, so every chord must clear the bar."""
    rng = np.random.default_rng(5)
    img = image_from_numpy(rng.random((64, 64, 3)))

    _, plain_order = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=400))
    _, filtered_order = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=400,
                                                              min_chord=40.0))

    assert filtered_order != plain_order
    pts = [NAILS[j] for j in filtered_order]
    for (r1, c1), (r2, c2) in zip(pts, pts[1:]):
        assert math.hypot(r2 - r1, c2 - c1) >= 40.0
