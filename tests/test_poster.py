"""Winding poster: thread length math and SVG structure."""

import math
import xml.etree.ElementTree as ET

import pytest

import restring
from restring.poster import poster_svg, thread_length_mm, thread_lengths_mm
from restring.project import Project

SVG_NS = "{http://www.w3.org/2000/svg}"


def hand_built_project(mode="bw"):
    """Five nails on a 10 px grid, order 0-1-2-3-4. At canvas 100 mm the
    scale is 10 mm per grid unit, so the chords measure 100 + 100 + 100 +
    70.7107 mm."""
    nails = [(0, 0), (0, 10), (10, 10), (10, 0), (5, 5)]
    order = [0, 1, 2, 3, 4]
    orders = [order] if mode == "bw" else [order, order, order]
    return Project(mode=mode, config={"grid": 10, "wb": False}, nails=nails,
                   pull_orders=orders, input_digest="sha256:t", created="2026-04-01T00:00:00Z",
                   restring_version="1.3.0")


def test_thread_length_matches_independent_recomputation():
    proj = hand_built_project()
    lengths_mm = thread_lengths_mm(proj, 100.0)

    expected_dist = 100.0 + 100.0 + 100.0 + math.hypot(5 * 10, 5 * 10)
    expected = expected_dist * 1.05 + 2 * 150.0
    assert len(lengths_mm) == 1
    assert abs(lengths_mm[0] - expected) / expected < 0.001
    assert abs(thread_length_mm(proj, 100.0) - expected) < 0.01


def test_rgb_project_has_three_thread_lengths():
    proj = hand_built_project(mode="rgb")
    lengths_mm = thread_lengths_mm(proj, 100.0)
    assert len(lengths_mm) == 3
    assert len({round(value, 6) for value in lengths_mm}) == 1
    assert thread_length_mm(proj, 100.0) == pytest.approx(3 * lengths_mm[0])


def _parse(svg):
    return ET.fromstring(svg)


def test_svg_structure_and_footer():
    proj = hand_built_project()
    svg = poster_svg(proj, canvas_size_mm=100.0, number_every=2)
    root = _parse(svg)

    circles = root.findall(f".//{SVG_NS}circle")
    assert len(circles) == len(proj.nails)
    texts = [t.text for t in root.findall(f".//{SVG_NS}text")]
    # numbering every 2nd nail in nail-list order: 0, 2, 4
    assert "0" in texts and "2" in texts and "4" in texts
    assert "1" not in texts and "3" not in texts
    footer = texts[-2]
    assert "Nails: 5" in footer and "Pulls: 4" in footer and "Threads: 1" in footer
    # 689.2 mm total rounds to whole meters on a real-size poster
    assert "thread length: 1 m" in footer
    assert f"ReString {restring.__version__}" in texts[-1] and "2026-04-01" in texts[-1]


def test_svg_numbering_order_matches_nail_list():
    nails = [(0, i * 10) for i in range(8)]
    order = list(range(8))
    proj = Project(mode="bw", config={"grid": 70, "wb": False}, nails=nails,
                   pull_orders=[order], input_digest="x", restring_version="1.3.0")
    svg = poster_svg(proj, canvas_size_mm=70.0, number_every=1)
    root = _parse(svg)
    numbers = [int(t.text) for t in root.findall(f".//{SVG_NS}text")
               if t.text and t.text.isdigit()]
    assert numbers == list(range(8))  # ascending in document order


def test_rgb_poster_footer_lists_three_lengths():
    proj = hand_built_project(mode="rgb")
    svg = poster_svg(proj, canvas_size_mm=100.0, number_every=0)
    root = _parse(svg)
    footer = [t.text for t in root.findall(f".//{SVG_NS}text")][-2]
    assert "Threads: 3 (R/G/B)" in footer
    assert footer.count("/") == 6  # 2 in "R/G/B" + 2 separators between the three lengths
    assert len(root.findall(f".//{SVG_NS}circle")) == len(proj.nails)  # shared numbering


def test_svg_preview_lines_and_no_numbering():
    proj = hand_built_project()
    svg = poster_svg(proj, canvas_size_mm=100.0, number_every=0, show_preview=True)
    root = _parse(svg)
    assert len(root.findall(f".//{SVG_NS}line")) == len(proj.pull_orders[0]) - 1
    assert not [t for t in root.findall(f".//{SVG_NS}text") if t.text and t.text.isdigit()]


def test_board_too_large_for_page():
    proj = hand_built_project()
    with pytest.raises(ValueError, match="does not fit"):
        poster_svg(proj, canvas_size_mm=400.0)

def test_poster_rejects_negative_number_every():
    with pytest.raises(ValueError, match="number_every must be"):
        poster_svg(hand_built_project("bw"), canvas_size_mm=200, number_every=-1)
