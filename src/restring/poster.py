"""Winding poster: printable SVG instructions and thread length math.

Everything is stdlib string templating, SVG 1.1 with a viewBox in
millimeters, sized for A-series printing (A3 landscape by default). The
geometry consumes a loaded project (docs/project-format.md); no search runs
here.
"""

import math

import restring

LEAD_IN_MM = 150.0   # tail before nail 0 and tail after the last nail, per thread
SLACK = 1.05         # handling slack: sag, knots, re-winds
PAGE_W_MM = 420.0    # A3 landscape
PAGE_H_MM = 297.0
MARGIN_MM = 10.0
FOOTER_MM = 16.0

CHANNEL_COLORS = ["#c22222", "#22a04a", "#2244cc"]
NAIL_COLOR = "#222222"
START_COLOR = "#c22222"


def _grid_sides(project):
    grid = project.config.get("grid", 300)
    return (float(grid), float(grid)) if isinstance(grid, int) else (float(grid[0]), float(grid[1]))


def thread_lengths_mm(project, canvas_size_mm):
    """Thread length per pull order in millimeters: scaled chord distances,
    times the handling slack, plus the lead-in tails."""
    gh, gw = _grid_sides(project)
    sy = canvas_size_mm / gh
    sx = canvas_size_mm / gw
    lengths = []
    for order in project.pull_orders:
        dist = 0.0
        for a, b in zip(order, order[1:]):
            (r1, c1), (r2, c2) = project.nails[a], project.nails[b]
            dist += math.hypot((r2 - r1) * sy, (c2 - c1) * sx)
        lengths.append(dist * SLACK + 2 * LEAD_IN_MM)
    return lengths


def thread_length_mm(project, canvas_size_mm):
    """Total thread across all pull orders, in millimeters."""
    return sum(thread_lengths_mm(project, canvas_size_mm))


def poster_svg(project, *, canvas_size_mm=260.0, number_every=10, show_preview=False,
               page_size_mm=(PAGE_W_MM, PAGE_H_MM)):
    """Render the winding instructions as an SVG string.

    The board sits to scale on an A3 landscape page, nails numbered every
    `number_every` nails in nail-list order (0 = none, 1 = all), so pull
    index N on the poster matches pull index N in the project.
    """
    pw, ph = page_size_mm
    max_board = min(pw, ph) - 2 * MARGIN_MM - FOOTER_MM
    if not 0 < canvas_size_mm <= max_board:
        raise ValueError(f"board of {canvas_size_mm:g} mm does not fit the page "
                         f"({pw:g} x {ph:g} mm), max {max_board:g} mm")
    if number_every < 0:
        raise ValueError("number_every must be 0 (none) or a positive int")

    gh, gw = _grid_sides(project)
    board_x = (pw - canvas_size_mm) / 2
    board_y = MARGIN_MM
    sx = canvas_size_mm / gw
    sy = canvas_size_mm / gh
    center_r, center_c = gh / 2, gw / 2

    def xy(nail):
        return board_x + nail[1] * sx, board_y + nail[0] * sy

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
           f'width="{pw:g}mm" height="{ph:g}mm" viewBox="0 0 {pw:g} {ph:g}">',
           f'<rect x="0" y="0" width="{pw:g}" height="{ph:g}" fill="white"/>',
           f'<rect x="{board_x:g}" y="{board_y:g}" width="{canvas_size_mm:g}" '
           f'height="{canvas_size_mm:g}" fill="none" stroke="{NAIL_COLOR}" stroke-width="0.3"/>']

    if show_preview:
        colors = CHANNEL_COLORS if project.mode == "rgb" else [NAIL_COLOR]
        for order, color in zip(project.pull_orders, colors):
            segments = " ".join(
                f'<line x1="{xy(project.nails[a])[0]:.2f}" y1="{xy(project.nails[a])[1]:.2f}" '
                f'x2="{xy(project.nails[b])[0]:.2f}" y2="{xy(project.nails[b])[1]:.2f}"/>'
                for a, b in zip(order, order[1:]))
            out.append(f'<g stroke="{color}" stroke-width="0.25" opacity="0.1">{segments}</g>')

    # nails: one 2 mm dot each, the starting nail marked in red
    for i, nail in enumerate(project.nails):
        x, y = xy(nail)
        if i == 0:
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.5" fill="white" '
                       f'stroke="{START_COLOR}" stroke-width="0.5"/>')
        else:
            out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1" fill="{NAIL_COLOR}"/>')

    # numbering in nail-list order: pull index N on the poster is nail N
    if number_every > 0:
        labels = []
        for i, nail in enumerate(project.nails):
            if i % number_every:
                continue
            x, y = xy(nail)
            dx, dy = nail[1] - center_c, nail[0] - center_r
            norm = math.hypot(dx, dy) or 1.0
            lx = x + dx / norm * 4.5
            ly = y + dy / norm * 4.5 + 0.9
            labels.append(f'<text x="{lx:.2f}" y="{ly:.2f}" font-size="2.6" '
                          f'font-family="Helvetica, Arial, sans-serif" fill="{NAIL_COLOR}" '
                          f'text-anchor="middle">{i}</text>')
        out.append("".join(labels))

    # footer: nail count, pull counts, thread lengths, version, date
    n_nails = len(project.nails)
    pulls = [len(order) - 1 for order in project.pull_orders]
    lengths_mm = thread_lengths_mm(project, canvas_size_mm)
    lengths_m = [length / 1000 for length in lengths_mm]
    if project.mode == "rgb":
        thread_info = (f"Threads: 3 (R/G/B), thread lengths: "
                       f"{'/'.join(f'{value:.0f}' for value in lengths_m)} m")
    else:
        thread_info = f"Threads: 1, thread length: {lengths_m[0]:.0f} m"
    date = project.created or "-"
    out.append(
        f'<text x="{MARGIN_MM}" y="{ph - FOOTER_MM + 4}" font-size="3.4" '
        f'font-family="Helvetica, Arial, sans-serif" fill="{NAIL_COLOR}">'
        f'Nails: {n_nails}, Pulls: {"/".join(str(p) for p in pulls)}, {thread_info}</text>')
    out.append(
        f'<text x="{MARGIN_MM}" y="{ph - FOOTER_MM + 9}" font-size="3" '
        f'font-family="Helvetica, Arial, sans-serif" fill="{NAIL_COLOR}">'
        f'ReString {restring.__version__}, {date}, board {canvas_size_mm:g} mm, '
        f'print at 100% scale</text>')
    out.append("</svg>")
    return "\n".join(out)
