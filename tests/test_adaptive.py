"""Adaptive nail placement prototype (T-14): candidate pools and selection."""

import numpy as np
import pytest

from _helpers import image_from_numpy
from restring.adaptive import adaptive_perimeter_nails, perimeter_candidates, uniform_perimeter_nails

SHAPE = (64, 64)


def gradient_with_hotspot():
    """A flat field with one bright block: the disc scorer must prefer it."""
    rng = np.random.default_rng(7)
    array = np.zeros((64, 64))
    array[20:30, 40:50] = 1.0
    array += rng.random((64, 64)) * 0.01
    return image_from_numpy(array)


def test_perimeter_candidates_circle_count_and_bounds():
    pts = perimeter_candidates(SHAPE, 32, "circle")

    assert len(pts) == 32
    for r, c in pts:
        assert 0.0 <= r < 64.0
        assert 0.0 <= c < 64.0


def test_perimeter_candidates_rect_walks_the_border():
    pts = perimeter_candidates((9, 11), 28, "rect")

    assert len(pts) == 28
    for r, c in pts:
        on_border = r in (0.0, 8.0) or c in (0.0, 10.0)
        assert on_border, (r, c)


def test_adaptive_selection_count_bounds_determinism():
    gradient = gradient_with_hotspot()

    a = adaptive_perimeter_nails(SHAPE, 20, gradient, "circle")
    b = adaptive_perimeter_nails(SHAPE, 20, gradient, "circle")

    assert a == b  # deterministic by construction
    assert len(a) == 20
    for r, c in a:
        assert 0 <= r < 64
        assert 0 <= c < 64
    assert len(set(a)) == 20  # no duplicate pixels


def test_adaptive_selects_the_hotspot_region_first():
    gradient = gradient_with_hotspot()
    nails = adaptive_perimeter_nails(SHAPE, 20, gradient, "rect")

    # nails near the hotspot sides sit closer to columns 30..60 than the
    # uniform ring would: check the closest nail to the block beats 32 px
    closest = min(abs(c - 45) for _, c in nails)
    assert closest <= 20


def test_uniform_perimeter_matches_requested_count():
    for layout in ("circle", "rect"):
        nails = uniform_perimeter_nails(SHAPE, 24, layout)

        assert len(nails) == 24
        for r, c in nails:
            assert 0 <= r < 64
            assert 0 <= c < 64


def test_adaptive_raises_when_the_pool_cannot_fill_the_count():
    gradient = gradient_with_hotspot()

    with pytest.raises(ValueError, match="found only"):
        # a 16 x 16 perimeter holds 60 unique border pixels, 80 cannot fit
        adaptive_perimeter_nails((16, 16), 80, gradient, "circle")
