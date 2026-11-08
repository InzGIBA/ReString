from restring.canvas import (
    get_aa_line,
    init_canvas,
    pull_order_to_array_bw,
)
from restring.nails import create_circle_nail_positions


def test_init_canvas_white_by_default():
    canvas = init_canvas((5, 5))

    assert canvas.shape == (5, 5)
    assert (canvas == 1).all()


def test_init_canvas_black():
    canvas = init_canvas((5, 5, 3), black=True)

    assert canvas.shape == (5, 5, 3)
    assert (canvas == 0).all()


def test_get_aa_line_clips_to_valid_range():
    pic = init_canvas((20, 20))

    line, rr, cc = get_aa_line((0, 0), (19, 19), -0.5, pic)

    assert len(rr) == len(cc) == len(line)
    assert line.min() >= 0.0
    assert line.max() <= 1.0


def test_pull_order_to_array_bw_stays_in_range():
    shape = (40, 40)
    nails = create_circle_nail_positions(shape, nail_step=2)
    order = [0, len(nails) // 3, len(nails) // 2, 1]

    result = pull_order_to_array_bw(order, init_canvas((80, 80)), nails, -0.3)

    assert result.shape == (80, 80)
    assert result.min() >= 0.0
    assert result.max() <= 1.0
