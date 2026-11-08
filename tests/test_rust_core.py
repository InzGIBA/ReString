"""Rust core (_core) golden tests.

The pure-Python reference implementations are gone (the pipeline is
Rust-only), so correctness is pinned with frozen golden data captured from
the verified implementation (which was, in turn, proven byte-identical to
skimage's rasterizer and to the former numpy reference — see
docs/optimization.md). Any change in rasterization, tie-breaking or subset
seeding must consciously update these goldens.
"""

import numpy as np
import pytest

from _helpers import image_from_numpy, image_to_numpy
from restring import _core
from restring.canvas import init_canvas, line_aa, pull_order_to_array_bw
from restring.generator import create_art
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


def test_backend_is_deterministic():
    rng = np.random.default_rng(3)
    target = image_from_numpy(rng.random(SHAPE) * 0.8 + 0.1)

    order_a, _ = create_art(NAILS, target, init_canvas(SHAPE), -0.05, i_limit=200)
    order_b, _ = create_art(NAILS, target, init_canvas(SHAPE), -0.05, i_limit=200)

    assert order_a == order_b


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
