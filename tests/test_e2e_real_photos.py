"""E2E quality acceptance tests on real portrait photos.

The fixtures in tests/data/ are portrait photos from Unsplash
(https://unsplash.com/s/photos/people), used under the Unsplash License.

Real photos are harder for the algorithm than the synthetic fixtures in
test_e2e_quality.py, so thresholds here are calibrated separately — measured
values are noted next to each threshold, with a safety margin. The greedy
pipeline is deterministic, so the numbers are stable across runs.
"""

from pathlib import Path

import matplotlib.image as mpimg
import numpy as np
import pytest
from skimage.transform import resize

from restring.canvas import init_canvas, pull_order_to_array_bw
from restring.cli import main
from restring.generator import Config, generate_bw
from restring.image_transformations import largest_square, rgb2gray
from restring.nails import create_circle_nail_positions

DATA = Path(__file__).parent / "data"
PHOTOS = sorted(DATA.glob("portrait_*.jpg"))
SHAPE = (64, 64)
NAILS = create_circle_nail_positions(SHAPE, nail_step=4)


def load_reference(path):
    """Mirror the CLI preprocessing: normalize, square-crop, downscale to 64x64."""
    img = mpimg.imread(path)
    if np.any(img > 100):  # uint8 JPEG -> 0..1, same check as restring.cli
        img = img / 255
    return resize(largest_square(img), SHAPE)


def mse(a, b):
    return float(np.mean((a - b) ** 2))


def corr(a, b):
    return float(np.corrcoef(a.ravel(), b.ravel())[0, 1])


def test_portrait_fixtures_present():
    # guard against the photo fixtures getting lost
    assert len(PHOTOS) >= 3, f"expected >=3 portrait fixtures in {DATA}, found {len(PHOTOS)}"


@pytest.mark.parametrize("photo", PHOTOS, ids=lambda p: p.name)
def test_cli_bw_portrait_quality(photo, tmp_path):
    reference = rgb2gray(load_reference(photo))
    output_file = tmp_path / "output.png"

    main(["-i", str(photo), "-o", str(output_file), "-d", "64", "-n", "4", "-l", "300"])

    result = rgb2gray(mpimg.imread(output_file)[..., :3])
    blank_mse = mse(np.ones(SHAPE), reference)
    assert mse(result, reference) <= 0.65 * blank_mse  # measured: 0.38-0.53
    assert corr(result, reference) >= 0.35  # measured: 0.46-0.57


def test_cli_rgb_portrait_quality(tmp_path):
    photo = DATA / "portrait_woman_1.jpg"
    reference = load_reference(photo)
    output_file = tmp_path / "output.png"

    main(["-i", str(photo), "-o", str(output_file), "-d", "64", "-n", "4", "-l", "150", "--rgb"])

    result = mpimg.imread(output_file)[..., :3]
    for channel in range(3):
        blank_mse = mse(np.ones(SHAPE), reference[:, :, channel])
        # measured factors: 0.51-0.54
        assert mse(result[:, :, channel], reference[:, :, channel]) <= 0.7 * blank_mse, \
            f"channel {channel} failed quality acceptance on a real portrait"


def test_greedy_beats_random_on_portrait():
    photo = DATA / "portrait_man_1.jpg"
    reference = rgb2gray(load_reference(photo))

    result, order = generate_bw(load_reference(photo), SHAPE, NAILS, Config(side_len=64, pull_amount=150))
    greedy_mse = mse(result, reference)

    for seed in (0, 1, 2):
        rng = np.random.default_rng(seed)
        random_order = [0] + list(rng.integers(0, len(NAILS), size=len(order) - 1))
        random_result = pull_order_to_array_bw(random_order, init_canvas(SHAPE), NAILS, -0.1)
        # measured greedy/random ratio: 0.70-0.78 — real photos leave less headroom
        # than synthetic fixtures, but guided pulling must still win clearly
        assert greedy_mse <= 0.9 * mse(random_result, reference), \
            f"greedy failed to beat random threads on a real portrait (seed={seed})"


def test_cli_output_deterministic(tmp_path):
    photo = DATA / "portrait_woman_2.jpg"
    outputs = []
    for run in range(2):
        output_file = tmp_path / f"output_{run}.png"
        main(["-i", str(photo), "-o", str(output_file), "-d", "64", "-n", "4", "-l", "100"])
        outputs.append(mpimg.imread(output_file))

    assert np.array_equal(outputs[0], outputs[1])
