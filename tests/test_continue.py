"""Resume: continue_art replays a stored order and appends new pulls on the
same uncut thread. The continuation must match a fresh run at the combined
budget while the search keeps improving."""

import json
from pathlib import Path

import numpy as np
import pytest

from _helpers import load_gray, save_image
from restring import _core
from restring.api import GenerateOptions, continue_project, generate
from restring.cli import main
from restring.image_transformations import largest_square, resize
from restring.nails import create_circle_nail_positions
from restring.palettes import builtin_palette
from restring.project import load as load_project
from restring.project import save as save_project

FIXTURE = Path(__file__).parent / "data" / "portrait_female.png"
SHAPE = (64, 64)


def working_target():
    img = resize(largest_square(_core.Image.load(str(FIXTURE))), SHAPE)
    return img.gray(0.9)


def test_continue_matches_a_fresh_run():
    target = working_target()
    nails = create_circle_nail_positions(SHAPE, nail_step=4)

    prefix, _ = _core.create_art(nails, target, -0.05, 60, None, True, None, None, False, None)
    continued, _ = _core.continue_art(nails, target, prefix, -0.05, 60, None, True,
                                      None, None, False, None)
    fresh, _ = _core.create_art(nails, target, -0.05, 120, None, True, None, None, False, None)

    assert continued[:len(prefix)] == prefix
    assert continued == fresh


def test_continue_rejects_an_empty_order():
    target = working_target()
    nails = create_circle_nail_positions(SHAPE, nail_step=4)
    with pytest.raises(ValueError, match="non-empty"):
        _core.continue_art(nails, target, [], -0.05, 10, None, True, None, None, False, None)


def test_continue_project_extends_bw_orders(tmp_path):
    options = GenerateOptions(layout="rect", nail_step=2, pulls=60, grid=64,
                              export_size=64, strength=0.1)
    run = generate(FIXTURE, options)
    path = tmp_path / "p.restring"
    save_project(path, mode="bw", config={"grid": 64, "wb": False, "layout": "rect"},
                 nails=run.nails, pull_orders=run.pull_orders, input_digest="sha256:x")

    proj = load_project(path)
    continued = continue_project(FIXTURE, proj, 40, strength=0.1, export_size=64)

    old = run.pull_orders[0]
    new = continued.pull_orders[0]
    assert new[:len(old)] == old
    assert len(new) > len(old)
    assert continued.stats.pulls_per_thread == [len(new) - 1]
    assert continued.image.shape() == (64, 64, 1)


def test_continue_project_extends_palette_orders(tmp_path):
    options = GenerateOptions(layout="rect", nail_step=2, pulls=50, grid=64,
                              export_size=64, strength=0.1, palette="cmyk")
    run = generate(FIXTURE, options)
    threads = builtin_palette("cmyk")
    path = tmp_path / "p.restring"
    save_project(path, mode="palette", config={"grid": 64, "wb": False, "layout": "rect"},
                 nails=run.nails, pull_orders=run.pull_orders, input_digest="sha256:x",
                 palette=threads)

    proj = load_project(path)
    continued = continue_project(FIXTURE, proj, 30, strength=0.1, export_size=64)

    assert len(continued.pull_orders) == 4
    for old, new in zip(run.pull_orders, continued.pull_orders):
        assert new[:len(old)] == old
        assert len(new) >= len(old)
    assert continued.options.palette == "cmyk"


def test_continue_project_wb(tmp_path):
    options = GenerateOptions(layout="rect", nail_step=2, pulls=50, grid=64,
                              export_size=64, strength=0.1, palette="wb")
    run = generate(FIXTURE, options)
    path = tmp_path / "p.restring"
    save_project(path, mode="bw", config={"grid": 64, "wb": True, "layout": "rect"},
                 nails=run.nails, pull_orders=run.pull_orders, input_digest="sha256:x")

    continued = continue_project(FIXTURE, load_project(path), 30, strength=0.1, export_size=64)
    assert continued.pull_orders[0][:51] == run.pull_orders[0]
    assert continued.options.palette == "wb"


def test_continue_project_rejects_zero_extra(tmp_path):
    options = GenerateOptions(pulls=20, grid=64, export_size=64)
    run = generate(FIXTURE, options)
    path = tmp_path / "p.restring"
    save_project(path, mode="bw", config={"grid": 64}, nails=run.nails,
                 pull_orders=run.pull_orders, input_digest="sha256:x")
    with pytest.raises(ValueError, match="extra_pulls"):
        continue_project(FIXTURE, load_project(path), 0)


def test_cli_extra_pulls_round_trip(tmp_path):
    input_file = tmp_path / "in.png"
    save_image(input_file, np.random.default_rng(2).random((40, 40, 3)))
    project_file = tmp_path / "p.restring"
    bigger_file = tmp_path / "bigger.restring"

    main(["-i", str(input_file), "-o", str(tmp_path / "out.png"), "-d", "40", "-l", "40",
          "--rect", "--project-out", str(project_file)])
    main(["--project", str(project_file), "-i", str(input_file), "--extra-pulls", "30",
          "-o", str(tmp_path / "continued.png"), "-d", "40",
          "--project-out", str(bigger_file)])

    old = json.loads(project_file.read_text())["pull_orders"][0]
    new = json.loads(bigger_file.read_text())["pull_orders"][0]
    assert new[:len(old)] == old
    assert len(new) > len(old)
    assert load_gray(tmp_path / "continued.png").shape == (40, 40)


def test_cli_extra_pulls_validation(tmp_path):
    input_file = tmp_path / "in.png"
    save_image(input_file, np.full((32, 32), 0.4))
    project_file = tmp_path / "p.restring"
    main(["-i", str(input_file), "--project-out", str(project_file), "-d", "32", "-l", "20"])

    # --extra-pulls without -i
    with pytest.raises(SystemExit):
        main(["--project", str(project_file), "--extra-pulls", "10",
              "-o", str(tmp_path / "o.png")])
    # --extra-pulls without --project
    with pytest.raises(SystemExit):
        main(["-i", str(input_file), "--extra-pulls", "10", "-o", str(tmp_path / "o.png")])
    # -i with --project but no --extra-pulls stays forbidden
    with pytest.raises(SystemExit):
        main(["--project", str(project_file), "-i", str(input_file),
              "-o", str(tmp_path / "o.png")])