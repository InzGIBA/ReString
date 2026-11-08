from math import atan2

import numpy as np

from restring.nails import (
    create_circle_nail_positions,
    create_rectangle_nail_positions,
    scale_nails,
)


def test_rectangle_nails_lie_on_the_border():
    shape = (50, 60)

    nails = create_rectangle_nail_positions(shape, nail_step=5)

    height, width = shape
    for y, x in nails:
        assert y in (0, height - 1) or x in (0, width - 1)


def test_rectangle_nails_go_clockwise_from_top_left():
    # 20x20, step 2: top edge has 10 nails, then the right edge follows
    nails = [tuple(nail) for nail in create_rectangle_nail_positions((20, 20), nail_step=2)]

    assert nails[0] == (0, 0)             # first nail: top left corner
    assert all(y == 0 for y, x in nails[:10])   # top edge block comes first
    assert nails[10] == (1, 19)           # right edge follows clockwise
    assert nails[-1][1] == 0              # last nails on the left edge (x == 0)


def test_rectangle_nails_are_unique():
    nails = create_rectangle_nail_positions((30, 40), nail_step=3)

    assert len(nails) == len({tuple(nail) for nail in nails})


def test_circle_nails_are_sorted_by_angle():
    shape = (101, 101)
    centre = (shape[0] // 2, shape[1] // 2)

    nails = create_circle_nail_positions(shape, nail_step=1)

    angles = [atan2(y - centre[0], x - centre[1]) for y, x in nails]
    assert angles == sorted(angles)


def test_circle_nail_step_subsamples():
    shape = (101, 101)

    all_nails = create_circle_nail_positions(shape, nail_step=1)
    every_fourth = create_circle_nail_positions(shape, nail_step=4)

    assert len(all_nails) > len(every_fourth)
    assert len(every_fourth) == len(all_nails[::4])


def test_circle_nails_stay_inside_canvas():
    shape = (60, 80)

    nails = create_circle_nail_positions(shape, nail_step=1)

    for y, x in nails:
        assert 0 <= y < shape[0]
        assert 0 <= x < shape[1]


def test_scale_nails_scales_y_then_x():
    nails = np.array([(10, 20), (30, 40)])

    scaled = scale_nails(0.5, 2, nails)  # (x_ratio, y_ratio)

    assert scaled == [(20, 10), (60, 20)]
