import numpy as np
import pytest

import restring
from _helpers import image_from_numpy, image_to_numpy, load_gray, load_rgb, save_image
from restring.cli import build_parser, main
from restring.generator import Config, generate_bw, resolve_export_strength
from restring.nails import create_circle_nail_positions


def test_package_import_has_no_side_effects():
    # importing must neither parse CLI arguments nor configure logging
    import restring.cli as cli

    assert restring.__version__
    assert not hasattr(cli, "args")
    assert not hasattr(cli, "parser")


def test_parser_defaults():
    args = build_parser().parse_args(["-i", "in.png"])

    assert args.input_file == "in.png"
    assert args.output_file == "output.png"
    assert args.side_len == 300
    assert args.export_strength is None  # auto: fitted from the pull count
    assert args.pull_amount is None
    assert args.random_nails is None
    assert args.radius1_multiplier == 1
    assert args.radius2_multiplier == 1
    assert args.nail_step == 4
    assert args.weight_peak is None
    assert args.min_chord is None
    assert args.project is None
    assert args.project_out is None
    assert not (args.wb or args.rgb or args.rect)


def test_parser_accepts_all_flags():
    argv = ["-i", "a.png", "-o", "b.png", "-d", "50", "-s", "0.2", "-l", "10",
            "-r", "7", "-r1", "1.2", "-r2", "0.8", "-n", "3", "--weight", "3",
            "--min-chord", "20", "--project", "a.restring", "--project-out", "b.restring",
            "--wb", "--rgb", "--rect"]

    args = build_parser().parse_args(argv)

    assert (args.input_file, args.output_file) == ("a.png", "b.png")
    assert args.side_len == 50
    assert args.export_strength == 0.2
    assert args.pull_amount == 10
    assert args.random_nails == 7
    assert (args.radius1_multiplier, args.radius2_multiplier) == (1.2, 0.8)
    assert args.nail_step == 3
    assert args.weight_peak == 3.0
    assert args.min_chord == 20.0
    assert (args.project, args.project_out) == ("a.restring", "b.restring")
    assert args.wb and args.rgb and args.rect


def test_generate_bw_smoke():
    rng = np.random.default_rng(1)
    img = image_from_numpy(rng.random((32, 32, 3)))
    shape = (32, 32)
    nails = create_circle_nail_positions(shape, nail_step=4)
    config = Config(side_len=64, pull_amount=30, export_strength=0.1)

    result, pull_order = generate_bw(img, shape, nails, config)

    arr = image_to_numpy(result)
    assert result.shape() == (64, 64, 1)
    assert arr.min() >= 0.0
    assert arr.max() <= 1.0
    assert len(pull_order) >= 2


def test_cli_min_chord_smoke(tmp_path):
    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))
    output_file = tmp_path / "out.png"

    main(["-i", str(input_file), "-o", str(output_file), "-d", "40", "-l", "30",
          "--min-chord", "10"])

    assert output_file.exists()


def test_cli_project_round_trip_bw(tmp_path, caplog):
    import logging

    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))
    project_file = tmp_path / "p.restring"

    main(["-i", str(input_file), "-o", str(tmp_path / "direct.png"), "-d", "40",
          "-l", "60", "--rect", "--project-out", str(project_file)])
    assert project_file.exists()

    with caplog.at_level(logging.INFO):
        main(["--project", str(project_file), "-o", str(tmp_path / "rerender.png"),
              "-d", "40"])

    assert np.array_equal(load_gray(tmp_path / "direct.png"),
                          load_gray(tmp_path / "rerender.png"))
    assert any("Re-render from project" in r.message for r in caplog.records)


def test_cli_project_round_trip_rgb(tmp_path):
    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))
    project_file = tmp_path / "p.restring"

    main(["-i", str(input_file), "-o", str(tmp_path / "direct.png"), "-d", "40",
          "-l", "60", "--rgb", "--project-out", str(project_file)])
    main(["--project", str(project_file), "--rgb", "-o", str(tmp_path / "rerender.png"),
          "-d", "40"])

    assert np.array_equal(load_rgb(tmp_path / "direct.png"),
                          load_rgb(tmp_path / "rerender.png"))


def test_cli_project_rejects_input_combo(tmp_path):
    with pytest.raises(SystemExit):
        main(["--project", "p.restring", "-i", "in.png", "-o", "out.png"])


def test_cli_poster_end_to_end(tmp_path):
    import xml.etree.ElementTree as ET

    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))
    project_file = tmp_path / "p.restring"
    poster_file = tmp_path / "poster.svg"

    # poster straight from a generate run
    main(["-i", str(input_file), "-o", str(tmp_path / "out.png"), "-d", "40", "-l", "60",
          "--rect", "--project-out", str(project_file), "--poster", str(poster_file)])
    assert ET.fromstring(poster_file.read_text()).tag.endswith("svg")

    # and from an existing project
    poster_file.unlink()
    main(["--project", str(project_file), "-o", str(tmp_path / "out2.png"),
          "--poster", str(poster_file)])
    assert ET.fromstring(poster_file.read_text()).tag.endswith("svg")


def test_resolve_export_strength():
    # fitted k = 104.0, residual band x1.06 (scripts/fit_export_strength.py)
    assert resolve_export_strength(1000) == pytest.approx(0.104)  # sweep anchor: best 0.1
    assert resolve_export_strength(2000) == pytest.approx(0.052)  # sweep anchor: best 0.05
    assert resolve_export_strength(50) == 0.2    # clamped at the ceiling
    assert resolve_export_strength(7000) == 0.03  # clamped at the floor
