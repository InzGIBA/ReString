from math import atan2

import numpy as np


def _ellipse_perimeter_pixels(centre_r, centre_c, r_radius, c_radius):
    """Thin rasterized ellipse boundary — replacement for skimage.draw.ellipse_perimeter.

    Classic midpoint ellipse algorithm (two regions, 4-way symmetry), producing
    an 8-connected one-pixel-thick perimeter like the skimage original.
    """
    a, b = int(c_radius), int(r_radius)  # horizontal / vertical semi-axes
    a2, b2 = a * a, b * b
    points = set()

    def plot4(x, y):
        points.update(((centre_r + y, centre_c + x), (centre_r + y, centre_c - x),
                       (centre_r - y, centre_c + x), (centre_r - y, centre_c - x)))

    x, y = 0, b
    dx, dy = 2 * b2 * x, 2 * a2 * y
    d1 = b2 - a2 * b + a2 / 4
    while dx < dy:  # region 1: slope > -1
        plot4(x, y)
        if d1 < 0:
            x += 1
            dx += 2 * b2
            d1 += dx + b2
        else:
            x += 1
            y -= 1
            dx += 2 * b2
            dy -= 2 * a2
            d1 += dx - dy + b2
    d2 = b2 * (x + 0.5) ** 2 + a2 * (y - 1) ** 2 - a2 * b2
    while y >= 0:  # region 2: slope <= -1
        plot4(x, y)
        if d2 > 0:
            y -= 1
            dy -= 2 * a2
            d2 += a2 - dy
        else:
            y -= 1
            x += 1
            dx += 2 * b2
            dy -= 2 * a2
            d2 += dx - dy + a2

    rows = np.fromiter((p[0] for p in points), dtype=int, count=len(points))
    cols = np.fromiter((p[1] for p in points), dtype=int, count=len(points))
    return rows, cols


def create_rectangle_nail_positions(shape, nail_step=2):
    height, width = shape

    nails_top = [(0, i) for i in range(0, width, nail_step)]
    nails_bot = [(height-1, i) for i in range(0, width, nail_step)]
    nails_right = [(i, width-1) for i in range(1, height-1, nail_step)]
    nails_left = [(i, 0) for i in range(1, height-1, nail_step)]

    return np.array(nails_top + nails_right + nails_bot + nails_left)


def create_circle_nail_positions(shape, nail_step=2, r1_multip=1, r2_multip=1):
    height = shape[0]
    width = shape[1]

    centre = (height // 2, width // 2)
    radius = min(height, width) // 2 - 1
    rr, cc = _ellipse_perimeter_pixels(centre[0], centre[1], int(radius*r1_multip), int(radius*r2_multip))
    nails = list(set([(rr[i], cc[i]) for i in range(len(cc))]))
    nails.sort(key=lambda c: atan2(c[0] - centre[0], c[1] - centre[1]))

    return np.asarray(nails[::nail_step])


def scale_nails(x_ratio, y_ratio, nails):
    return [(int(y_ratio*nail[0]), int(x_ratio*nail[1])) for nail in nails]
