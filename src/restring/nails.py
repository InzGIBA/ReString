"""Nail layouts — thin wrappers over the Rust core."""

from restring import _core


def create_rectangle_nail_positions(shape, nail_step=2):
    """Border nails clockwise from the top-left corner."""
    return _core.rect_nails(shape[1], shape[0], nail_step)


def create_circle_nail_positions(shape, nail_step=2, r1_multip=1, r2_multip=1):
    """Ellipse nails clockwise from 9 o'clock (midpoint rasterization)."""
    return _core.circle_nails(shape[1], shape[0], nail_step, r1_multip, r2_multip)


def scale_nails(x_ratio, y_ratio, nails):
    """Scale nail coordinates onto a resized canvas."""
    return [(int(y_ratio * nail[0]), int(x_ratio * nail[1])) for nail in nails]
