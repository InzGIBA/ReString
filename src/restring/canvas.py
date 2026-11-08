"""Canvas and thread rendering.

The runtime pipeline is fully Rust: `init_canvas`, `pull_order_to_array_*`
and the line rasterization inside `create_art`/renders all live in
`restring._core`. `line_aa` below is the pure-Python *reference port* of
skimage's Zingl rasterizer — its only callers are the Rust-equivalence tests
(`tests/test_rust_core.py`); numpy appears solely in lazy, dev-only imports
(analysis-script helpers and the generator fallback when `_core` is absent).
"""

from restring import _core


def line_aa(r0, c0, r1, c1):
    """Anti-aliased line — Zingl's Bresenham-based rasterizer.

    Faithful port of skimage.draw.line_aa (scikit-image, BSD-licensed;
    A. Zingl, "A Rasterizing Algorithm for Drawing Curves", 2012), so the
    simulation and export rasters are identical to the original pipeline.
    Returns (rr, cc, val) as plain lists, val in [0, 1].
    """
    rr, cc, val = [], [], []

    dc = abs(c0 - c1)
    dr = abs(r0 - r1)
    err = dc - dr

    sign_c = 1 if c0 < c1 else -1
    sign_r = 1 if r0 < r1 else -1
    ed = 1.0 if dc + dr == 0 else (dc * dc + dr * dr) ** 0.5

    c, r = c0, r0
    while True:
        cc.append(c)
        rr.append(r)
        val.append(abs(err - dc + dr) / ed)

        err_prime = err
        c_prime = c

        if 2 * err_prime >= -dc:
            if c == c1:
                break
            if (err_prime + dr) < ed:
                cc.append(c)
                rr.append(r + sign_r)
                val.append(abs(err_prime + dr) / ed)
            err -= dr
            c += sign_c

        if 2 * err_prime <= dr:
            if r == r1:
                break
            if (dc - err_prime) < ed:
                cc.append(c_prime + sign_c)
                rr.append(r)
                val.append(abs(dc - err_prime) / ed)
            err += dc
            r += sign_r

    return rr, cc, [1.0 - v for v in val]


def init_canvas(shape, black=False):
    """Uniform canvas Image (1.0 = white by default)."""
    ch = shape[2] if len(shape) > 2 else 1
    return _core.Image.blank(shape[1], shape[0], ch, 0.0 if black else 1.0)


def get_aa_line(from_pos, to_pos, strength, picture):
    """Overlay an AA line on a numpy canvas (analysis-script convenience).

    Rasterizes via the Rust core (the Python `line_aa` below is the test
    reference, not a runtime path).
    """
    import numpy as np

    rr, cc, val = _core.line_aa(from_pos[0], from_pos[1], to_pos[0], to_pos[1])
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
