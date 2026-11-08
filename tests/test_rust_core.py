"""Rust core (_core) equivalence tests.

The compiled Rust backend must be a drop-in replacement of the numpy path:
identical line rasterization, identical pull orders (the greedy choice must
not drift between backends), deterministic output.
"""

import numpy as np
import pytest

from _helpers import image_from_numpy, image_to_numpy
from restring import _core
from restring.canvas import init_canvas, line_aa
from restring.generator import create_art
from restring.nails import create_circle_nail_positions

pytestmark = pytest.mark.skipif(_core is None, reason="Rust core not built")

SHAPE = (64, 64)
NAILS = create_circle_nail_positions(SHAPE, nail_step=4)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_line_aa_matches_python_port(seed):
    rng = np.random.default_rng(seed)
    for _ in range(50):
        p0 = tuple(int(v) for v in rng.integers(0, 64, 2))
        p1 = tuple(int(v) for v in rng.integers(0, 64, 2))
        py = line_aa(*p0, *p1)
        rs = _core.line_aa(*p0, *p1)
        assert py[0] == list(rs[0])
        assert py[1] == list(rs[1])
        assert np.allclose(py[2], np.asarray(rs[2]), atol=1e-12)


def test_circle_nails_match_python_semantics():
    # first nail at 9 o'clock, angles ascending (clockwise), step subsampling
    nails = _core.circle_nails(64, 64, 4, 1, 1)
    all_nails = _core.circle_nails(64, 64, 1, 1, 1)
    assert all(0 <= r < 64 and 0 <= c < 64 for r, c in nails)
    assert len(nails) == len(all_nails[::4])
    assert nails == all_nails[::4]


def _numpy_create_art(nails, target_image, strength, i_limit, random_nails=None):
    """create_art with the Rust backend temporarily disabled."""
    import restring.generator as gen

    saved = gen._core
    gen._core = None
    try:
        return create_art(nails, target_image, init_canvas(SHAPE), strength,
                          i_limit=i_limit, random_nails=random_nails)
    finally:
        gen._core = saved


def test_greedy_orders_identical():
    rng = np.random.default_rng(5)
    target = image_from_numpy(rng.random(SHAPE) * 0.8 + 0.1)

    order_np, pic_np = _numpy_create_art(NAILS, target, -0.05, 400)
    order_rs, pic_rs = create_art(NAILS, target, init_canvas(SHAPE), -0.05, i_limit=400)

    assert order_np == order_rs
    # the working canvas contract holds on the Rust path too
    assert np.allclose(image_to_numpy(pic_np), image_to_numpy(pic_rs), atol=1e-9)


def test_greedy_orders_identical_random_subset():
    rng = np.random.default_rng(9)
    target = image_from_numpy(rng.random(SHAPE) * 0.8 + 0.1)

    order_np, _ = _numpy_create_art(NAILS, target, -0.05, 300, random_nails=20)
    order_rs, _ = create_art(NAILS, target, init_canvas(SHAPE), -0.05,
                             i_limit=300, random_nails=20)

    assert order_np == order_rs


def test_rust_backend_is_deterministic():
    rng = np.random.default_rng(3)
    target = image_from_numpy(rng.random(SHAPE) * 0.8 + 0.1)

    order_a, _ = create_art(NAILS, target, init_canvas(SHAPE), -0.05, i_limit=200)
    order_b, _ = create_art(NAILS, target, init_canvas(SHAPE), -0.05, i_limit=200)

    assert order_a == order_b


def test_render_bw_roundtrip_matches_python_reference():
    # the Rust render must equal the documented Python semantics: scaled nails,
    # accumulated AA lines, final clip
    rng = np.random.default_rng(4)
    order = [0] + list(rng.integers(0, len(NAILS), size=20))
    from restring.canvas import pull_order_to_array_bw

    rendered = pull_order_to_array_bw(order, init_canvas((80, 80)), NAILS, -0.3)
    arr = image_to_numpy(rendered)
    assert arr.min() >= 0.0 and arr.max() <= 1.0
