"""Round trips and validation for .restring project files."""

import json

import numpy as np
import pytest

from _helpers import image_from_numpy, image_to_numpy
from restring.canvas import init_canvas, pull_order_to_array_bw, pull_order_to_array_rgb
from restring.generator import Config, generate_bw, generate_rgb
from restring.nails import create_circle_nail_positions
from restring.project import ProjectError, load, save

SHAPE = (64, 64)
NAILS = create_circle_nail_positions(SHAPE, nail_step=4)


def seeded_noise():
    rng = np.random.default_rng(5)
    return image_from_numpy(rng.random((64, 64, 3)))


def test_bw_round_trip_pixel_identical(tmp_path):
    img = seeded_noise()
    result, order = generate_bw(img, SHAPE, NAILS,
                                Config(side_len=64, pull_amount=150, export_strength=0.1))
    path = tmp_path / "p.restring"
    save(path, mode="bw", config={"grid": 64, "wb": False}, nails=NAILS,
         pull_orders=[order], input_digest="sha256:x")

    proj = load(path)
    assert proj.mode == "bw"
    assert len(proj.pull_orders) == 1
    assert proj.input_digest == "sha256:x"

    rendered = pull_order_to_array_bw(proj.pull_orders[0], init_canvas((64, 64)),
                                      proj.nails, -0.1, shape=SHAPE)
    assert np.array_equal(image_to_numpy(rendered), image_to_numpy(result))


def test_rgb_round_trip_pixel_identical_with_padding(tmp_path):
    img = seeded_noise()
    result, orders = generate_rgb(img, SHAPE, NAILS,
                                  Config(side_len=64, pull_amount=150, export_strength=0.1))
    path = tmp_path / "p.restring"
    save(path, mode="rgb", config={"grid": 64, "wb": False}, nails=NAILS,
         pull_orders=orders, input_digest="sha256:y")

    proj = load(path)
    assert proj.mode == "rgb"
    assert len(proj.pull_orders) == 3
    assert len({len(o) for o in proj.pull_orders}) == 1  # padding preserved

    rendered = pull_order_to_array_rgb(proj.pull_orders, init_canvas((64, 64, 3)),
                                       proj.nails, strength=[-0.1] * 3, shape=SHAPE)
    assert np.array_equal(image_to_numpy(rendered), image_to_numpy(result))


def _mutate(tmp_path, mutations):
    path = tmp_path / "p.restring"
    save(path, mode="bw", config={"grid": 64, "wb": False}, nails=NAILS,
         pull_orders=[[0, 1, 2]], input_digest="sha256:x")
    data = json.loads(path.read_text())
    mutations(data)
    path.write_text(json.dumps(data))
    return path


def test_rejects_nail_index_out_of_range(tmp_path):
    path = _mutate(tmp_path, lambda d: d["pull_orders"].__setitem__(0, [0, len(NAILS)]))
    with pytest.raises(ProjectError, match="out of range"):
        load(path)


def test_rejects_wrong_order_arity(tmp_path):
    path = _mutate(tmp_path, lambda d: d.update(mode="bw", pull_orders=[[0, 1], [0, 1]]))
    with pytest.raises(ProjectError, match="needs 1 pull order"):
        load(path)


def test_rejects_unknown_format_version(tmp_path):
    path = _mutate(tmp_path, lambda d: d.update(version=3))
    with pytest.raises(ProjectError, match="version"):
        load(path)


def test_loads_version_1_files(tmp_path):
    path = _mutate(tmp_path, lambda d: d.update(version=1))
    proj = load(path)
    assert proj.version == 1
    assert proj.mode == "bw"
    assert proj.palette is None


def test_palette_round_trip_pixel_identical(tmp_path):
    from restring.canvas import pull_order_to_array_palette
    from restring.generator import generate_palette
    from restring.palettes import builtin_palette

    img = seeded_noise()
    threads = builtin_palette("cmyk")
    result, orders = generate_palette(img, SHAPE, NAILS,
                                      Config(side_len=64, pull_amount=120, export_strength=0.1),
                                      threads)
    path = tmp_path / "p.restring"
    save(path, mode="palette", config={"grid": 64, "wb": False}, nails=NAILS,
         pull_orders=orders, input_digest="sha256:z", palette=threads)

    proj = load(path)
    assert proj.mode == "palette"
    assert proj.version == 2
    assert [t.name for t in proj.palette] == [t.name for t in threads]
    assert [t.rgb for t in proj.palette] == [t.rgb for t in threads]
    assert len(proj.pull_orders) == 4

    rendered = pull_order_to_array_palette(proj.pull_orders, init_canvas((64, 64, 3)),
                                           proj.nails, [t.rgb for t in proj.palette],
                                           strength=[-0.1] * 4, shape=SHAPE)
    assert np.array_equal(image_to_numpy(rendered), image_to_numpy(result))


def test_palette_save_validates_arity(tmp_path):
    from restring.palettes import builtin_palette

    threads = builtin_palette("cmy")
    with pytest.raises(ProjectError, match="one thread color per pull order"):
        save(tmp_path / "p.restring", mode="palette", config={"grid": 64}, nails=NAILS,
             pull_orders=[[0, 1], [0, 1]], input_digest="sha256:z", palette=threads)
    with pytest.raises(ProjectError, match="needs a palette"):
        save(tmp_path / "p.restring", mode="palette", config={"grid": 64}, nails=NAILS,
             pull_orders=[[0, 1]], input_digest="sha256:z")
    with pytest.raises(ProjectError, match="implicit colors"):
        save(tmp_path / "p.restring", mode="bw", config={"grid": 64}, nails=NAILS,
             pull_orders=[[0, 1]], input_digest="sha256:z", palette=threads)


def test_palette_load_validates_colors(tmp_path):
    from restring.palettes import builtin_palette

    path = tmp_path / "p.restring"
    save(path, mode="palette", config={"grid": 64}, nails=NAILS,
         pull_orders=[[0, 1], [0, 1]], input_digest="sha256:z",
         palette=builtin_palette("cmy")[:2])

    data = json.loads(path.read_text())
    data["palette"][0]["rgb"] = [1.5, 0.0, 0.0]
    path.write_text(json.dumps(data))
    with pytest.raises(ProjectError, match="0..1"):
        load(path)

    data = json.loads(path.read_text())
    data["palette"] = data["palette"][:1]
    path.write_text(json.dumps(data))
    with pytest.raises(ProjectError, match="one color per pull order"):
        load(path)


def test_rejects_foreign_format(tmp_path):
    path = _mutate(tmp_path, lambda d: d.update(format="other-project"))
    with pytest.raises(ProjectError, match="not a restring project"):
        load(path)


def test_rejects_bad_mode(tmp_path):
    path = _mutate(tmp_path, lambda d: d.update(mode="cmyk"))
    with pytest.raises(ProjectError, match="mode"):
        load(path)


def test_rejects_bad_nails(tmp_path):
    path = _mutate(tmp_path, lambda d: d.update(nails=[[0]]))
    with pytest.raises(ProjectError, match=r"\[row, col\]"):
        load(path)
