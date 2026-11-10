"""Thread palettes: loading, validation, separation, palette rendering."""

import json

import numpy as np
import pytest

from _helpers import image_from_numpy, image_to_numpy
from restring import palettes
from restring.canvas import init_canvas, pull_order_to_array_palette, pull_order_to_array_rgb
from restring.generator import Config, generate_palette, generate_rgb, separate_targets
from restring.nails import create_circle_nail_positions

SHAPE = (64, 64)
NAILS = create_circle_nail_positions(SHAPE, nail_step=4)
RGB_TRIPLE = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]


def seeded_image():
    rng = np.random.default_rng(5)
    return image_from_numpy(rng.random((64, 64, 3)))


def test_builtins_cover_the_documented_sets():
    assert [t.name for t in palettes.builtin_palette("rgb")] == ["red", "green", "blue"]
    assert len(palettes.builtin_palette("cmy")) == 3
    assert len(palettes.builtin_palette("cmyk")) == 4
    assert palettes.builtin_palette("cmyk")[3].rgb == (1.0, 1.0, 1.0)
    with pytest.raises(palettes.PaletteError, match="unknown palette"):
        palettes.builtin_palette("dmcc")


def test_load_palette_file_round_trip(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps([
        {"comment": "community DMC-to-RGB charts, approximate sRGB"},
        {"name": "DMC 310", "rgb": [0.05, 0.05, 0.06]},
        {"name": "DMC Blanc", "rgb": [0.98, 0.98, 0.96]},
    ]))
    threads = palettes.load_palette(path)
    assert [t.name for t in threads] == ["DMC 310", "DMC Blanc"]
    assert threads[0].rgb == (0.05, 0.05, 0.06)


def test_rejects_out_of_range_rgb(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps([{"name": "hot", "rgb": [1.5, 0.0, 0.0]}]))
    with pytest.raises(palettes.PaletteError, match="0..1"):
        palettes.load_palette(path)


def test_rejects_bad_json_shape(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"name": "solo", "rgb": [0, 0, 0]}))
    with pytest.raises(palettes.PaletteError, match="JSON list"):
        palettes.load_palette(path)


def test_rejects_more_than_eight_threads(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps([{"name": f"t{i}", "rgb": [0.1 * i, 0, 0]} for i in range(9)]))
    with pytest.raises(palettes.PaletteError, match="cap of 8"):
        palettes.load_palette(path)


def test_separation_pure_red_reaches_only_the_right_threads():
    img = image_from_numpy([[[1.0, 0.0, 0.0]]])
    rgb_threads = palettes.builtin_palette("rgb")
    maps = separate_targets(img, rgb_threads, (1, 1))
    r_map = image_to_numpy(maps[0])
    g_map = image_to_numpy(maps[1])
    b_map = image_to_numpy(maps[2])
    # the R thread target is the red channel (pure red everywhere), the
    # G and B thread targets sit at zero: no ink for a pure red image
    assert r_map[0, 0] == 1.0
    assert g_map[0, 0] == 0.0 and b_map[0, 0] == 0.0


def test_cmy_separation_pure_red_is_cyan_free():
    img = image_from_numpy([[[1.0, 0.0, 0.0]]])
    cmy = palettes.builtin_palette("cmy")
    maps = separate_targets(img, cmy, (1, 1))
    # cyan = (G + B) / 2 = 0 on pure red; magenta and yellow each carry 0.5
    assert image_to_numpy(maps[0])[0, 0] == 0.0
    assert image_to_numpy(maps[1])[0, 0] == 0.5
    assert image_to_numpy(maps[2])[0, 0] == 0.5


def test_rgb_palette_pipeline_is_pixel_identical_to_generate_rgb():
    img = seeded_image()
    rgb_result, rgb_orders = generate_rgb(img, SHAPE, NAILS,
                                          Config(side_len=64, pull_amount=80, export_strength=0.1))
    pal_result, pal_orders = generate_palette(img, SHAPE, NAILS,
                                              Config(side_len=64, pull_amount=80, export_strength=0.1),
                                              palettes.builtin_palette("rgb"))
    assert pal_orders == rgb_orders
    assert np.array_equal(image_to_numpy(pal_result), image_to_numpy(rgb_result))


def test_cmyk_end_to_end():
    img = seeded_image()
    result, orders = generate_palette(img, SHAPE, NAILS,
                                      Config(side_len=64, pull_amount=100, export_strength=0.1),
                                      palettes.builtin_palette("cmyk"))
    arr = image_to_numpy(result)
    assert result.shape() == (64, 64, 3)
    assert len(orders) == 4
    assert len({len(o) for o in orders}) == 1
    assert arr.min() >= 0.0 and arr.max() <= 1.0


def test_render_palette_matches_render_rgb_for_the_rgb_triple():
    orders = [[0, 5, 10, 5], [0, 16, 21, 16], [0, 27, 32, 27]]
    canvas = init_canvas((64, 64, 3))
    via_rgb = pull_order_to_array_rgb(orders, canvas, NAILS, strength=[-0.1] * 3)
    via_palette = pull_order_to_array_palette(orders, canvas, NAILS, RGB_TRIPLE,
                                              strength=[-0.1] * 3)
    assert np.array_equal(image_to_numpy(via_rgb), image_to_numpy(via_palette))
