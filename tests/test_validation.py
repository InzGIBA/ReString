"""Input validation across the package: project files, palettes, layout
specs, palette resolution, plus the thick-render and metric wrappers the
error paths sit next to."""

import json

import numpy as np
import pytest

from _helpers import image_from_numpy, image_to_numpy
from restring import _core
from restring.api import _resolve_threads, export_strength, parse_layout_spec
from restring.canvas import init_canvas, pull_order_to_array_bw, pull_order_to_array_palette, pull_order_to_array_rgb
from restring.generator import Config, generate_rgb, resolve_export_strength
from restring.image_transformations import largest_rect
from restring.metrics import blurred_ssim, corr, mse
from restring.nails import create_circle_nail_positions
from restring.palettes import PaletteError, load_palette
from restring.project import ProjectError, load

SHAPE = (64, 64)
NAILS = create_circle_nail_positions(SHAPE, nail_step=4)
ORDER = [0, 5, 12, 3, 0]


# --- .restring project validation -------------------------------------------

def write_project(tmp_path, data, name="p.restring"):
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


def valid_project():
    return {
        "format": "restring-project",
        "version": 1,
        "mode": "bw",
        "config": {"grid": 64, "wb": False},
        "nails": [[0, 0], [0, 32]],
        "pull_orders": [[0, 1, 0]],
        "input_digest": "sha256:x",
    }


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d.update(nails=[0, 1]), "nails must be"),
    (lambda d: d.update(mode="cmyk"), "mode must be"),
    (lambda d: d.update(pull_orders=[]), "needs 1 pull order"),
    (lambda d: d.update(pull_orders=[[0, 9, 0]]), "out of range"),
    (lambda d: d.update(pull_orders=[["0", "1"]]), "out of range"),
    (lambda d: d.update(pull_orders=[[0, True, 0]]), "out of range"),
    (lambda d: d.update(pull_orders=["x"]), "must be lists"),
    (lambda d: d.pop("config"), "missing config"),
])
def test_project_rejects_malformed_files(tmp_path, mutate, message):
    data = valid_project()
    mutate(data)

    with pytest.raises(ProjectError, match=message):
        load(write_project(tmp_path, data))


def test_project_rejects_non_object_wrong_format_and_version(tmp_path):
    with pytest.raises(ProjectError, match="JSON object"):
        load(write_project(tmp_path, [1, 2]))
    with pytest.raises(ProjectError, match="not a restring project"):
        load(write_project(tmp_path, {**valid_project(), "format": "other"}))
    with pytest.raises(ProjectError, match="unsupported project format version"):
        load(write_project(tmp_path, {**valid_project(), "version": 99}))


def test_project_rejects_bw_file_carrying_two_orders(tmp_path):
    data = valid_project()
    data["pull_orders"] = [[0, 1, 0], [1, 0, 1]]

    with pytest.raises(ProjectError, match="needs 1 pull order"):
        load(write_project(tmp_path, data))


# --- palette files ------------------------------------------------------------

def write_palette(tmp_path, data):
    path = tmp_path / "p.json"
    path.write_text(json.dumps(data))
    return path


def thread(name="T", rgb=(0.5, 0.5, 0.5)):
    return {"name": name, "rgb": list(rgb)}


def test_palette_skips_comment_entries_and_keeps_threads(tmp_path):
    path = write_palette(tmp_path, [{"comment": "header"}, thread()])

    threads = load_palette(path)

    assert len(threads) == 1
    assert threads[0].name == "T"


@pytest.mark.parametrize("entry, message", [
    ("red", "must be objects"),
    ({"name": "no color"}, "missing 'rgb'"),
    ({"rgb": [0.1, 0.2]}, "'rgb' must be"),
    ({"rgb": [0.1, 0.2, "z"]}, "'rgb' must be"),
    ({"rgb": [0.1, 0.2, 1.4]}, "sit in 0..1"),
])
def test_palette_rejects_bad_entries(tmp_path, entry, message):
    with pytest.raises(PaletteError, match=message):
        load_palette(write_palette(tmp_path, [entry]))


def test_palette_rejects_non_list_empty_and_over_cap(tmp_path):
    with pytest.raises(PaletteError, match="JSON list"):
        load_palette(write_palette(tmp_path, {"rgb": [0, 0, 0]}))
    with pytest.raises(PaletteError, match="carries no thread colors"):
        load_palette(write_palette(tmp_path, [{"comment": "only a header"}]))
    with pytest.raises(PaletteError, match="exceeds the cap"):
        load_palette(write_palette(tmp_path, [thread(f"t{i}") for i in range(9)]))


# --- layout spec parsing (api) -------------------------------------------------

@pytest.mark.parametrize("spec, message", [
    ("circle@zzz", "aspect must be a number"),
    ("circle@99", "aspect must sit in 0.1..10"),
    ("hexagon:6", "unknown layout"),
    # the rest parse fine and raise when the parsed builder runs
    ("polygon:5:two", "must be an int"),
    ("polygon:5:1", "must be >= 3"),
    ("star:5", "star:points:inner"),
    ("star:two:0.5", "must be an int"),
    ("star:5:two", "must be a number"),
    ("star:5:5", "inner"),
    ("star:5:0.5:2", "star count must be >= 3"),
    ("rings:0.5", "rings:r:count"),
    ("rings:0.5:8:0.9", "rings:r:count"),
    ("rings:zz:8", "must be a number"),
    ("rings:0.5:two", "must be an int"),
    ("rings:0.5:1", "must be >= 3"),
    ("svg:f.svg:two", "must be an int"),
])
def test_layout_spec_errors(spec, message):
    # parse-time specs raise inside parse_layout_spec, build-time specs raise
    # inside the returned builder; both surfaces are ValueError
    with pytest.raises(ValueError, match=message):
        parsed = parse_layout_spec(spec)
        parsed[0](SHAPE, 4)


def test_layout_spec_svg_needs_a_path():
    with pytest.raises(ValueError, match="svg:file.svg"):
        parsed = parse_layout_spec("svg")
        parsed[0](SHAPE, 4)


def test_layout_spec_builds_for_rect_aspect_and_circle():
    builder, label, aspect = parse_layout_spec("rect@2.0")
    nails = builder(SHAPE, 4)

    # the aspect crop happens in the generate pipeline, the builder sees the
    # raw working shape
    assert label == "rect"
    assert aspect == 2.0
    assert all(0 <= n[0] < 64 for n in nails)
    assert all(0 <= n[1] < 64 for n in nails)

    builder, label, aspect = parse_layout_spec("circle")
    assert label == "circle" and aspect == 1.0
    assert builder(SHAPE, 4)


def test_resolve_threads_builtin_and_unknown():
    assert _resolve_threads("bw") == (None, False)
    assert _resolve_threads("wb") == (None, True)

    threads, wb = _resolve_threads("cmyk")
    assert wb is False
    assert len(threads) == 4

    with pytest.raises(PaletteError):
        _resolve_threads("no-such-palette")


def test_resolve_threads_cap_guard(monkeypatch):
    from restring import palettes

    monkeypatch.setattr(palettes, "MAX_THREADS", 2)

    with pytest.raises(ValueError, match="exceeds the cap"):
        _resolve_threads("cmyk")


def test_export_strength_alias_matches_the_fitted_rule():
    assert export_strength(1000) == resolve_export_strength(1000)


# --- render wrappers: thick variants and palette render ------------------------

def test_rgb_and_palette_thick_renders_match_classic_within_tolerance():
    rng = np.random.default_rng(11)
    img = image_from_numpy(rng.random((64, 64, 3)))
    canvas = init_canvas((64, 64, 3))
    _, orders = generate_rgb(img, SHAPE, NAILS,
                             Config(side_len=64, pull_amount=40, export_strength=0.1))

    # white canvas: black thread needs a negative strength
    classic = pull_order_to_array_rgb(orders, canvas, NAILS, strength=-0.1)
    thick = pull_order_to_array_rgb(orders, canvas, NAILS, strength=-0.1, thread_px=2.0)
    colors = [t.rgb for t in _resolve_threads("rgb")[0]]
    palette = pull_order_to_array_palette(orders, canvas, NAILS, colors, strength=-0.1)
    palette_thick = pull_order_to_array_palette(orders, canvas, NAILS, colors,
                                                strength=-0.1, thread_px=2.0)
    assert image_to_numpy(palette_thick).mean() <= image_to_numpy(palette).mean()

    classic_np, thick_np, palette_np = (image_to_numpy(x) for x in (classic, thick, palette))
    assert classic_np.shape == thick_np.shape == palette_np.shape
    # thicker lines darken more: the render cannot come out brighter overall
    assert thick_np.mean() < classic_np.mean()
    assert np.abs(palette_np - classic_np).mean() < 0.05  # rgb triple reproduces rgb mode


def test_bw_thick_render_darkens_and_keeps_shape():
    order = [0, 8, 0]
    classic = image_to_numpy(pull_order_to_array_bw(order, init_canvas(SHAPE), NAILS, -0.1))
    thick = image_to_numpy(
        pull_order_to_array_bw(order, init_canvas(SHAPE), NAILS, -0.1, thread_px=3.0))

    assert thick.shape == classic.shape
    assert thick.mean() < classic.mean()


# --- metrics and transformations wrappers --------------------------------------

def test_metric_wrappers_agree_with_core():
    rows = np.linspace(0.0, 1.0, 64).repeat(64).reshape(64, 64)
    a = image_from_numpy(rows)
    b = image_from_numpy(rows * 0.9 + 0.05)

    assert _core.mse(a, b) == pytest.approx(mse(a, b))
    assert _core.corr(a, b) == pytest.approx(corr(a, b))
    assert 0.0 <= blurred_ssim(a, b, radius=2) <= 1.0


def test_largest_rect_crops_tall_and_wide_images():
    # 80 x 40 against aspect 1.0: too tall, rows crop down to 40
    tall = image_from_numpy(np.ones((80, 40)) * 0.3)
    assert largest_rect(tall, 1.0).shape()[:2] == (40, 40)

    # 40 x 80 against aspect 1.0: too wide, columns crop down to 40
    wide = image_from_numpy(np.ones((40, 80)) * 0.3)
    assert largest_rect(wide, 1.0).shape()[:2] == (40, 40)


def test_thread_px_logs_both_branches(caplog):
    import logging

    from restring.generator import Config, _thread_px

    with caplog.at_level(logging.INFO, logger="restring.generator"):
        thin = _thread_px(Config(realistic=True, thread_width=0.2, canvas_size=400), 1200)
        thick = _thread_px(Config(realistic=True, thread_width=0.5, canvas_size=100), 400)

    assert thin == pytest.approx(0.6)
    assert thick == pytest.approx(2.0)
    assert any("below 1 px" in r.message for r in caplog.records)
    assert any("thread 2.00 px" in r.message for r in caplog.records)
