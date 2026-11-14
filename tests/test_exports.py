"""Machine exports: SVG paths, DXF lines, CSV/TXT winding orders."""

import csv
import io
import json
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from _helpers import save_image
from restring.cli import main
from restring.exports import dxf, paths_svg, winding_csv, winding_txt, write_export
from restring.palettes import builtin_palette
from restring.project import Project

NAILS = [(0, 0), (0, 9), (9, 9), (9, 0)]
ORDERS = [[0, 2, 1, 3], [0, 1, 2, 3]]


def make_project(mode="bw", palette=None):
    if mode == "bw":
        orders = ORDERS[:1]
    elif mode == "rgb":
        orders = [ORDERS[0], ORDERS[1], ORDERS[0]]
    else:
        orders = [ORDERS[i % len(ORDERS)] for i in range(len(palette))]
    return Project(mode=mode, config={"grid": 10, "wb": False}, nails=NAILS,
                   pull_orders=orders, input_digest="sha256:x", palette=palette)


def test_svg_one_polyline_per_thread():
    proj = make_project("palette", builtin_palette("cmy"))
    root = ET.fromstring(paths_svg(proj, canvas_size_mm=200))
    ns = {"svg": "http://www.w3.org/2000/svg"}
    lines = root.findall("svg:polyline", ns)
    assert len(lines) == 3
    assert len(lines[0].get("points").split()) == len(ORDERS[0])
    assert root.get("width") == "200mm"
    assert root.get("height") == "200mm"


def test_svg_keeps_the_grid_aspect():
    proj = make_project()
    proj.config["grid"] = [10, 20]
    root = ET.fromstring(paths_svg(proj, canvas_size_mm=200))
    assert root.get("width") == "200mm"
    assert root.get("height") == "100mm"


def test_dxf_one_line_per_pull_with_y_up():
    proj = make_project()
    text = dxf(proj, canvas_size_mm=100)
    assert text.count("\nLINE\n") == len(ORDERS[0]) - 1
    # nail (0, 0) is top-left: DXF y = height - row * scale = 100
    first = text.split("0\nLINE\n")[1]
    assert "10\n0.0000\n20\n100.0000" in first
    assert text.rstrip().endswith("EOF")


def test_csv_rows_match_pulls():
    proj = make_project("palette", builtin_palette("cmy"))
    rows = list(csv.reader(io.StringIO(winding_csv(proj))))
    assert rows[0] == ["thread", "pull", "from_nail", "to_nail"]
    assert len(rows) - 1 == 3 * (len(ORDERS[0]) - 1)
    assert rows[1] == ["1", "0", "0", "2"]


def test_txt_sequences():
    proj = make_project("palette", builtin_palette("cmy"))
    lines = winding_txt(proj).splitlines()
    sequences = [line for line in lines if not line.startswith("#")]
    assert len(sequences) == 3
    assert sequences[0] == "0 2 1 3"
    assert any("cyan" in line for line in lines)


def test_write_export_picks_format(tmp_path):
    proj = make_project()
    for name, marker in (("a.svg", "<svg"), ("a.dxf", "SECTION"),
                         ("a.csv", "thread,pull"), ("a.txt", "# nails:")):
        path = tmp_path / name
        write_export(proj, path)
        assert marker in path.read_text()
    with pytest.raises(ValueError, match="unknown export format"):
        write_export(proj, tmp_path / "a.png")


def test_cli_export_generate_and_project_modes(tmp_path):
    input_file = tmp_path / "in.png"
    save_image(input_file, np.random.default_rng(2).random((40, 40, 3)))
    project_file = tmp_path / "p.restring"

    # generate mode without --project-out
    main(["-i", str(input_file), "-o", str(tmp_path / "out.png"), "-d", "40", "-l", "30",
          "--rect", "--export", str(tmp_path / "art.svg")])
    assert ET.fromstring((tmp_path / "art.svg").read_text()).tag.endswith("svg")

    # project mode, palette colors survive the round trip
    main(["-i", str(input_file), "-o", str(tmp_path / "out2.png"), "-d", "40", "-l", "30",
          "--palette", "cmyk", "--project-out", str(project_file)])
    main(["--project", str(project_file), "-o", str(tmp_path / "out3.png"),
          "--export", str(tmp_path / "order.csv")])
    data = json.loads(project_file.read_text())
    rows = (tmp_path / "order.csv").read_text().splitlines()
    assert len(rows) - 1 == sum(len(o) - 1 for o in data["pull_orders"])


def test_cli_export_bad_extension_and_batch(tmp_path):
    input_file = tmp_path / "in.png"
    save_image(input_file, np.full((32, 32), 0.4))

    with pytest.raises(SystemExit):
        main(["-i", str(input_file), "-o", str(tmp_path / "o.png"), "-d", "32",
              "-l", "10", "--export", str(tmp_path / "o.png")])

    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()
    save_image(batch_dir / "a.png", np.full((32, 32), 0.4))
    with pytest.raises(SystemExit):
        main(["--batch", str(batch_dir), "-o", str(tmp_path / "out"),
              "--export", str(tmp_path / "art.svg")])