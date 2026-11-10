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
