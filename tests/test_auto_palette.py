"""Auto palettes: k-means suggestions, DMC snapping, configurable cap."""

import json
from pathlib import Path

import numpy as np
import pytest

from _helpers import image_from_numpy, save_image
from restring import _core
from restring.api import GenerateOptions, generate
from restring.auto_palette import (
    kmeans_colors,
    parse_spec,
    snap_to_chart,
    suggest_palette,
)
from restring.cli import main
from restring.palettes import ThreadColor, builtin_palette, load_palette

FIXTURE = Path(__file__).parent / "data" / "portrait_female.png"


def two_color_image():
    grid = np.zeros((32, 32, 3))
    grid[:16, :, 0] = 0.9  # red top half
    grid[16:, :, 2] = 0.9  # blue bottom half
    return image_from_numpy(grid)


def test_kmeans_finds_the_two_colors():
    centers = kmeans_colors(two_color_image(), 2, seed=1)
    centers = sorted(centers)
    assert centers[0][2] > 0.8 and centers[0][0] < 0.1
    assert centers[1][0] > 0.8 and centers[1][2] < 0.1


def test_suggestion_is_deterministic():
    img = _core.Image.load(str(FIXTURE))
    a = suggest_palette(img, 4, seed=7)
    b = suggest_palette(img, 4, seed=7)
    assert [t.rgb for t in a] == [t.rgb for t in b]
    assert len(a) == 4


def test_snap_to_chart_deduplicates():
    chart = builtin_palette("cmy")
    threads = [ThreadColor("x", (0.01, 0.99, 0.99)), ThreadColor("y", (0.02, 0.98, 0.98)),
               ThreadColor("z", (0.99, 0.01, 0.99))]
    snapped = snap_to_chart(threads, chart)
    assert [t.name for t in snapped] == ["cyan", "magenta"]


def test_parse_spec():
    k, chart = parse_spec("auto:4")
    assert k == 4 and chart is None
    k, chart = parse_spec("auto:4:dmc")
    assert k == 4 and chart.is_file()
    for bad in ("auto", "auto:0", "auto:x", "auto:2:no-such-chart.json", "auto:1:2:3"):
        with pytest.raises(ValueError):
            parse_spec(bad)


def test_generate_with_auto_palette():
    options = GenerateOptions(layout="rect", nail_step=2, pulls=40, grid=64,
                              export_size=64, strength=0.1, palette="auto:3")
    result = generate(FIXTURE, options)
    assert len(result.pull_orders) == 3
    assert len(result.palette) == 3
    assert result.image.shape() == (64, 64, 3)
    assert all(t.name.startswith("auto ") for t in result.palette)


def test_generate_with_dmc_snapping():
    options = GenerateOptions(layout="rect", nail_step=2, pulls=40, grid=64,
                              export_size=64, strength=0.1, palette="auto:4:dmc")
    result = generate(FIXTURE, options)
    assert 1 <= len(result.palette) <= 4
    assert all(t.name.startswith("DMC") for t in result.palette)


def test_cli_auto_palette_project(tmp_path):
    input_file = tmp_path / "in.png"
    save_image(input_file, np.random.default_rng(2).random((40, 40, 3)))
    project_file = tmp_path / "p.restring"

    main(["-i", str(input_file), "-o", str(tmp_path / "out.png"), "-d", "40", "-l", "30",
          "--palette", "auto:3", "--project-out", str(project_file)])

    data = json.loads(project_file.read_text())
    assert data["mode"] == "palette"
    assert len(data["palette"]) == 3
    assert len(data["pull_orders"]) == 3


def test_cli_max_threads_cap(tmp_path):
    input_file = tmp_path / "in.png"
    save_image(input_file, np.random.default_rng(2).random((40, 40, 3)))
    palette_file = tmp_path / "nine.json"
    palette_file.write_text(json.dumps([
        {"name": f"c{i}", "rgb": [i / 9, 0.2, 0.3]} for i in range(9)
    ]))

    with pytest.raises(SystemExit):
        main(["-i", str(input_file), "-o", str(tmp_path / "o.png"), "-d", "40", "-l", "20",
              "--palette", str(palette_file)])

    main(["-i", str(input_file), "-o", str(tmp_path / "o.png"), "-d", "40", "-l", "20",
          "--palette", str(palette_file), "--max-threads", "9"])
    assert (tmp_path / "o.png").exists()

    with pytest.raises(SystemExit):
        main(["-i", str(input_file), "-o", str(tmp_path / "o.png"), "-d", "40", "-l", "20",
              "--palette", "auto:3", "--max-threads", "2"])


def test_chart_loads_beyond_the_cap():
    chart = load_palette(Path(__file__).parent.parent / "src" / "restring" / "data" / "dmc.json",
                         max_threads=None)
    assert len(chart) == 20