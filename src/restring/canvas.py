"""Canvas and thread rendering.

The pipeline is fully Rust and dependency-free: `init_canvas`, the line
rasterizer and both renders live in `restring._core`. Nothing in this
module (or the whole runtime package) imports numpy — that is guarded by
tests/test_no_runtime_numpy.py.
"""

from restring import _core


def init_canvas(shape, black=False):
    """Uniform canvas Image (1.0 = white by default)."""
    ch = shape[2] if len(shape) > 2 else 1
    return _core.Image.blank(shape[1], shape[0], ch, 0.0 if black else 1.0)


def line_aa(r0, c0, r1, c1):
    """Anti-aliased line — Zingl's Bresenham-based rasterizer (Rust core)."""
    return _core.line_aa(r0, c0, r1, c1)


def pull_order_to_array_bw(order, canvas, nails, strength, shape=None, thread_px=None):
    """Render a pull order onto a canvas of the given value. With `thread_px`
    set (physical thread model), segments stamp with the given pixel width;
    None keeps the classic 1-px hairline."""
    h, w, _ = canvas.shape()
    white = canvas.pixel(0, 0, 0) >= 0.5
    in_h, in_w = shape[:2] if shape is not None else (h, w)
    order_int = [int(i) for i in order]
    nails_int = [(int(n[0]), int(n[1])) for n in nails]
    if thread_px is not None:
        return _core.render_bw_thick(order_int, nails_int, float(strength),
                                     in_w, in_h, w, h, white, float(thread_px))
    return _core.render_bw(order_int, nails_int, float(strength), in_w, in_h, w, h, white)


def pull_order_to_array_rgb(orders, canvas, nails, colors=None, strength=0.1, shape=None,
                            thread_px=None):
    """Render interleaved per-channel pull orders (fixed RGB thread colors).

    `strength` is one float applied to every channel or a per-channel
    sequence of the same length as `orders` (auto export strength resolves
    per channel from each channel's actual pull count). `thread_px` switches
    to the physical thread model like the B/W renderer.
    """
    h, w, _ = canvas.shape()
    white = canvas.pixel(0, 0, 0) >= 0.5
    in_h, in_w = shape[:2] if shape is not None else (h, w)
    strengths = ([float(s) for s in strength] if isinstance(strength, (list, tuple))
                 else [float(strength)] * len(orders))
    orders_int = [[int(i) for i in order] for order in orders]
    nails_int = [(int(n[0]), int(n[1])) for n in nails]
    if thread_px is not None:
        return _core.render_rgb_thick(orders_int, nails_int, strengths,
                                      in_w, in_h, w, h, white, float(thread_px))
    return _core.render_rgb(orders_int, nails_int, strengths, in_w, in_h, w, h, white)


def pull_order_to_array_palette(orders, canvas, nails, colors, strength=0.1, shape=None,
                                thread_px=None):
    """Render interleaved pull orders for an arbitrary thread palette:
    `colors` is one (r, g, b) triple per order; `strength` is one float or a
    per-channel sequence, as in the RGB renderer. `thread_px` switches to the
    thick physical renderer like the RGB path (colors pass through)."""
    h, w, _ = canvas.shape()
    white = canvas.pixel(0, 0, 0) >= 0.5
    in_h, in_w = shape[:2] if shape is not None else (h, w)
    strengths = ([float(s) for s in strength] if isinstance(strength, (list, tuple))
                 else [float(strength)] * len(orders))
    orders_int = [[int(i) for i in order] for order in orders]
    nails_int = [(int(n[0]), int(n[1])) for n in nails]
    colors_int = [(float(r), float(g), float(b)) for r, g, b in colors]
    if thread_px is not None:
        return _core.render_palette(orders_int, nails_int, colors_int, strengths,
                                    in_w, in_h, w, h, white, float(thread_px))
    return _core.render_palette(orders_int, nails_int, colors_int, strengths,
                                in_w, in_h, w, h, white)
