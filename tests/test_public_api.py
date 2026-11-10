"""Public API contract: the facade's names, signatures, defaults and result
fields are pinned here. Any breaking change to the documented surface fails
this file."""

import dataclasses
import inspect
import json

import numpy as np
import pytest

import restring
from _helpers import image_from_numpy
from restring.api import GenerateOptions, Result, Stats, generate

SHAPE = (64, 64)


def seeded_image():
    rng = np.random.default_rng(5)
    return image_from_numpy(rng.random((64, 64, 3)))


def test_all_exports_the_facade_plus_the_legacy_names():
    assert set(restring.__all__) == {
        "Config", "GenerateOptions", "Result", "Stats", "generate",
        "generate_bw", "generate_rgb",
    }


def test_generate_signature():
    params = inspect.signature(generate).parameters
    assert list(params) == ["source", "options"]
    assert params["options"].default is None


def test_generate_options_fields_and_defaults():
    fields = dataclasses.fields(GenerateOptions)
    expected = {
        "layout": "rect", "nail_step": 4, "pulls": None, "strength": None,
        "palette": "bw", "grid": 300, "export_size": 300, "weight": None,
        "min_chord": None, "rollback": False, "realistic": False,
        "canvas_size": 400.0, "thread_width": 0.2,
        "radius1_multiplier": 1.0, "radius2_multiplier": 1.0,
    }
    assert {f.name: f.default for f in fields} == expected


def test_result_and_stats_fields():
    assert [f.name for f in dataclasses.fields(Result)] == [
        "image", "pull_orders", "nails", "options", "stats"]
    assert [f.name for f in dataclasses.fields(Stats)] == [
        "pulls_per_thread", "nails", "elapsed_s"]


def test_generate_end_to_end(tmp_path):
    img = seeded_image()
    options = GenerateOptions(layout="rect", nail_step=4, pulls=60, export_size=64,
                              grid=64, strength=0.1)
    result = generate(img, options)

    assert result.image.shape() == (64, 64, 1)
    assert len(result.pull_orders) == 1
    assert len(result.pull_orders[0]) - 1 == result.stats.pulls_per_thread[0]
    assert result.stats.nails == len(result.nails)
    assert result.options == options

    png = tmp_path / "out.png"
    result.image.save_png(str(png))
    assert png.exists()


def test_generate_accepts_a_path(tmp_path):
    from _helpers import save_image

    source = tmp_path / "in.png"
    save_image(source, np.random.default_rng(2).random((40, 40, 3)))
    result = generate(source, GenerateOptions(pulls=30, grid=40, export_size=40))
    assert result.image.shape() == (40, 40, 1)


def test_generate_accepts_bytes(tmp_path):
    from _helpers import save_image

    source = tmp_path / "in.png"
    save_image(source, np.random.default_rng(2).random((40, 40, 3)))
    result = generate(source.read_bytes(), GenerateOptions(pulls=30, grid=40, export_size=40))
    assert result.image.shape() == (40, 40, 1)


def test_layout_specs_parse():
    from restring.api import parse_layout_spec

    for spec in ("circle", "rect", "polygon:5:80", "star:5:0.55:80",
                 "rings:1.0:60,0.6:40", "polygon:5:80@1.5"):
        builder, label, aspect = parse_layout_spec(spec)
        assert callable(builder) and label and 0.1 <= aspect <= 10.0
    with pytest.raises(ValueError, match="unknown layout"):
        parse_layout_spec("hexagon:6")
    with pytest.raises(ValueError, match="star:points:inner"):
        parse_layout_spec("star:5")


def test_layout_builder_validates_geometry():
    # parse-time checks cover the grammar; geometry checks fire on build
    from restring.api import parse_layout_spec

    # star:2 surfaces at build time through generate()/the CLI (ValueError
    # caught and converted to an argparse error there)
    builder_star, _, _ = parse_layout_spec("star:2:0.5")
    with pytest.raises(ValueError, match="star points must be >= 3"):
        builder_star((64, 64), 4)
    builder5, _, _ = parse_layout_spec("polygon:2")
    with pytest.raises(ValueError, match="polygon sides must be >= 3"):
        builder5((64, 64), 4)
    builder_inner, _, _ = parse_layout_spec("star:5:1.2")
    with pytest.raises(ValueError, match="inner_radius must sit in"):
        builder_inner((64, 64), 4)


def test_legacy_wrappers_still_work_and_warn():
    img = seeded_image()
    nails = [(0, 0), (0, 63), (63, 63)]
    config = restring.Config(side_len=64, pull_amount=20, export_strength=0.1)
    with pytest.deprecated_call(match="deprecated since 2.0"):
        result, order = restring.generate_bw(img, (64, 64), nails, config)
    assert len(order) >= 2
    with pytest.deprecated_call(match="deprecated since 2.0"):
        result_rgb, orders = restring.generate_rgb(img, (64, 64), nails, config)
    assert len(orders) == 3


def test_options_round_trip_through_json():
    options = GenerateOptions(layout="polygon:5", pulls=100)
    payload = json.dumps(dataclasses.asdict(options))
    loaded = GenerateOptions(**json.loads(payload))
    assert loaded == options
