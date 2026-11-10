import numpy as np

import restring
from _helpers import image_from_numpy, image_to_numpy, save_image
from restring.cli import build_parser, main
from restring.generator import Config, generate_bw
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
    assert args.export_strength == 0.1
    assert args.pull_amount is None
    assert args.random_nails is None
    assert args.radius1_multiplier == 1
    assert args.radius2_multiplier == 1
    assert args.nail_step == 4
    assert args.weight_peak is None
    assert args.min_chord is None
    assert not (args.wb or args.rgb or args.rect)


def test_parser_accepts_all_flags():
    argv = ["-i", "a.png", "-o", "b.png", "-d", "50", "-s", "0.2", "-l", "10",
            "-r", "7", "-r1", "1.2", "-r2", "0.8", "-n", "3", "--weight", "3",
            "--min-chord", "20", "--wb", "--rgb", "--rect"]

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
