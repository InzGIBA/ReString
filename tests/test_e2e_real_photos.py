"""E2E quality acceptance tests on real portrait photos.

The fixtures in tests/data/ are square face-centered crops of studio portrait
photos (2048x2048, lossless PNG; face located via subject-mask analysis at
crop time). Real photos are harder for the algorithm than the synthetic
fixtures in test_e2e_quality.py, so thresholds here are calibrated separately
— measured values are noted next to each threshold, with a safety margin.
The greedy pipeline is deterministic, so the numbers are stable across runs.
"""

import os
from pathlib import Path

import numpy as np
import pytest

from _helpers import image_to_numpy, load_gray, load_rgb
from restring import _core
from restring.canvas import init_canvas, pull_order_to_array_bw
from restring.cli import main
from restring.generator import Config, generate_bw, resolve_export_strength
from restring.image_transformations import largest_square, resize, rgb2gray
from restring.nails import create_circle_nail_positions, create_rectangle_nail_positions

DATA = Path(__file__).parent / "data"
PHOTOS = sorted(DATA.glob("portrait_*.png"))
SHAPE = (64, 64)
NAILS = create_circle_nail_positions(SHAPE, nail_step=4)
SWEEP_GRID = [0.025, 0.05, 0.075, 0.1, 0.15, 0.2]  # docs/img/params/pulls.json grid


def reference_image(path):
    """Mirror the CLI preprocessing: RGB load, square-crop, downscale to 64x64."""
    return resize(largest_square(_core.Image.load(os.fspath(path))), SHAPE)


def mse(a, b):
    return float(np.mean((a - b) ** 2))


def corr(a, b):
    return float(np.corrcoef(a.ravel(), b.ravel())[0, 1])


def test_portrait_fixtures_present():
    # guard against the photo fixtures getting lost
    assert len(PHOTOS) >= 2, f"expected >=2 portrait fixtures in {DATA}, found {len(PHOTOS)}"


@pytest.mark.parametrize("photo", PHOTOS, ids=lambda p: p.name)
def test_cli_bw_portrait_quality(photo, tmp_path):
    reference = image_to_numpy(rgb2gray(reference_image(photo)))
    output_file = tmp_path / "output.png"

    main(["-i", str(photo), "-o", str(output_file), "-d", "64", "-n", "4", "-l", "300"])

    result = load_gray(output_file)
    blank_mse = mse(np.ones(SHAPE), reference)
    assert mse(result, reference) <= 0.65 * blank_mse  # measured: 0.39-0.52
    assert corr(result, reference) >= 0.45  # measured: 0.58-0.68


def test_cli_rgb_portrait_quality(tmp_path):
    photo = DATA / "portrait_female.png"
    reference = image_to_numpy(reference_image(photo))
    output_file = tmp_path / "output.png"

    main(["-i", str(photo), "-o", str(output_file), "-d", "64", "-n", "4", "-l", "150", "--rgb"])

    result = load_rgb(output_file)
    for channel in range(3):
        blank_mse = mse(np.ones(SHAPE), reference[:, :, channel])
        # measured factors: 0.38-0.43
        assert mse(result[:, :, channel], reference[:, :, channel]) <= 0.6 * blank_mse, \
            f"channel {channel} failed quality acceptance on a real portrait"


def test_greedy_beats_random_on_portrait():
    photo = DATA / "portrait_male.png"
    ref_img = reference_image(photo)
    reference = image_to_numpy(rgb2gray(ref_img))

    result, order = generate_bw(ref_img, SHAPE, NAILS, Config(side_len=64, pull_amount=150))
    greedy_mse = mse(image_to_numpy(result), reference)

    for seed in (0, 1, 2):
        rng = np.random.default_rng(seed)
        random_order = [0] + list(rng.integers(0, len(NAILS), size=len(order) - 1))
        random_result = pull_order_to_array_bw(random_order, init_canvas(SHAPE), NAILS, -0.1)
        # measured greedy/random ratio: 0.61-0.63 — face crops have more usable
        # structure, guided pulling wins clearly
        assert greedy_mse <= 0.8 * mse(image_to_numpy(random_result), reference), \
            f"greedy failed to beat random threads on a real portrait (seed={seed})"


def test_cli_output_deterministic(tmp_path):
    photo = DATA / "portrait_male.png"
    outputs = []
    for run in range(2):
        output_file = tmp_path / f"output_{run}.png"
        main(["-i", str(photo), "-o", str(output_file), "-d", "64", "-n", "4", "-l", "100"])
        outputs.append(load_gray(output_file))

    assert np.array_equal(outputs[0], outputs[1])


def center_mse(a, b):
    """MSE inside the central 50% box, the face region (experiment metric)."""
    box = (slice(a.shape[0] // 4, 3 * a.shape[0] // 4), slice(a.shape[1] // 4, 3 * a.shape[1] // 4))
    return float(np.mean((a[box] - b[box]) ** 2))


@pytest.mark.parametrize("photo", PHOTOS, ids=lambda p: p.name)
@pytest.mark.parametrize("budget", [500, 2000])
def test_auto_export_strength_matches_hand_tuned(photo, budget):
    """Auto -s must land within 2 percent of the best hand-tuned strength at
    the measured budgets. Reference sweep: docs/img/params/pulls.json
    (circle nails step 4, 300 px grid, prefixes of the saturation order)."""
    ref_img = resize(largest_square(_core.Image.load(os.fspath(photo))), (300, 300))
    reference = image_to_numpy(ref_img.gray(0.9))
    nails = create_circle_nail_positions((300, 300), nail_step=4)

    _, order = generate_bw(ref_img, (300, 300), nails,
                           Config(side_len=300, pull_amount=budget))
    pulls = len(order) - 1
    auto = resolve_export_strength(pulls)

    def render_mse(s):
        rendered = pull_order_to_array_bw(order, init_canvas((300, 300)), nails, -s)
        return mse(image_to_numpy(rendered), reference)

    auto_mse = render_mse(auto)
    best_hand = min(render_mse(s) for s in SWEEP_GRID)
    assert auto_mse <= 1.02 * best_hand, \
        f"auto s={auto:.3f} missed the hand-tuned optimum: " \
        f"{auto_mse:.4f} vs best {best_hand:.4f} on {photo.name} at {pulls} pulls"


@pytest.mark.parametrize("photo", PHOTOS, ids=lambda p: p.name)
def test_weight_flag_improves_center_quality(photo):
    """--weight 3 must beat plain greedy inside the central 50% box at 2000
    threads. Measured gains: male 23.7 percent, female 25.0 percent
    (docs/research/alternatives-experiment.md). Threshold 15 percent."""
    ref_img = resize(largest_square(_core.Image.load(os.fspath(photo))), (300, 300))
    reference = image_to_numpy(ref_img.gray(0.9))
    nails = create_rectangle_nail_positions((300, 300), nail_step=4)

    plain, _ = generate_bw(ref_img, (300, 300), nails,
                           Config(side_len=300, pull_amount=2000, export_strength=0.05))
    weighted, _ = generate_bw(ref_img, (300, 300), nails,
                              Config(side_len=300, pull_amount=2000, export_strength=0.05,
                                     weight_peak=3.0))

    plain_center = center_mse(image_to_numpy(plain), reference)
    weighted_center = center_mse(image_to_numpy(weighted), reference)
    # measured: 0.0257 -> 0.0196 (male), 0.0300 -> 0.0225 (female)
    assert weighted_center <= 0.85 * plain_center, \
        f"weighting failed to improve the center box on {photo.name}: " \
        f"{weighted_center:.4f} vs plain {plain_center:.4f}"
