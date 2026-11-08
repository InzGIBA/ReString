import numpy as np

from _helpers import image_to_numpy
from restring.canvas import get_aa_line, init_canvas, line_aa, pull_order_to_array_bw
from restring.nails import create_circle_nail_positions


def test_init_canvas_white_by_default():
    canvas = init_canvas((5, 5))

    assert canvas.shape() == (5, 5, 1)
    assert canvas.pixel(0, 0, 0) == 1.0
    assert canvas.pixel(4, 4, 0) == 1.0


def test_init_canvas_black():
    canvas = init_canvas((5, 5, 3), black=True)

    assert canvas.shape() == (5, 5, 3)
    assert canvas.pixel(2, 2, 2) == 0.0


def test_line_aa_stays_within_segment_and_covers_endpoints():
    rng = np.random.default_rng(11)
    for _ in range(100):
        p0 = tuple(int(v) for v in rng.integers(0, 64, 2))
        p1 = tuple(int(v) for v in rng.integers(0, 64, 2))
        rr, cc, val = line_aa(*p0, *p1)
        assert p0 in set(zip(rr, cc)) and p1 in set(zip(rr, cc))
        assert all(0 <= v <= 1 for v in val)


def test_get_aa_line_clips_to_valid_range():
    pic = np.ones((20, 20))

    line, rr, cc = get_aa_line((0, 0), (19, 19), -0.5, pic)

    assert len(rr) == len(cc) == len(line)
    assert line.min() >= 0.0
    assert line.max() <= 1.0


def test_pull_order_to_array_bw_stays_in_range():
    shape = (40, 40)
    nails = create_circle_nail_positions(shape, nail_step=2)
    order = [0, len(nails) // 3, len(nails) // 2, 1]

    result = pull_order_to_array_bw(order, init_canvas((80, 80)), nails, -0.3)

    arr = image_to_numpy(result)
    assert arr.shape == (80, 80)
    assert arr.min() >= 0.0
    assert arr.max() <= 1.0
