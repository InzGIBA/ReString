"""SVG outline import: element subset, errors, sampling."""

from pathlib import Path

import numpy as np
import pytest

from restring.layouts import LayoutError, from_svg

SHAPE = (64, 64)
STAR = Path(__file__).parent.parent / "data" / "star_outline.svg"


def test_star_fixture_samples_and_fits():
    nails = from_svg(STAR, SHAPE, 150)
    assert len(nails) == 150
    assert all(0 <= r < 64 and 0 <= c < 64 for r, c in nails)
    assert len(set(nails)) == 150
    # the star's five spikes reach near the grid edge, the valleys stay inside
    radii = [max(abs(r - 31.5), abs(c - 31.5)) for r, c in nails]
    assert max(radii) > 25
    assert min(radii) < 12


def test_path_subset_m_l_z(tmp_path):
    path = tmp_path / "triangle.svg"
    path.write_text('<svg viewBox="0 0 100 100"><path d="M 50 2 L 98 95 L 2 95 Z"/></svg>')
    nails = from_svg(path, SHAPE, 60)
    assert len(nails) == 60


def test_relative_commands_supported(tmp_path):
    path = tmp_path / "tri.svg"
    path.write_text('<svg viewBox="0 0 100 100"><path d="m 50 2 l 48 93 l -96 0 z"/></svg>')
    a = from_svg(path, SHAPE, 30)
    path.write_text('<svg viewBox="0 0 100 100"><path d="M 50 2 L 98 95 L 2 95 Z"/></svg>')
    b = from_svg(path, SHAPE, 30)
    assert np.allclose(a, b)


def test_curves_fail_with_clear_message(tmp_path):
    path = tmp_path / "curve.svg"
    path.write_text('<svg viewBox="0 0 100 100"><path d="M 10 10 C 40 10 60 90 90 90"/></svg>')
    with pytest.raises(LayoutError, match="M/L/Z"):
        from_svg(path, SHAPE, 60)


def test_unsupported_shapes_fail(tmp_path):
    path = tmp_path / "empty.svg"
    path.write_text('<svg viewBox="0 0 100 100"><ellipse cx="50" cy="50" rx="40" ry="30"/></svg>')
    with pytest.raises(LayoutError, match="no supported outline"):
        from_svg(path, SHAPE, 60)


def test_count_too_small(tmp_path):
    with pytest.raises(LayoutError, match="count >= 3"):
        from_svg(STAR, SHAPE, 2)


def test_rect_circle_polyline_elements(tmp_path):
    rect = tmp_path / "rect.svg"
    rect.write_text('<svg viewBox="0 0 100 100"><rect x="10" y="20" width="60" height="40"/></svg>')
    nails = from_svg(rect, SHAPE, 40)
    assert len(nails) == 40
    assert all(0 <= r < 64 and 0 <= c < 64 for r, c in nails)

    circle = tmp_path / "circle.svg"
    circle.write_text('<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="30"/></svg>')
    assert len(from_svg(circle, SHAPE, 40)) == 40

    polyline = tmp_path / "poly.svg"
    polyline.write_text('<svg viewBox="0 0 100 100"><polyline points="10,10 90,10 50,90"/></svg>')
    assert len(from_svg(polyline, SHAPE, 40)) == 40


def test_polyline_with_odd_coordinates_fails(tmp_path):
    path = tmp_path / "bad.svg"
    path.write_text('<svg viewBox="0 0 100 100"><polyline points="10,10 90"/></svg>')

    with pytest.raises(LayoutError, match="needs pairs of coordinates"):
        from_svg(path, SHAPE, 40)


def test_path_command_missing_coordinates_fails(tmp_path):
    path = tmp_path / "short.svg"
    path.write_text('<svg viewBox="0 0 100 100"><path d="M 50"/></svg>')

    with pytest.raises(LayoutError, match="missing coordinates"):
        from_svg(path, SHAPE, 40)


def test_size_from_width_height_when_viewbox_missing(tmp_path):
    path = tmp_path / "sized.svg"
    path.write_text('<svg width="100px" height="100px"><path d="M 50 2 L 98 95 L 2 95 Z"/></svg>')
    assert len(from_svg(path, SHAPE, 40)) == 40


def test_unsizable_svg_fails(tmp_path):
    # a missing size falls back to a 1 x 1 unit space; only an explicit
    # non-positive size triggers the error
    path = tmp_path / "zero.svg"
    path.write_text('<svg width="0" height="0"><path d="M 50 2 L 98 95 L 2 95 Z"/></svg>')

    with pytest.raises(LayoutError, match="cannot determine the SVG size"):
        from_svg(path, SHAPE, 40)


def test_clockwise_sort_snaps_the_nine_oclock_seam():
    from restring.layouts import _clockwise_from_9

    # a float point within 1e-9 of the seam angle snaps to the front; scaled
    # SVG coordinates can land that close, integer pixels cannot. The other
    # points sit on the seam's row so the point-set centroid keeps the seam
    # point's angle inside the snap window.
    seam = (31.5 + 1e-10, 0.0)
    points = [seam, (31.5, 30), (31.5, 62)]
    ordered = _clockwise_from_9(points)

    assert ordered[0] is seam
