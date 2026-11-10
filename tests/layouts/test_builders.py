"""Builder invariants for the custom nail layouts."""

import math

import numpy as np
import pytest

from restring.layouts import LayoutError, explicit, polygon, rings, star

SHAPE = (64, 64)


def test_polygon_count_bounds_clockwise():
    nails = polygon(SHAPE, 5, 120)
    assert len(nails) == 120
    assert all(0 <= r < 64 and 0 <= c < 64 for r, c in nails)
    assert len(set(nails)) == 120
    # clockwise from the centroid's 9 o'clock: angles grow monotonically
    cy = sum(r for r, _ in nails) / len(nails)
    cx = sum(c for _, c in nails) / len(nails)
    angles = [(math.atan2(r - cy, c - cx) - math.pi) % (2 * math.pi) for r, c in nails]
    assert angles == sorted(angles)


def test_star_alternates_radii():
    nails = star(SHAPE, 5, 0.55, 100)
    cy, cx = 31.5, 31.5
    radii = [math.hypot(r - cy, c - cx) for r, c in nails]
    assert max(radii) > min(radii)
    # the outer vertices sit near the full radius (31.5 scaled to the grid)
    assert max(radii) > 0.9 * 31.5
    assert min(radii) < 0.6 * 31.5
    assert len(nails) == 100


def test_rings_keep_ring_order():
    nails = rings(SHAPE, [(1.0, 60), (0.6, 40)])
    assert len(nails) == 100
    cy, cx = 31.5, 31.5
    first_ring = [math.hypot(r - cy, c - cx) for r, c in nails[:60]]
    second_ring = [math.hypot(r - cy, c - cx) for r, c in nails[60:]]
    assert all(d > 30 for d in first_ring)   # outer ring first
    assert all(d < 20 for d in second_ring)  # inner ring second


def test_rings_reject_bad_specs():
    with pytest.raises(LayoutError, match="radius_fraction"):
        rings(SHAPE, [(1.4, 50)])
    with pytest.raises(LayoutError, match="count >= 3"):
        rings(SHAPE, [(1.0, 2)])


def test_explicit_validates_bounds_and_dedupes():
    nails = explicit([(0, 0), (63, 63), (0, 63), (0, 0)], SHAPE)
    assert nails == [(0, 0), (63, 63), (0, 63)]
    with pytest.raises(LayoutError, match="outside"):
        explicit([(0, 0), (64, 5), (5, 5)], SHAPE)
    with pytest.raises(LayoutError, match="3 distinct nails"):
        explicit([(1, 1), (1, 1), (1, 1), (1, 2)], SHAPE)


def test_polygon_rejects_bad_params():
    with pytest.raises(LayoutError, match="sides >= 3"):
        polygon(SHAPE, 2, 100)
    with pytest.raises(LayoutError, match="count >= 3"):
        polygon(SHAPE, 5, 2)


def test_star_rejects_bad_params():
    with pytest.raises(LayoutError, match="points >= 3"):
        star(SHAPE, 2, 0.5, 100)
    with pytest.raises(LayoutError, match="inner_radius"):
        star(SHAPE, 5, 1.2, 100)


def test_layouts_search_end_to_end():
    from _helpers import image_from_numpy
    from restring.generator import Config, generate_bw

    rng = np.random.default_rng(5)
    img = image_from_numpy(rng.random((64, 64, 3)))
    layouts_under_test = {
        "polygon": polygon(SHAPE, 5, 120),
        "star": star(SHAPE, 5, 0.55, 100),
        "rings": rings(SHAPE, [(1.0, 60), (0.6, 40)]),
        "explicit": explicit([(0, 0), (0, 63), (63, 63), (63, 0), (31, 31)], SHAPE),
    }
    for name, nails in layouts_under_test.items():
        result, order = generate_bw(img, SHAPE, nails,
                                    Config(side_len=64, pull_amount=40, export_strength=0.1))
        assert len(order) > 1, f"{name} produced no pulls"
        assert result.shape() == (64, 64, 1)



def test_star_count_below_three_is_rejected_directly():
    # the api spec path pre-validates count, the builder keeps its own guard
    with pytest.raises(LayoutError, match="star needs count >= 3"):
        star(SHAPE, 5, 0.5, 2)
