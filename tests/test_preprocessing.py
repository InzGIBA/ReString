"""Photo preprocessing: crop, contrast, gamma, invert and weight maps."""

from pathlib import Path

import numpy as np
import pytest

from _helpers import image_from_numpy, image_to_numpy, save_image
from restring.api import GenerateOptions, continue_project, generate
from restring.cli import main
from restring.project import load as load_project
from restring.project import save as save_project

FIXTURE = Path(__file__).parent / "data" / "portrait_female.png"


def run(**overrides):
    options = GenerateOptions(layout="rect", nail_step=2, pulls=80, grid=64,
                              export_size=64, strength=0.1)
    for key, value in overrides.items():
        setattr(options, key, value)
    return generate(FIXTURE, options)


def test_adjust_contrast_gamma_invert():
    img = image_from_numpy([[0.2, 0.5, 0.8]])
    hard = image_to_numpy(img.adjust(2.0, 1.0, False))
    assert np.allclose(hard, [[0.0, 0.5, 1.0]])
    gamma = image_to_numpy(img.adjust(1.0, 2.0, False))
    assert np.allclose(gamma, [[0.04, 0.25, 0.64]])
    neg = image_to_numpy(img.adjust(1.0, 1.0, True))
    assert np.allclose(neg, [[0.8, 0.5, 0.2]])
    same = image_to_numpy(img.adjust(1.0, 1.0, False))
    assert np.allclose(same, [[0.2, 0.5, 0.8]])


def test_crop_bounds():
    img = image_from_numpy(np.arange(16, dtype=float).reshape(4, 4) / 16)
    cropped = img.crop(1, 1, 3, 3)
    assert cropped.shape() == (2, 2, 1)
    assert cropped.pixel(0, 0, 0) == pytest.approx(5 / 16)
    with pytest.raises(ValueError, match="outside"):
        img.crop(0, 0, 5, 4)
    with pytest.raises(ValueError, match="outside"):
        img.crop(2, 2, 2, 3)


def test_crop_changes_the_search():
    full = run()
    cropped = run(crop=(0.25, 0.25, 0.75, 0.75))
    assert full.pull_orders[0] != cropped.pull_orders[0]


def test_adjustments_change_the_search():
    base = run()
    for overrides in ({"contrast": 1.8}, {"gamma": 0.6}, {"invert": True}):
        assert run(**overrides).pull_orders[0] != base.pull_orders[0]


def test_invalid_preprocessing_values():
    with pytest.raises(ValueError, match="crop"):
        run(crop=(0.5, 0.5, 0.4, 0.9))
    with pytest.raises(ValueError, match="crop"):
        run(crop=(0.0, 0.0, 1.2, 1.0))
    with pytest.raises(ValueError, match="contrast"):
        run(contrast=0.0)
    with pytest.raises(ValueError, match="gamma"):
        run(gamma=-1.0)


def test_weight_map_steers_the_search(tmp_path):
    map_file = tmp_path / "map.png"
    grid = np.full((64, 64), 0.2)
    grid[16:48, 16:48] = 1.0
    save_image(map_file, grid)

    plain = run()
    weighted = run(weight_map=str(map_file))
    assert weighted.pull_orders[0] != plain.pull_orders[0]
    assert weighted.image.shape() == (64, 64, 1)


def test_cli_preprocessing_flags(tmp_path):
    input_file = tmp_path / "in.png"
    save_image(input_file, np.random.default_rng(2).random((40, 40, 3)))
    map_file = tmp_path / "map.png"
    save_image(map_file, np.full((40, 40), 0.7))

    main(["-i", str(input_file), "-o", str(tmp_path / "out.png"), "-d", "40", "-l", "30",
          "--crop", "0.1,0.1,0.9,0.9", "--contrast", "1.4", "--gamma", "0.8", "--invert",
          "--weight-map", str(map_file)])
    assert (tmp_path / "out.png").exists()

    with pytest.raises(SystemExit):
        main(["-i", str(input_file), "-o", str(tmp_path / "bad.png"), "-d", "40",
              "-l", "20", "--crop", "0.1,0.1,0.9"])


def test_continue_reproduces_preprocessed_target(tmp_path):
    options = GenerateOptions(layout="rect", nail_step=2, pulls=60, grid=64,
                              export_size=64, strength=0.1,
                              crop=(0.2, 0.2, 0.8, 0.8), contrast=1.5, gamma=0.9)
    run_result = generate(FIXTURE, options)
    path = tmp_path / "p.restring"
    save_project(path, mode="bw",
                 config={"grid": 64, "wb": False, "layout": "rect",
                         "crop": [0.2, 0.2, 0.8, 0.8], "contrast": 1.5, "gamma": 0.9},
                 nails=run_result.nails, pull_orders=run_result.pull_orders,
                 input_digest="sha256:x")

    continued = continue_project(FIXTURE, load_project(path), 40, strength=0.1, export_size=64)
    old = run_result.pull_orders[0]
    new = continued.pull_orders[0]
    assert new[:len(old)] == old
    assert len(new) > len(old)