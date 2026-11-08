"""Rust core (_core) equivalence tests.

The compiled Rust backend must be a drop-in replacement of the numpy path:
identical line rasterization, identical pull orders (the greedy choice must
not drift between backends), deterministic output.
"""

import numpy as np
import pytest

from restring import _core
from restring.canvas import init_canvas, line_aa
from restring.generator import _create_art_rust, create_art
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
        assert np.array_equal(py[0], np.asarray(rs[0]))
        assert np.array_equal(py[1], np.asarray(rs[1]))
        assert np.allclose(py[2], np.asarray(rs[2]), atol=1e-12)


def _numpy_create_art(nails, orig, pic, strength, i_limit, random_nails=None):
    """create_art with the Rust backend temporarily disabled."""
    import restring.generator as gen

    saved = gen._core
    gen._core = None
    try:
        return create_art(nails, orig, pic, strength, i_limit=i_limit,
                          random_nails=random_nails)
    finally:
        gen._core = saved


def test_greedy_orders_identical():
    rng = np.random.default_rng(5)
    target = rng.random(SHAPE) * 0.8 + 0.1

    pic_np = init_canvas(SHAPE)
    order_np = _numpy_create_art(NAILS, target, pic_np, -0.05, i_limit=400)

    pic_rs = init_canvas(SHAPE)
    order_rs = create_art(NAILS, target, pic_rs, -0.05, i_limit=400)

    assert order_np == order_rs
    # the working canvas contract (mutation) holds on the Rust path too
    assert np.allclose(pic_np, pic_rs, atol=1e-9)


def test_greedy_orders_identical_random_subset():
    rng = np.random.default_rng(9)
    target = rng.random(SHAPE) * 0.8 + 0.1

    pic_np = init_canvas(SHAPE)
    order_np = _numpy_create_art(NAILS, target, pic_np, -0.05, i_limit=300, random_nails=20)

    pic_rs = init_canvas(SHAPE)
    order_rs = create_art(NAILS, target, pic_rs, -0.05, i_limit=300, random_nails=20)

    assert order_np == order_rs


def test_rust_backend_is_deterministic():
    rng = np.random.default_rng(3)
    target = rng.random(SHAPE) * 0.8 + 0.1

    order_a = _create_art_rust(NAILS, target, init_canvas(SHAPE), -0.05, 200, None)
    order_b = _create_art_rust(NAILS, target, init_canvas(SHAPE), -0.05, 200, None)

    assert order_a == order_b
