"""Adaptive nail placement (prototype, measured and rejected as a default).

Candidates sit evenly on the board perimeter; each candidate scores by the
mean Sobel gradient magnitude within a fixed radius; a greedy pass picks the
top-scored candidates while keeping every pick at least one candidate slot
away from the others. Prototype quality: pure Python, small grids.
"""

import logging
import math

from restring import _core

logger = logging.getLogger(__name__)

SCORE_RADIUS_PX = 40


def perimeter_candidates(shape, m, layout):
    """M evenly spaced perimeter positions (row, col) floats: ellipse ring for
    the circle layout, border walk for rect."""
    h, w = shape
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    ry, rx = (h - 1) / 2.0, (w - 1) / 2.0
    if layout == "circle":
        return [(cy + ry * math.sin(math.pi + 2.0 * math.pi * i / m),
                 cx + rx * math.cos(math.pi + 2.0 * math.pi * i / m)) for i in range(m)]
    # rect border walk, clockwise from the top-left corner
    pts = []
    total = 2 * (w - 1) + 2 * (h - 1)
    for i in range(m):
        d = total * i / m
        if d < w - 1:
            pts.append((0.0, d))
        elif d < w - 1 + h - 1:
            pts.append((d - (w - 1), w - 1.0))
        elif d < 2 * (w - 1) + h - 1:
            pts.append((h - 1.0, w - 1 - (d - (w - 1) - (h - 1))))
        else:
            pts.append((h - 1 - (d - 2 * (w - 1) - (h - 1)), 0.0))
    return pts


def _disc_score(mag_rows, cy, cx, radius, h, w):
    total = 0.0
    r0 = max(0, int(cy - radius))
    r1 = min(h - 1, int(cy + radius) + 1)
    c0 = max(0, int(cx - radius))
    c1 = min(w - 1, int(cx + radius) + 1)
    r2 = radius * radius
    for r in range(r0, r1 + 1):
        row = mag_rows[r]
        for c in range(c0, c1 + 1):
            if (r - cy) * (r - cy) + (c - cx) * (c - cx) <= r2:
                total += row[c]
    return total


def adaptive_perimeter_nails(shape, count, gradient, layout, pool_factor=4):
    """Adaptive perimeter nail list: score `pool_factor * count` evenly spaced
    perimeter candidates by the mean gradient magnitude within a 40 px disc,
    then greedily select `count` with a minimum gap of one candidate slot."""
    h, w = shape
    mag = _core.gradient_magnitude(gradient)
    mag_rows = mag.tolist()
    m = min(pool_factor * count, 4 * count)
    candidates = perimeter_candidates(shape, m, layout)
    scores = [_disc_score(mag_rows, p[0], p[1], SCORE_RADIUS_PX, h, w) for p in candidates]
    order = sorted(range(m), key=lambda i: scores[i], reverse=True)

    gap = 1.0 / m  # one candidate slot, normalized perimeter units
    chosen = []
    taken_positions = []
    seen_pixels = set()
    for i in order:
        pos = i / m
        if any(min(abs(pos - t), 1.0 - abs(pos - t)) < gap for t in taken_positions):
            continue
        nail = (int(round(candidates[i][0])), int(round(candidates[i][1])))
        if nail in seen_pixels:
            continue  # rounding collapsed two slots onto one pixel
        seen_pixels.add(nail)
        taken_positions.append(pos)
        chosen.append(nail)
        if len(chosen) == count:
            break
    if len(chosen) < count:
        raise ValueError(f"adaptive selection found only {len(chosen)} of {count} nails")
    return chosen


def uniform_perimeter_nails(shape, count, layout):
    """Uniform perimeter reference list at exactly `count` nails."""
    h, w = shape
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    ry, rx = (h - 1) / 2.0, (w - 1) / 2.0
    if layout == "circle":
        return [(int(round(cy + ry * math.sin(math.pi + 2.0 * math.pi * i / count))),
                 int(round(cx + rx * math.cos(math.pi + 2.0 * math.pi * i / count))))
                for i in range(count)]
    pts = perimeter_candidates(shape, count, "rect")
    return [(int(round(y)), int(round(x))) for y, x in pts]
