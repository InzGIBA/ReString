"""Machine and plotter exports: vector thread paths and winding orders.

The poster is for hammering nails by hand; these formats are for machines
that draw or wind the pattern themselves. SVG carries one polyline per
thread at physical scale, DXF carries one LINE per pull (R12, the widest
reader support), CSV and TXT carry the raw nail-by-nail order. Everything
consumes a loaded project, no search runs here.
"""

from pathlib import Path

from restring.poster import thread_lengths_mm

RGB_TRIPLE = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
# AutoCAD color index per thread slot, for DXF layers
ACI_COLORS = [1, 3, 5, 2, 6, 4, 7, 8]


def _grid_sides(project):
    grid = project.config.get("grid", 300)
    return (float(grid), float(grid)) if isinstance(grid, int) else (float(grid[0]), float(grid[1]))


def _threads(project):
    """(name, rgb) per pull order: the physical thread colors."""
    if project.mode == "bw":
        wb = bool(project.config.get("wb", False))
        return [("white" if wb else "black", (1.0, 1.0, 1.0) if wb else (0.0, 0.0, 0.0))]
    if project.mode == "rgb":
        return list(zip(("red", "green", "blue"), RGB_TRIPLE))
    return [(t.name, t.rgb) for t in project.palette]


def _hex(rgb):
    return "#" + "".join(f"{round(v * 255):02x}" for v in rgb)


def _board_mm(project, canvas_size_mm):
    gh, gw = _grid_sides(project)
    return canvas_size_mm, canvas_size_mm * gh / gw, gh, gw


def paths_svg(project, *, canvas_size_mm=400.0, thread_width_mm=0.2):
    """The thread pattern as vector paths: one polyline per thread, board
    width `canvas_size_mm`, height following the working-grid aspect."""
    width, height, gh, gw = _board_mm(project, canvas_size_mm)
    sx, sy = width / gw, height / gh
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
           f'width="{width:g}mm" height="{height:g}mm" viewBox="0 0 {width:g} {height:g}">',
           f'<rect x="0" y="0" width="{width:g}" height="{height:g}" fill="none" '
           f'stroke="#888888" stroke-width="0.2"/>']
    for (name, rgb), order in zip(_threads(project), project.pull_orders):
        points = " ".join(f"{project.nails[i][1] * sx:.3f},{project.nails[i][0] * sy:.3f}"
                          for i in order)
        out.append(f'<polyline points="{points}" fill="none" stroke="{_hex(rgb)}" '
                   f'stroke-width="{thread_width_mm:g}" stroke-linecap="round" '
                   f'data-thread="{name}"/>')
    out.append("</svg>")
    return "\n".join(out)


def dxf(project, *, canvas_size_mm=400.0):
    """One LINE entity per pull, layer per thread, Y up (DXF convention).
    Minimal R12: plotters and CAD readers accept it without tables."""
    width, height, gh, gw = _board_mm(project, canvas_size_mm)
    sx, sy = width / gw, height / gh

    def xy(nail):
        return nail[1] * sx, height - nail[0] * sy

    out = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "0", "ENDSEC",
           "0", "SECTION", "2", "ENTITIES"]
    for slot, order in enumerate(project.pull_orders, start=1):
        layer = f"THREAD_{slot}"
        color = ACI_COLORS[(slot - 1) % len(ACI_COLORS)]
        for a, b in zip(order, order[1:]):
            x1, y1 = xy(project.nails[a])
            x2, y2 = xy(project.nails[b])
            out += ["0", "LINE", "8", layer, "62", str(color),
                    "10", f"{x1:.4f}", "20", f"{y1:.4f}", "30", "0.0",
                    "11", f"{x2:.4f}", "21", f"{y2:.4f}", "31", "0.0"]
    out += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(out) + "\n"


def winding_csv(project):
    """One row per pull: thread (1-based), pull index, from nail, to nail."""
    rows = ["thread,pull,from_nail,to_nail"]
    for slot, order in enumerate(project.pull_orders, start=1):
        for pull, (a, b) in enumerate(zip(order, order[1:])):
            rows.append(f"{slot},{pull},{a},{b}")
    return "\n".join(rows) + "\n"


def winding_txt(project):
    """Comment header plus one space-separated nail sequence per thread."""
    threads = _threads(project)
    lengths = thread_lengths_mm(project, 400.0)
    out = [f"# nails: {len(project.nails)}",
           f"# threads: {len(threads)}"]
    for slot, ((name, _rgb), order) in enumerate(zip(threads, project.pull_orders), start=1):
        out.append(f"# thread {slot}: {name}, {len(order) - 1} pulls, "
                   f"{lengths[slot - 1] / 1000:.0f} m at 400 mm board")
    for order in project.pull_orders:
        out.append(" ".join(str(i) for i in order))
    return "\n".join(out) + "\n"


EXPORT_FORMATS = {".svg": paths_svg, ".dxf": dxf, ".csv": winding_csv, ".txt": winding_txt}


def write_export(project, path, *, canvas_size_mm=400.0):
    """Write the export format picked by the file extension. Returns the
    format name; raises ValueError on an unknown extension."""
    suffix = Path(path).suffix.lower()
    if suffix not in EXPORT_FORMATS:
        raise ValueError(f"unknown export format {suffix!r}: use .svg, .dxf, .csv or .txt")
    if suffix in (".svg", ".dxf"):
        content = EXPORT_FORMATS[suffix](project, canvas_size_mm=canvas_size_mm)
    else:
        content = EXPORT_FORMATS[suffix](project)
    Path(path).write_text(content)
    return suffix