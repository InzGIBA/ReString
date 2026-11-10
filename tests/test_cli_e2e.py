import json

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


def test_cli_anim_end_to_end(tmp_path, caplog):
    import logging

    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))
    project_file = tmp_path / "p.restring"
    anim_file = tmp_path / "wind.gif"

    main(["-i", str(input_file), "-o", str(tmp_path / "out.png"), "-d", "40", "-l", "60",
          "--project-out", str(project_file)])

    with caplog.at_level(logging.INFO):
        main(["--project", str(project_file), "-o", str(tmp_path / "out2.png"),
              "--anim", str(anim_file), "--anim-frames", "12"])

    raw = anim_file.read_bytes()
    assert raw[:4] == b"GIF8"
    assert len(raw) > 1000
    assert any("Animation written" in r.message for r in caplog.records)

    with pytest.raises(SystemExit):
        main(["-i", str(input_file), "-o", str(tmp_path / "out3.png"), "--anim", str(anim_file)])


def test_cli_palette_cmyk(tmp_path):
    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))

    main(["-i", str(input_file), "-o", str(tmp_path / "cmyk.png"), "-d", "40", "-l", "60",
          "--palette", "cmyk"])
    out = load_rgb(tmp_path / "cmyk.png")
    assert out.shape == (40, 40, 3)
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_cli_palette_file(tmp_path):
    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))
    palette_file = tmp_path / "dmc.json"
    palette_file.write_text(json.dumps([
        {"comment": "starter subset"},
        {"name": "DMC 310 black", "rgb": [0.05, 0.05, 0.06]},
        {"name": "DMC 415 pearl gray", "rgb": [0.71, 0.71, 0.7]},
    ]))

    main(["-i", str(input_file), "-o", str(tmp_path / "dmc.png"), "-d", "40", "-l", "60",
          "--palette", str(palette_file)])
    assert (tmp_path / "dmc.png").exists()


def test_cli_rgb_wins_over_palette(tmp_path, caplog):
    import logging

    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))

    with caplog.at_level(logging.INFO):
        main(["-i", str(input_file), "-o", str(tmp_path / "out.png"), "-d", "40", "-l", "60",
              "--rgb", "--palette", "cmy"])
    assert any("ignoring --palette" in r.message for r in caplog.records)


def test_cli_metrics_report(tmp_path):
    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))
    metrics_file = tmp_path / "metrics.json"

    main(["-i", str(input_file), "-o", str(tmp_path / "out.png"), "-d", "40", "-l", "40",
          "--metrics", str(metrics_file)])

    report = json.loads(metrics_file.read_text())
    assert report["pulls"] >= 1
    assert report["nails"] >= 3
    assert 0.0 <= report["mse"] <= 1.0
    assert -1.0 <= report["corr"] <= 1.0
    assert 0.0 <= report["ssim"] <= 1.0
    assert 0.0 <= report["blurred_ssim"] <= 1.0


def test_cli_metrics_rejected_for_project(tmp_path):
    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))
    project_file = tmp_path / "p.restring"
    main(["-i", str(input_file), "-o", str(tmp_path / "out.png"), "-d", "40", "-l", "40",
          "--project-out", str(project_file)])

    with pytest.raises(SystemExit):
        main(["--project", str(project_file), "-o", str(tmp_path / "out2.png"),
              "--metrics", str(tmp_path / "m.json")])


def test_cli_layout_specs(tmp_path):
    from pathlib import Path

    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))

    for spec in ("polygon:5:80", "star:5:0.55:80", "rings:1.0:60,0.6:40"):
        main(["-i", str(input_file), "-o", str(tmp_path / f"{spec.replace(':', '_')}.png"),
              "-d", "40", "-l", "40", "--layout", spec])
        assert (tmp_path / f"{spec.replace(':', '_')}.png").exists()

    star_svg = Path(__file__).parent / "data" / "star_outline.svg"
    main(["-i", str(input_file), "-o", str(tmp_path / "svg.png"), "-d", "40", "-l", "40",
          "--layout", f"svg:{star_svg}:80"])
    assert (tmp_path / "svg.png").exists()


def test_cli_layout_grammar_errors(tmp_path):
    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))

    for spec in ("star:2", "polygon:2", "rings:1.4:50", "hexagon:6"):
        with pytest.raises(SystemExit):
            main(["-i", str(input_file), "-o", str(tmp_path / "bad.png"), "-d", "40",
                  "-l", "20", "--layout", spec])


def test_cli_layout_rect_conflict(tmp_path):
    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))

    with pytest.raises(SystemExit):
        main(["-i", str(input_file), "-o", str(tmp_path / "out.png"), "-d", "40", "-l", "20",
              "--rect", "--layout", "polygon:5"])


def test_cli_layout_aspect_crop(tmp_path):
    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 80, 3)))  # wide source

    main(["-i", str(input_file), "-o", str(tmp_path / "wide.png"), "-d", "40",
          "-l", "30", "--layout", "polygon:5:80@2.0"])
    assert (tmp_path / "wide.png").exists()


def test_cli_palette_project_out_rejected(tmp_path):
    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))

    with pytest.raises(SystemExit):
        main(["-i", str(input_file), "-o", str(tmp_path / "out.png"), "-d", "40", "-l", "60",
              "--palette", "cmyk", "--project-out", str(tmp_path / "p.restring")])


def test_cli_realistic_thread_width(tmp_path, caplog):
    import logging

    rng = np.random.default_rng(2)
    input_file = tmp_path / "in.png"
    save_image(input_file, rng.random((40, 40, 3)))

    with caplog.at_level(logging.INFO):
        main(["-i", str(input_file), "-o", str(tmp_path / "real.png"), "-d", "1200",
              "-l", "80", "--realistic", "--canvas-size", "400", "--thread-width", "0.2"])

    # the acceptance command: thread_px = 0.2 mm * 1200 px / 400 mm = 0.6 px
    assert any("thread 0.60 px" in r.message for r in caplog.records)
    assert any("below 1 px" in r.message for r in caplog.records)

    real = load_gray(tmp_path / "real.png")
    assert real.shape == (1200, 1200)
    assert real.min() >= 0.0 and real.max() <= 1.0


def test_resolve_export_strength():
    # fitted k = 104.0, residual band x1.06 (scripts/fit_export_strength.py)
    assert resolve_export_strength(1000) == pytest.approx(0.104)  # sweep anchor: best 0.1
    assert resolve_export_strength(2000) == pytest.approx(0.052)  # sweep anchor: best 0.05
    assert resolve_export_strength(50) == 0.2    # clamped at the ceiling
    assert resolve_export_strength(7000) == 0.03  # clamped at the floor


# --- CLI argument validation and the module entry point ------------------------

def test_cli_rejects_conflicting_and_missing_sources(tmp_path):
    input_file = tmp_path / "in.png"
    save_image(input_file, np.full((32, 32), 0.4))
    project = tmp_path / "p.restring"

    with pytest.raises(SystemExit) as e:
        main(["-i", str(input_file), "--project", str(project)])
    assert e.value.code == 2  # argparse usage error

    with pytest.raises(SystemExit) as e:
        main([])  # neither -i nor --project
    assert e.value.code == 2


def test_cli_metrics_needs_generate_mode(tmp_path):
    input_file = tmp_path / "in.png"
    save_image(input_file, np.full((32, 32), 0.4))
    project = tmp_path / "p.restring"
    main(["-i", str(input_file), "--project-out", str(project), "-d", "32"])

    with pytest.raises(SystemExit) as e:
        main(["--project", str(project), "--metrics", str(tmp_path / "m.json")])
    assert e.value.code == 2


def test_cli_anim_and_poster_require_their_inputs(tmp_path):
    input_file = tmp_path / "in.png"
    save_image(input_file, np.full((32, 32), 0.4))

    with pytest.raises(SystemExit):
        main(["-i", str(input_file), "--anim", str(tmp_path / "a.gif")])
    with pytest.raises(SystemExit):
        main(["-i", str(input_file), "--poster", str(tmp_path / "p.svg")])


def test_cli_project_mode_mismatch_is_an_error(tmp_path):
    input_file = tmp_path / "in.png"
    save_image(input_file, np.full((32, 32), 0.4))
    bw_project = tmp_path / "bw.restring"
    main(["-i", str(input_file), "--project-out", str(bw_project), "-d", "32"])

    with pytest.raises(SystemExit):
        main(["--project", str(bw_project), "--rgb", "-o", str(tmp_path / "o.png")])

    rgb_project = tmp_path / "rgb.restring"
    main(["-i", str(input_file), "--rgb", "--project-out", str(rgb_project), "-d", "32"])
    with pytest.raises(SystemExit):
        main(["--project", str(rgb_project), "-o", str(tmp_path / "o.png")])


def test_cli_unknown_palette_is_a_clean_error(tmp_path):
    input_file = tmp_path / "in.png"
    save_image(input_file, np.full((32, 32), 0.4))

    with pytest.raises(SystemExit) as e:
        main(["-i", str(input_file), "--palette", "no-such-palette",
              "-o", str(tmp_path / "o.png")])
    assert e.value.code == 2


def test_python_dash_m_entry_point(monkeypatch, capsys):
    import runpy

    # in-process module execution: argparse --help exits 0 after printing usage
    monkeypatch.setattr("sys.argv", ["restring", "--help"])
    with pytest.raises(SystemExit) as e:
        runpy.run_module("restring", run_name="__main__")
    assert e.value.code == 0
    assert "Create string art" in capsys.readouterr().out

    import subprocess
    import sys

    result = subprocess.run([sys.executable, "-m", "restring", "--help"],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert "Create string art" in result.stdout


def test_cli_metrics_with_layout_aspect_crops_the_target(tmp_path):
    # a 64 x 32 input with rect@2.0: aspect != 1 drives the largest_rect path
    input_file = tmp_path / "wide.png"
    save_image(input_file, np.full((32, 64), 0.4))
    metrics = tmp_path / "m.json"

    main(["-i", str(input_file), "-o", str(tmp_path / "o.png"), "-d", "32",
          "--layout", "rect@2.0", "--metrics", str(metrics), "-l", "40"])

    report = json.loads(metrics.read_text())
    assert report["mse"] >= 0.0
