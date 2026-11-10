"""Rust core (_core) golden tests.

The pure-Python reference implementations are gone (the pipeline is
Rust-only), so correctness is pinned with frozen golden data captured from
the verified implementation (which was, in turn, proven byte-identical to
skimage's rasterizer and to the former numpy reference — see
docs/optimization.md). Any change in rasterization, tie-breaking or subset
seeding must consciously update these goldens.
"""

import math

import numpy as np
import pytest

from _helpers import image_from_numpy, image_to_numpy
from restring import _core
from restring.canvas import init_canvas, line_aa, pull_order_to_array_bw
from restring.generator import Config, create_art, generate_bw, generate_rgb
from restring.nails import create_circle_nail_positions

pytestmark = pytest.mark.skipif(_core is None, reason="Rust core not built")

SHAPE = (64, 64)
NAILS = create_circle_nail_positions(SHAPE, nail_step=4)

# Frozen rasterizer outputs (Zingl): segment -> (rr, cc, val) with values
# rounded to 12 decimals. Axis-aligned lines are runs of full coverage;
# the 45-degree diagonal carries the characteristic 0.2929 pair weights.
LINE_AA_GOLDENS = [
    ((0, 0, 0, 7), [0] * 8, list(range(8)), [1.0] * 8),
    ((0, 0, 7, 0), list(range(8)), [0] * 8, [1.0] * 8),
    ((0, 0, 7, 7),
     [0, 1, 0, 1, 2, 1, 2, 3, 2, 3, 4, 3, 4, 5, 4, 5, 6, 5, 6, 7, 6, 7],
     [0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6, 7, 7],
     [1.0, 0.292893218813, 0.292893218813] * 7 + [1.0]),
]

LINE_AA_CHECKSUMS = [
    # (segment, pixel count, first pixel, last pixel, total ink) — measured
    ((2, 3, 41, 29), 92, (2, 3), (41, 29), 48.733385),
    ((0, 0, 63, 31), 142, (0, 0), (63, 31), 71.216354),
    ((10, 50, 55, 5), 136, (10, 50), (55, 5), 72.360390),
]


@pytest.mark.parametrize("golden", LINE_AA_GOLDENS)
def test_line_aa_golden_exact(golden):
    seg, rr, cc, val = golden
    got = line_aa(*seg)
    assert list(got[0]) == rr
    assert list(got[1]) == cc
    assert np.allclose(got[2], val, atol=1e-9)


# Frozen thick-segment outputs: (segment, half_width, rr, cc, coverage) with
# coverage rounded to 12 decimals. Pixel centers sit on integer coordinates,
# so a horizontal segment at hw 0.5 covers its row fully (distance 0), the
# neighbor rows at half (distance 1: 1 - (1 - 0.5)), and the endcap corners
# at 1 - (sqrt(2) - 0.5) = 0.0858. Sum of coverage approximates width * length.
THICK_LINE_GOLDENS = [
    ((0, 0, 7, 0), 0.5,
     [-1, -1, -1, 0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6, 7, 7, 7, 8, 8, 8],
     [-1, 0, 1, -1, 0, 1, -1, 0, 1, -1, 0, 1, -1, 0, 1, -1, 0, 1, -1, 0, 1, -1, 0, 1, -1, 0, 1, -1, 0, 1],
     [0.085786437627, 0.5, 0.085786437627, 0.5, 1.0, 0.5, 0.5, 1.0, 0.5, 0.5, 1.0, 0.5, 0.5, 1.0, 0.5,
      0.5, 1.0, 0.5, 0.5, 1.0, 0.5, 0.5, 1.0, 0.5, 0.5, 1.0, 0.5, 0.085786437627, 0.5, 0.085786437627]),
    ((0, 0, 7, 7), 1.0,
     [-1, -1, -1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 5, 5, 5, 5,
      5, 6, 6, 6, 6, 6, 7, 7, 7, 7, 8, 8, 8],
     [-1, 0, 1, -1, 0, 1, 2, -1, 0, 1, 2, 3, 0, 1, 2, 3, 4, 1, 2, 3, 4, 5, 2, 3, 4, 5, 6, 3, 4, 5, 6,
      7, 4, 5, 6, 7, 8, 5, 6, 7, 8, 6, 7, 8],
     [0.585786437627, 1.0, 0.585786437627, 1.0, 1.0, 1.0, 0.585786437627, 0.585786437627, 1.0, 1.0,
      1.0, 0.585786437627, 0.585786437627, 1.0, 1.0, 1.0, 0.585786437627, 0.585786437627, 1.0, 1.0,
      1.0, 0.585786437627, 0.585786437627, 1.0, 1.0, 1.0, 0.585786437627, 0.585786437627, 1.0, 1.0,
      1.0, 0.585786437627, 0.585786437627, 1.0, 1.0, 1.0, 0.585786437627, 0.585786437627, 1.0, 1.0,
      1.0, 0.585786437627, 1.0, 0.585786437627]),
    ((0, 0, 5, 2), 1.5,
     [-2, -2, -2, -1, -1, -1, -1, -1, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3,
      4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 7, 7, 7],
     [-1, 0, 1, -2, -1, 0, 1, 2, -2, -1, 0, 1, 2, -2, -1, 0, 1, 2, 3, -1, 0, 1, 2, 3, -1, 0, 1, 2, 3,
      -1, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 1, 2, 3],
     [0.2639320225, 0.5, 0.2639320225, 0.2639320225, 1.0, 1.0, 1.0, 0.2639320225, 0.5, 1.0, 1.0, 1.0,
      0.643046618229, 0.271655941875, 1.0, 1.0, 1.0, 1.0, 0.085960603698, 0.828741956407, 1.0, 1.0,
      1.0, 0.457351280052, 0.457351280052, 1.0, 1.0, 1.0, 0.828741956407, 0.085960603698, 1.0, 1.0,
      1.0, 1.0, 0.271655941875, 0.643046618229, 1.0, 1.0, 1.0, 0.5, 0.2639320225, 1.0, 1.0, 1.0,
      0.2639320225, 0.2639320225, 0.5, 0.2639320225]),
    ((3, 3, 3, 3), 1.0,
     [2, 2, 2, 3, 3, 3, 4, 4, 4],
     [2, 3, 4, 2, 3, 4, 2, 3, 4],
     [0.585786437627, 1.0, 0.585786437627, 1.0, 1.0, 1.0, 0.585786437627, 1.0, 0.585786437627]),
]


@pytest.mark.parametrize("golden", THICK_LINE_GOLDENS)
def test_thick_line_golden_exact(golden):
    seg, hw, rr, cc, cov = golden
    got_rr, got_cc, got_cov = _core.thick_line(*seg, hw)
    assert list(got_rr) == rr
    assert list(got_cc) == cc
    assert np.allclose(got_cov, cov, atol=1e-11)


def test_gradient_magnitude_hand_computed():
    # horizontal ramp value = column: the interior Sobel response is
    # Gx = -4 * (c-1) + 4 * (c+1) = 8, edge pixels clamp to half (4)
    ramp = image_from_numpy([[float(c) for c in range(5)] for _ in range(5)])
    mag = image_to_numpy(_core.gradient_magnitude(ramp))
    assert np.allclose(mag, [[4.0, 8.0, 8.0, 8.0, 4.0]] * 5)


@pytest.mark.parametrize("golden", LINE_AA_CHECKSUMS)
def test_line_aa_golden_checksums(golden):
    seg, count, first, last, ink = golden
    rr, cc, val = line_aa(*seg)
    assert len(rr) == count
    assert (rr[0], cc[0]) == first and (rr[-1], cc[-1]) == last
    assert abs(sum(val) - ink) < 1e-6  # total ink == major-axis length + 1


# Frozen greedy pull order: seeded random target, 44 circle nails, 400 iters.
FULL_ORDER = [
    0, 21, 2, 23, 42, 19, 43, 19, 37, 14, 38, 15, 34, 10, 32, 13, 35, 14, 38,
    16, 40, 17, 39, 11, 30, 7, 36, 17, 33, 10, 28, 7, 26, 3, 24, 1, 26, 5, 28,
    6, 26, 4, 30, 5, 25, 1, 22, 37, 20, 1, 17, 39, 14, 33, 11, 35, 8, 27, 3,
    24, 0, 27, 3, 24, 37, 18, 40, 16, 43, 22, 6, 34, 7, 29, 9, 34, 15, 32, 6,
    35, 14, 37, 23, 4, 29, 11, 39, 24, 1, 27, 12, 36, 7, 21, 5, 24, 13, 28, 8,
    26, 40, 22, 2, 30, 4, 21, 34, 17, 41, 13, 0, 29, 6, 23, 36, 17, 1, 19, 7,
    31, 9, 26, 42, 23, 8, 27, 2, 29, 15, 33, 4, 20, 43, 27, 12, 38, 11, 23,
    36, 7, 21, 40, 24, 13, 40, 11, 41, 10, 32, 16, 37, 24, 42, 14, 31, 17, 3,
    26, 40, 19, 35, 5, 18, 41, 14, 38, 22, 5, 31, 19, 8, 26, 4, 32, 19, 9, 23,
    2, 34, 7, 29, 17, 33, 43, 30, 13, 2, 18, 33, 9, 36, 15, 37, 6, 25, 10, 28,
    13, 0, 30, 2, 31, 12, 41, 25, 3, 16, 35, 24, 7, 19, 33, 22, 11, 37, 21,
    10, 38, 9, 40, 8, 24, 13, 22, 37, 3, 29, 5, 26, 1, 34, 4, 15, 39, 20, 36,
    23, 11, 27, 41, 10, 34, 21, 0, 26, 38, 16, 1, 13, 39, 6, 18, 42, 25, 34,
    6, 27, 14, 43, 33, 16, 42, 28, 15, 35, 17, 7, 23, 31, 22, 13, 2, 35, 24,
    11, 36, 22, 10, 37, 19, 31, 43, 8, 19, 28, 5, 23, 4, 39, 28, 12, 35, 3,
    30, 17, 43, 15, 4, 18, 37, 27, 39, 8, 43, 32, 1, 30, 20, 10, 2, 11, 43,
    13, 26, 40, 16, 26, 6, 21, 35, 7, 17, 31, 13, 22, 34, 0, 10, 30, 23, 41,
    7, 26, 37, 3, 31, 23, 12, 36, 1, 23, 9, 24, 38, 28, 7, 40, 33, 7, 21, 13,
    4, 29, 41, 15, 31, 20, 29, 17, 27, 3, 34, 13, 5, 18, 7, 37, 20, 9, 37,
    30, 23, 32, 0, 37, 17, 7, 41, 19, 9, 0, 12, 26, 14, 23, 39, 6, 37, 25,
    34, 43, 19, 27, 37, 14, 22, 33, 43, 22, 17, 6,
]

# Frozen subset-mode order: different seeded target, random_nails=20, 300 iters
# (subset drawn by the core's splitmix64+Floyd sampler, seed 42).
SUBSET_ORDER = [
    0, 22, 41, 16, 39, 15, 38, 13, 36, 12, 36, 16, 35, 12, 38, 13, 34, 8, 28,
    8, 29, 10, 28, 5, 23, 1, 22, 5, 34, 16, 39, 18, 41, 15, 34, 12, 36, 18,
    35, 13, 39, 12, 29, 4, 23, 1, 29, 4, 28, 8, 34, 16, 38, 10, 28, 1, 29, 8,
    36, 16, 41, 23, 39, 15, 35, 10, 41, 22, 4, 23, 38, 15, 36, 5, 22, 1, 18,
    34, 22, 39, 13, 29, 10, 36, 13, 34, 15, 28, 41, 10, 39, 8, 35, 16, 4, 35,
    18, 39, 12, 38, 8, 28, 16, 1, 28, 5, 34, 22, 36, 12, 41, 15, 29, 12, 35,
    23, 8, 41, 18, 4, 29, 5, 36, 23, 39, 16, 28, 12, 22, 8, 39, 15, 1, 13, 38,
    16, 35, 13, 29, 1, 23, 5, 16, 4, 34, 18, 36, 10, 41, 28, 10, 22, 35, 5,
    18, 1, 13, 28, 16, 41, 23, 34, 16, 29, 41, 8, 34, 10, 38, 23, 34, 12, 41,
    22, 4, 36, 16, 5, 39, 22, 34, 18, 39, 10, 23, 36, 8, 39, 29, 8, 41, 15,
    28, 4, 39, 28, 41, 10, 1, 36, 15, 29, 18, 41, 13, 39, 23, 8, 22, 10, 29,
    39, 5, 22, 12, 1, 22, 36, 12, 39, 16, 1, 8, 38, 23, 35, 10, 1, 29, 41, 8,
    28, 16, 29, 12, 23, 34, 15, 1, 36, 5, 28, 22, 13, 36, 29, 5, 38, 15, 35,
    18, 29, 39, 1, 8, 16, 5, 18, 36, 4, 23, 28, 1, 12, 22, 13, 34, 5, 23, 10,
    41, 23, 28, 18, 38, 12, 28, 38, 4, 39, 1, 10, 39, 28, 22, 15, 5, 38, 13,
    29, 36, 1, 23, 34, 16, 4, 18, 29, 4, 35, 22,
]


# Frozen importance-weighted order: same fixture as the full-scan golden, Gaussian weight map
# (sigma 64/3, peak 3, bg 0.5), 400 iters.
WEIGHTED_ORDER = [
    0, 21, 0, 24, 3, 27, 3, 24, 1, 22, 43, 19, 43, 20, 1, 26, 5, 28, 7, 30, 11, 33, 14, 37, 14,
    38, 15, 34, 10, 32, 10, 28, 6, 26, 4, 23, 2, 27, 8, 26, 3, 24, 1, 19, 42, 23, 42, 18, 40,
    16, 38, 14, 35, 11, 34, 7, 29, 9, 31, 12, 36, 17, 39, 17, 1, 27, 8, 35, 13, 32, 6, 29, 4,
    30, 5, 25, 6, 34, 9, 33, 17, 36, 7, 26, 5, 31, 14, 35, 16, 40, 22, 2, 21, 5, 24, 42, 26,
    40, 17, 41, 23, 2, 30, 13, 28, 8, 26, 3, 21, 42, 14, 39, 11, 37, 19, 40, 24, 39, 20, 37,
    16, 43, 17, 34, 15, 32, 16, 40, 13, 41, 18, 37, 10, 28, 5, 22, 37, 15, 36, 7, 31, 6, 23,
    36, 7, 21, 4, 33, 15, 39, 11, 29, 2, 27, 12, 38, 22, 6, 35, 19, 37, 24, 7, 30, 10, 25, 1,
    17, 31, 3, 17, 33, 10, 38, 11, 40, 26, 9, 36, 12, 28, 13, 24, 43, 27, 12, 35, 5, 18, 2, 31,
    15, 29, 0, 13, 31, 19, 43, 15, 41, 25, 42, 20, 36, 23, 8, 29, 3, 25, 40, 21, 7, 34, 21, 35,
    17, 30, 4, 20, 0, 13, 24, 37, 6, 34, 2, 30, 9, 38, 15, 42, 11, 23, 37, 21, 10, 41, 14, 43,
    22, 34, 13, 2, 17, 29, 7, 19, 8, 33, 18, 4, 32, 19, 1, 32, 13, 26, 40, 9, 23, 5, 35, 24, 9,
    19, 39, 23, 4, 15, 28, 42, 26, 38, 24, 8, 40, 11, 36, 7, 33, 43, 30, 14, 27, 11, 22, 10,
    41, 11, 23, 36, 5, 18, 1, 30, 0, 25, 6, 39, 27, 41, 29, 5, 16, 3, 37, 20, 10, 27, 6, 18,
    30, 3, 27, 37, 22, 13, 1, 34, 21, 7, 17, 31, 22, 33, 43, 8, 19, 41, 12, 37, 6, 26, 0, 33,
    16, 1, 26, 4, 39, 28, 19, 7, 23, 32, 0, 27, 17, 7, 26, 14, 24, 35, 2, 13, 24, 11, 43, 31,
    19, 29, 4, 34, 25, 8, 38, 28, 7, 41, 30, 23, 9, 19, 33, 12, 3, 37, 26, 16, 37, 9, 0, 34, 3,
    15, 35, 3, 13, 22, 13, 39, 6, 21, 30, 23, 12, 26, 39, 8, 43, 13,
]


def test_greedy_order_golden_weighted():
    rng = np.random.default_rng(5)
    target = image_from_numpy(rng.random(SHAPE) * 0.8 + 0.1)
    weights = _core.gaussian_weights(64, 64, SHAPE[0] / 3, 3.0, 0.5)

    order, _ = create_art(NAILS, target, init_canvas(SHAPE), -0.05, i_limit=400, weights=weights)

    assert order == WEIGHTED_ORDER


def test_weighted_search_supports_random_nails():
    # the merged weighted path keeps subset scanning (weighted_search lacks it)
    rng = np.random.default_rng(9)
    target = image_from_numpy(rng.random(SHAPE) * 0.8 + 0.1)
    weights = _core.gaussian_weights(64, 64, 16.0, 3.0, 0.5)

    order_a, _ = create_art(NAILS, target, init_canvas(SHAPE), -0.05,
                            i_limit=300, random_nails=20, weights=weights)
    order_b, _ = create_art(NAILS, target, init_canvas(SHAPE), -0.05,
                            i_limit=300, random_nails=20, weights=weights)

    assert order_a == order_b
    assert order_a != SUBSET_ORDER  # weighting changed the choices


def test_gaussian_weights_values():
    w = _core.gaussian_weights(64, 64, 16.0, 3.0, 0.5)
    assert w.shape() == (64, 64, 1)
    # center sits at (w/2, h/2) = (32, 32), value == peak
    assert abs(w.pixel(32, 32, 0) - 3.0) < 1e-12
    # corner: d^2 = 2048, w = bg + (peak - bg) * exp(-2048 / (2 * 16^2))
    expected = 0.5 + 2.5 * math.exp(-4.0)
    assert abs(w.pixel(0, 0, 0) - expected) < 1e-12


# Frozen minimum-chord order: same fixture as the full-scan golden, min_chord
# 30 px (chords below 30 px are banned, dead ends recover via masked-out pulls), 400 iters.
MIN_CHORD_ORDER = [0, 21, 2, 23, 42, 19, 43, 19, 37, 14, 38, 15, 34, 10, 32, 13, 35, 14, 38, 16,
    40, 17, 39, 11, 30, 7, 36, 17, 33, 10, 28, 7, 26, 3, 24, 1, 26, 5, 28, 6, 26, 4, 30, 5, 25, 1,
    22, 37, 20, 1, 17, 39, 14, 33, 11, 35, 8, 27, 3, 24, 0, 27, 3, 24, 37, 18, 40, 16, 43, 22, 6,
    34, 7, 29, 9, 34, 15, 32, 6, 35, 14, 37, 23, 4, 29, 11, 39, 24, 1, 27, 12, 36, 7, 21, 5, 24,
    13, 28, 8, 26, 40, 22, 2, 30, 4, 21, 34, 17, 41, 13, 0, 29, 6, 23, 36, 17, 1, 19, 7, 31, 9,
    26, 42, 23, 8, 27, 2, 29, 15, 33, 4, 20, 43, 27, 12, 38, 11, 23, 36, 7, 21, 40, 24, 13, 40,
    11, 41, 10, 32, 16, 37, 24, 42, 14, 31, 17, 3, 26, 40, 19, 35, 5, 18, 41, 14, 38, 22, 5, 31,
    19, 8, 26, 4, 32, 19, 9, 23, 2, 34, 7, 29, 17, 33, 43, 30, 13, 2, 18, 33, 9, 36, 15, 37, 6,
    25, 10, 28, 13, 0, 30, 2, 31, 12, 41, 25, 3, 16, 35, 24, 7, 19, 33, 22, 11, 37, 21, 10, 38, 9,
    40, 8, 24, 13, 22, 37, 3, 29, 5, 26, 1, 34, 4, 15, 39, 20, 36, 23, 11, 27, 41, 10, 34, 21, 0,
    26, 38, 16, 1, 13, 39, 6, 18, 42, 25, 34, 6, 27, 14, 43, 33, 16, 42, 28, 15, 35, 17, 7, 23,
    31, 22, 13, 2, 35, 24, 11, 36, 22, 10, 37, 19, 31, 43, 8, 19, 28, 5, 23, 4, 39, 28, 12, 35, 3,
    30, 17, 43, 15, 4, 18, 37, 27, 39, 8, 43, 32, 1, 30, 20, 10, 2, 11, 43, 13, 26, 40, 16, 26, 6,
    21, 35, 7, 17, 31, 13, 22, 34, 0, 10, 30, 23, 41, 7, 26, 37, 3, 31, 23, 12, 36, 1, 23, 9, 24,
    38, 28, 7, 40, 33, 7, 21, 13, 4, 29, 41, 15, 31, 20, 29, 17, 27, 3, 34, 13, 5, 18, 7, 37, 20,
    9, 37, 0, 32, 23, 14, 26, 42, 11, 23, 30, 41, 19, 9, 0, 12, 3, 21, 33, 40, 32, 19, 39, 23, 30,
    7, 40, 14, 22, 31, 1, 19, 27]


# Frozen RGB channel orders: seeded noise target, 44 circle nails, working
# strength 0.05 (docs/research/rgb-channels-experiment.md), 150 iters per
# channel, auto export. Padded to the longest channel.
RGB_ORDERS_GOLDEN = [
    [0, 17, 2, 23, 1, 20, 5, 26, 4, 30, 7, 30, 8, 31, 12, 38, 16, 37, 12, 33, 11, 35, 11, 32, 14,
     31, 12, 30, 7, 26, 2, 18, 42, 26, 5, 22, 6, 29, 6, 32, 5, 20, 38, 15, 36, 8, 29, 11, 27, 10,
     28, 43, 23, 40, 24, 1, 23, 2, 21, 39, 15, 36, 12, 34, 9, 31, 16, 41, 19, 39, 21, 3, 23, 43,
     28, 10, 38, 12, 31, 8, 33, 15, 37, 13, 34, 18, 2, 17, 43, 25, 0, 16, 35, 8, 25, 7, 27, 9, 22,
     6, 24, 38, 17, 0, 26, 40, 20, 4, 32, 19, 42, 16, 1, 29, 13, 31, 4, 32, 7, 28, 8, 36, 18, 0,
     24, 41, 11, 32, 5, 22, 9, 39, 15, 29, 6, 35, 21, 37, 19, 4, 36, 21, 1, 30, 14, 42, 26, 4, 21,
     39, 10],
    [0, 26, 3, 23, 3, 27, 5, 24, 3, 27, 7, 28, 5, 25, 4, 26, 2, 21, 42, 19, 42, 15, 32, 13, 36,
     10, 30, 10, 37, 12, 35, 12, 31, 9, 29, 9, 32, 16, 40, 23, 38, 17, 1, 18, 0, 28, 3, 19, 4, 31,
     11, 32, 16, 34, 13, 39, 12, 37, 18, 36, 14, 37, 9, 33, 17, 1, 22, 43, 24, 41, 21, 1, 18, 34,
     15, 30, 7, 23, 40, 21, 2, 33, 6, 31, 9, 27, 10, 38, 17, 1, 22, 43, 26, 0, 24, 8, 28, 12, 27,
     4, 20, 41, 23, 38, 14, 33, 7, 31, 4, 19, 34, 3, 34, 12, 25, 42, 16, 36, 10, 35, 18, 0, 27,
     12, 40, 16, 1, 12, 42, 9, 30, 2, 20, 33, 20, 39, 13, 37, 6, 27, 10, 43, 28, 15, 32, 13, 29,
     42, 21, 37, 11],
    [0, 21, 39, 18, 39, 16, 40, 17, 39, 21, 4, 24, 3, 21, 38, 19, 2, 26, 5, 22, 1, 27, 10, 34, 12,
     35, 15, 37, 18, 43, 23, 42, 20, 5, 25, 42, 16, 3, 32, 6, 29, 11, 26, 43, 15, 35, 13, 33, 7,
     28, 0, 19, 4, 28, 5, 31, 7, 30, 13, 36, 10, 30, 2, 31, 13, 33, 7, 22, 38, 12, 28, 11, 39, 14,
     38, 16, 3, 24, 41, 25, 1, 19, 38, 15, 36, 9, 37, 7, 22, 5, 20, 4, 30, 8, 33, 14, 42, 23, 40,
     27, 6, 22, 0, 12, 29, 11, 36, 8, 25, 9, 31, 2, 26, 11, 39, 21, 3, 32, 10, 40, 24, 0, 28, 42,
     20, 7, 28, 42, 17, 39, 18, 1, 16, 30, 15, 43, 29, 2, 15, 31, 1, 22, 38, 8, 26, 9, 34, 14, 3,
     27, 40]
]


def test_rgb_orders_golden():
    rng = np.random.default_rng(5)
    img = image_from_numpy(rng.random((64, 64, 3)))

    _, orders = generate_rgb(img, SHAPE, NAILS, Config(side_len=64, pull_amount=150))

    assert orders == RGB_ORDERS_GOLDEN
    assert len(orders[0]) == len(orders[1]) == len(orders[2])  # padded to the max


def test_greedy_order_golden_full_scan():
    rng = np.random.default_rng(5)
    target = image_from_numpy(rng.random(SHAPE) * 0.8 + 0.1)

    order, _ = create_art(NAILS, target, init_canvas(SHAPE), -0.05, i_limit=400)

    assert order == FULL_ORDER


def test_greedy_order_golden_random_subset():
    rng = np.random.default_rng(9)
    target = image_from_numpy(rng.random(SHAPE) * 0.8 + 0.1)

    order, _ = create_art(NAILS, target, init_canvas(SHAPE), -0.05,
                          i_limit=300, random_nails=20)

    assert order == SUBSET_ORDER


def test_greedy_order_golden_min_chord():
    rng = np.random.default_rng(5)
    target = image_from_numpy(rng.random(SHAPE) * 0.8 + 0.1)

    order, _ = create_art(NAILS, target, init_canvas(SHAPE), -0.05, i_limit=400, min_chord=30.0)

    assert order == MIN_CHORD_ORDER
    # the threshold bites: the unfiltered golden contains a 21 px chord
    assert order != FULL_ORDER
    pts = [NAILS[j] for j in order]
    for (r1, c1), (r2, c2) in zip(pts, pts[1:]):
        assert math.hypot(r2 - r1, c2 - c1) >= 30.0


def test_min_chord_dead_end_recovery(caplog):
    # three corner nails, min_chord above the largest pairwise distance:
    # every candidate is masked out, recovery must keep pulling
    import logging

    rng = np.random.default_rng(9)
    target = image_from_numpy(rng.random(SHAPE) * 0.8 + 0.1)
    sparse = [(0, 0), (0, 63), (63, 0)]  # pairwise distances 63, 63, 89

    with caplog.at_level(logging.DEBUG):
        order, _ = create_art(sparse, target, init_canvas(SHAPE), -0.05,
                              i_limit=50, min_chord=100.0)

    assert len(order) > 1  # a stalling search would return [0]
    assert sum(1 for r in caplog.records if "dead end" in r.message) == 1


def test_backend_is_deterministic():
    rng = np.random.default_rng(3)
    target = image_from_numpy(rng.random(SHAPE) * 0.8 + 0.1)

    order_a, _ = create_art(NAILS, target, init_canvas(SHAPE), -0.05, i_limit=200)
    order_b, _ = create_art(NAILS, target, init_canvas(SHAPE), -0.05, i_limit=200)

    assert order_a == order_b


def test_rollback_prefix_never_worse():
    # stagnation exit (no i_limit): the search runs into failing pulls; with
    # rollback the order truncates to the best prefix and its canvas error is
    # at most the full order's
    rng = np.random.default_rng(5)
    target = image_from_numpy(rng.random(SHAPE) * 0.8 + 0.1)
    full, final_full = create_art(NAILS, target, init_canvas(SHAPE), -0.05)
    short, final_short = create_art(NAILS, target, init_canvas(SHAPE), -0.05, rollback=True)

    assert len(short) <= len(full)
    assert short == full[: len(short)]  # the truncated order is a prefix
    assert _core.mse(final_short, target) <= _core.mse(final_full, target) + 1e-12


def test_circle_nails_semantics():
    nails = _core.circle_nails(64, 64, 4, 1, 1)
    all_nails = _core.circle_nails(64, 64, 1, 1, 1)
    assert all(0 <= r < 64 and 0 <= c < 64 for r, c in nails)
    assert len(nails) == len(all_nails[::4])
    assert nails == all_nails[::4]


def test_render_bw_stays_in_range():
    rng = np.random.default_rng(4)
    order = [0] + list(rng.integers(0, len(NAILS), size=20))
    rendered = pull_order_to_array_bw(order, init_canvas((80, 80)), NAILS, -0.3)
    arr = image_to_numpy(rendered)
    assert arr.min() >= 0.0 and arr.max() <= 1.0


def test_thick_render_ink_conservation():
    # hand-checked: total ink equals strength * sum of segment coverage,
    # no clamping in this brightness range
    order = [0, 1, 2]
    render = pull_order_to_array_bw(order, init_canvas(SHAPE), NAILS, -0.1, thread_px=2.0)
    arr = image_to_numpy(render)
    expected = 0.0
    for a, b in ((0, 1), (1, 2)):
        _, _, cov = _core.thick_line(NAILS[a][0], NAILS[a][1], NAILS[b][0], NAILS[b][1], 1.0)
        expected += sum(cov)
    expected *= 0.1
    assert abs((1.0 - arr).sum() - expected) < 1e-9


def test_thick_render_converges_to_classic_at_subpixel_width():
    # at sub-pixel thread widths the physical model draws the same chords as
    # the classic hairline with a near-identical coverage profile
    rng = np.random.default_rng(5)
    img = image_from_numpy(rng.random((64, 64, 3)))
    classic, classic_order = generate_bw(img, SHAPE, NAILS,
                                         Config(side_len=64, pull_amount=60, export_strength=0.1))
    thick, thick_order = generate_bw(img, SHAPE, NAILS,
                                     Config(side_len=64, pull_amount=60, export_strength=0.1,
                                            realistic=True, thread_width=0.5, canvas_size=64))
    assert thick_order == classic_order  # the flag changes rendering only
    diff = _core.mse(thick, classic)
    assert diff < 0.005  # measured: 0.0043 at thread_px 0.5
