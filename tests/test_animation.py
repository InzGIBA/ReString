"""Winding animation: frame math, GIF output, wb palette survival."""

import numpy as np

from _helpers import image_from_numpy, image_to_numpy
from restring import _core
from restring.canvas import init_canvas, pull_order_to_array_bw, pull_order_to_array_rgb
from restring.generator import Config, generate_bw, generate_rgb
from restring.nails import create_circle_nail_positions
from restring.project import Project

SHAPE = (64, 64)
NAILS = [tuple(n) for n in create_circle_nail_positions(SHAPE, nail_step=4)]
GFX = (64, 64, 64, 64, True)  # in_w, in_h, out_w, out_h, white


def noise_project(mode="bw"):
    rng = np.random.default_rng(5)
    img = image_from_numpy(rng.random((64, 64, 3)))
    if mode == "bw":
        _, order = generate_bw(img, SHAPE, NAILS, Config(side_len=64, pull_amount=60,
                                                         export_strength=0.1))
        orders = [order]
    else:
        _, orders = generate_rgb(img, SHAPE, NAILS, Config(side_len=64, pull_amount=60,
                                                           export_strength=0.1))
    return Project(mode=mode, config={"grid": 64, "wb": False}, nails=NAILS,
                   pull_orders=orders, input_digest="x", restring_version="1.1.0")


def test_raw_mode_snapshots_after_every_pull():
    proj = noise_project()
    order = proj.pull_orders[0]
    frames = _core.animate_bw(order, NAILS, -0.1, *GFX, 0)

    assert len(frames) == len(order) - 1
    for i in range(len(frames)):
        prefix = pull_order_to_array_bw(order[: i + 2], init_canvas(SHAPE), NAILS, -0.1)
        assert np.array_equal(image_to_numpy(frames[i]), image_to_numpy(prefix))


def test_downsampled_frames_blank_first_full_last():
    proj = noise_project()
    order = proj.pull_orders[0]
    total = len(order) - 1
    n_frames = 6
    frames = _core.animate_bw(order, NAILS, -0.1, *GFX, n_frames)

    assert len(frames) == n_frames
    assert np.array_equal(image_to_numpy(frames[0]), np.ones((64, 64)))  # blank canvas
    full = pull_order_to_array_bw(order, init_canvas(SHAPE), NAILS, -0.1)
    assert np.array_equal(image_to_numpy(frames[-1]), image_to_numpy(full))

    # monotonic contiguous coverage: frame i is the render after (total * i) // (n_frames - 1) pulls
    for i in range(1, n_frames - 1):
        pulls_done = total * i // (n_frames - 1)
        prefix = pull_order_to_array_bw(order[: pulls_done + 1], init_canvas(SHAPE), NAILS, -0.1)
        assert np.array_equal(image_to_numpy(frames[i]), image_to_numpy(prefix))


def test_rgb_last_frame_matches_render_rgb():
    proj = noise_project(mode="rgb")
    frames = _core.animate_rgb(proj.pull_orders, NAILS, [-0.1] * 3, *GFX, 6)
    assert len(frames) == 6
    full = pull_order_to_array_rgb(proj.pull_orders, init_canvas((64, 64, 3)), NAILS,
                                   strength=[-0.1] * 3)
    assert np.array_equal(image_to_numpy(frames[-1]), image_to_numpy(full))


def test_gif_file_signature_and_survives_quantization(tmp_path):
    # wb mode: white thread on black canvas — dark tones must survive the
    # GIF palette quantization
    proj = Project(mode="bw", config={"grid": 64, "wb": True}, nails=NAILS,
                   pull_orders=[[0, 21, 42, 0, 21]], input_digest="x", restring_version="1.1.0")
    frames = _core.animate_bw(proj.pull_orders[0], NAILS, 0.1, 64, 64, 64, 64, False, 4)
    assert np.array_equal(image_to_numpy(frames[0]), np.zeros((64, 64)))  # blank black

    path = tmp_path / "wind.gif"
    count = _core.save_gif(str(path), frames, 30)
    assert count == 4
    raw = path.read_bytes()
    assert raw[:4] == b"GIF8"
    assert len(raw) > 1000

    loaded = _core.Image.load(str(path))  # first frame, palette-quantized
    arr = image_to_numpy(loaded)
    assert arr.mean() < 0.1  # quantized black stays black


def test_animate_project_rgb_writes_a_gif(tmp_path):
    import restring.animation as animation

    proj = noise_project(mode="rgb")
    path = tmp_path / "rgb.gif"

    animation.animate_project(proj, path, export_strength=0.1, size=64, frames=5)

    raw = path.read_bytes()
    assert raw[:4] == b"GIF8"
    assert len(raw) > 1000


def test_animate_project_halves_fps_over_the_size_limit(tmp_path, caplog, monkeypatch):
    import logging

    import restring.animation as animation

    monkeypatch.setattr(animation, "SIZE_LIMIT_BYTES", 10)  # force the over-limit path
    proj = noise_project()
    path = tmp_path / "big.gif"

    with caplog.at_level(logging.WARNING, logger="restring.animation"):
        animation.animate_project(proj, path, export_strength=0.1, size=64, frames=5)

    assert any("halving fps" in r.message for r in caplog.records)
    assert path.read_bytes()[:4] == b"GIF8"


def test_animate_project_rgb_resolves_strength_per_channel(tmp_path):
    import restring.animation as animation

    proj = noise_project(mode="rgb")
    path = tmp_path / "auto.gif"

    animation.animate_project(proj, path, export_strength=None, size=64, frames=5)

    assert path.read_bytes()[:4] == b"GIF8"
