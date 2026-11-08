"""Canvas and thread rendering.

The pipeline is fully Rust: `init_canvas`, the line rasterizer and both
renders live in `restring._core`. The numpy import below is lazy and
dev-only (analysis-script helpers operating on numpy canvases).
"""

from restring import _core


def init_canvas(shape, black=False):
    """Uniform canvas Image (1.0 = white by default)."""
    ch = shape[2] if len(shape) > 2 else 1
    return _core.Image.blank(shape[1], shape[0], ch, 0.0 if black else 1.0)


def line_aa(r0, c0, r1, c1):
    """Anti-aliased line — Zingl's Bresenham-based rasterizer (Rust core)."""
    return _core.line_aa(r0, c0, r1, c1)


def get_aa_line(from_pos, to_pos, strength, picture):
    """Overlay an AA line on a numpy canvas (analysis-script convenience)."""
    import numpy as np

    rr, cc, val = line_aa(from_pos[0], from_pos[1], to_pos[0], to_pos[1])
    rr, cc, val = np.asarray(rr), np.asarray(cc), np.asarray(val)
    line = np.clip(picture[rr, cc] + strength * val, 0, 1)
    return line, rr, cc


def pull_order_to_array_bw(order, canvas, nails, strength, shape=None):
    """Render a pull order onto a canvas of the given value."""
    h, w, _ = canvas.shape()
    white = canvas.pixel(0, 0, 0) >= 0.5
    in_h, in_w = shape[:2] if shape is not None else (h, w)
    return _core.render_bw(
        [int(i) for i in order],
        [(int(n[0]), int(n[1])) for n in nails],
        float(strength), in_w, in_h, w, h, white,
    )


def pull_order_to_array_rgb(orders, canvas, nails, colors=None, strength=0.1, shape=None):
    """Render interleaved per-channel pull orders (fixed RGB thread colors)."""
    h, w, _ = canvas.shape()
    white = canvas.pixel(0, 0, 0) >= 0.5
    in_h, in_w = shape[:2] if shape is not None else (h, w)
    return _core.render_rgb(
        [[int(i) for i in order] for order in orders],
        [(int(n[0]), int(n[1])) for n in nails],
        float(strength), in_w, in_h, w, h, white,
    )
