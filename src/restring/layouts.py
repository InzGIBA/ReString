"""Custom nail layouts: polygon, star, multi-ring, SVG outline, explicit list.

Every builder returns list[(row, col)] in working-grid pixels: deduplicated,
inside the grid, and — except rings, which keep ring-by-ring order — sorted
clockwise from the centroid's 9 o'clock, matching the circle layout
convention. The core treats nail lists as opaque points, so any geometry
searches and renders without core changes.
"""

import logging
import math
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

SVG_CIRCLE_SEGMENTS = 64  # approximation granularity for <circle> outlines


class LayoutError(ValueError):
    """Raised for malformed layout specs, files or nail sets."""


def _validate(nails, shape):
    h, w = shape
    out, seen, duplicates = [], set(), 0
    for nail in nails:
        r, c = int(round(float(nail[0]))), int(round(float(nail[1])))
        if not (0 <= r < h and 0 <= c < w):
            raise LayoutError(f"nail ({r}, {c}) falls outside the {w} x {h} grid")
        if (r, c) in seen:
            duplicates += 1
            continue
        seen.add((r, c))
        out.append((r, c))
    if duplicates:
        logger.warning(f"layout: removed {duplicates} duplicate nail(s)")
    if len(out) < 3:
        raise LayoutError(f"a layout needs at least 3 distinct nails, got {len(out)}")
    return out


def _clockwise_from_9(points):
    """Sort points clockwise (image coordinates, y grows downward) starting
    at the 9 o'clock position relative to the centroid."""
    cy = sum(p[0] for p in points) / len(points)
    cx = sum(p[1] for p in points) / len(points)

    def key(p):
        angle = math.atan2(p[0] - cy, p[1] - cx)  # 0 at 3 o'clock, growing clockwise
        key = (angle - math.pi) % (2.0 * math.pi)  # rotate the start to 9 o'clock
        if key > 2.0 * math.pi - 1e-9:
            key = 0.0  # snap points sitting exactly on the 9 o'clock seam
        return key

    return sorted(points, key=key)


def _centered(shape):
    h, w = shape
    return (h - 1) / 2.0, (w - 1) / 2.0


def _perimeter_points(vertices, count):
    """Distribute count points at equal arc length along the closed polyline
    through vertices (clockwise by construction of the vertex angles)."""
    edges = []
    total = 0.0
    for k in range(len(vertices)):
        (y1, x1), (y2, x2) = vertices[k], vertices[(k + 1) % len(vertices)]
        d = math.hypot(y2 - y1, x2 - x1)
        edges.append(d)
        total += d
    points = []
    acc = 0.0
    edge = 0
    for i in range(count):
        target = i * total / count
        while edge < len(edges) - 1 and acc + edges[edge] < target:
            acc += edges[edge]
            edge += 1
        (y1, x1), (y2, x2) = vertices[edge], vertices[(edge + 1) % len(vertices)]
        frac = (target - acc) / edges[edge] if edges[edge] > 0 else 0.0
        points.append((y1 + (y2 - y1) * frac, x1 + (x2 - x1) * frac))
    return points


def polygon(shape, sides, count):
    """Regular n-gon perimeter fitted to the working shape, `count` nails at
    equal arc length along the outline."""
    if sides < 3:
        raise LayoutError("polygon needs sides >= 3")
    if count < 3:
        raise LayoutError("polygon needs count >= 3")
    cy, cx = _centered(shape)
    verts = []
    for k in range(sides):
        ang = math.pi + 2.0 * math.pi * k / sides  # from 9 o'clock, clockwise
        verts.append((cy + cy * math.sin(ang), cx + cx * math.cos(ang)))
    return _clockwise_from_9(_validate(_perimeter_points(verts, count), shape))


def star(shape, points, inner_radius, count):
    """Star outline: `points` spikes alternating between the outer radius and
    `inner_radius` * outer, `count` nails at equal arc length."""
    if points < 3:
        raise LayoutError("star needs points >= 3")
    if not 0.0 < inner_radius < 1.0:
        raise LayoutError(f"inner_radius must sit in (0, 1), got {inner_radius}")
    if count < 3:
        raise LayoutError("star needs count >= 3")
    cy, cx = _centered(shape)
    verts = []
    for k in range(2 * points):
        ang = math.pi + math.pi * k / points  # outer, inner, outer, ...
        radius = cy if k % 2 == 0 else cy * inner_radius
        radius_x = cx if k % 2 == 0 else cx * inner_radius
        verts.append((cy + radius * math.sin(ang), cx + radius_x * math.cos(ang)))
    return _clockwise_from_9(_validate(_perimeter_points(verts, count), shape))


def rings(shape, specs):
    """Concentric rings from (radius_fraction, count) pairs, concatenated
    ring by ring, each ring clockwise. Pulls between rings are ordinary
    long chords — no core change needed."""
    points = []
    for radius_fraction, count in specs:
        if not 0.0 < radius_fraction <= 1.0:
            raise LayoutError(f"ring radius_fraction must sit in (0, 1], got {radius_fraction}")
        if count < 3:
            raise LayoutError(f"ring needs count >= 3, got {count}")
        cy, cx = _centered(shape)
        for i in range(count):
            ang = math.pi + 2.0 * math.pi * i / count
            points.append((cy + cy * radius_fraction * math.sin(ang),
                           cx + cx * radius_fraction * math.cos(ang)))
    return _validate(points, shape)


def _svg_polyline_points(tag, element):
    """Outline points (svg coordinates) of one supported SVG element."""
    if tag in ("polygon", "polyline"):
        raw = (element.get("points") or "").replace(",", " ").split()
        coords = [float(v) for v in raw]
        if len(coords) < 4 or len(coords) % 2:
            raise LayoutError(f"<{tag}> needs pairs of coordinates")
        return list(zip(coords[1::2], coords[0::2]))  # (y, x)
    if tag == "rect":
        x, y = float(element.get("x", 0)), float(element.get("y", 0))
        w, h = float(element.get("width", 0)), float(element.get("height", 0))
        return [(y, x), (y, x + w), (y + h, x + w), (y + h, x)]
    if tag == "circle":
        cy, cx = float(element.get("cy", 0)), float(element.get("cx", 0))
        r = float(element.get("r", 0))
        return [(cy + r * math.sin(2 * math.pi * i / SVG_CIRCLE_SEGMENTS),
                 cx + r * math.cos(2 * math.pi * i / SVG_CIRCLE_SEGMENTS))
                for i in range(SVG_CIRCLE_SEGMENTS)]
    return None


def _svg_path_points(d):
    """Points of a path whose d attribute uses only M/L/Z (upper or lower
    case). Curves raise with the offending command."""
    tokens = d.replace(",", " ").split()
    points = []
    current = (0.0, 0.0)
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in ("M", "m", "L", "l"):
            if i + 2 >= len(tokens):
                raise LayoutError(f"path command {token} is missing coordinates")
            dx, dy = float(tokens[i + 1]), float(tokens[i + 2])
            if token.islower():
                dx, dy = current[1] + dx, current[0] + dy
            current = (dy, dx)  # (y, x)
            points.append(current)
            i += 3
        elif token in ("Z", "z"):
            if points:
                points.append(points[0])  # close back to the subpath start
            i += 1
        else:
            raise LayoutError(f"unsupported path command {token!r} (documented "
                              "limitation: M/L/Z only; curves are not supported)")
    return points


def from_svg(path, shape, count):
    """Sample `count` points at equal arc length along the combined outline
    of an SVG file. Supported elements: polygon, polyline, rect, circle and
    path restricted to M/L/Z (curves unsupported, documented limitation)."""
    if count < 3:
        raise LayoutError(f"svg layout needs count >= 3, got {count}")
    root = ET.parse(path).getroot()
    vw = float(root.get("viewBox", "0 0 1 1").split()[2]) if root.get("viewBox") else None
    vh = float(root.get("viewBox", "0 0 1 1").split()[3]) if root.get("viewBox") else None
    if vw is None:
        vw, vh = 1.0, 1.0
        if root.get("width") and root.get("height"):
            vw = float(str(root.get("width")).removesuffix("px").removesuffix("mm"))
            vh = float(str(root.get("height")).removesuffix("px").removesuffix("mm"))
    if vw <= 0 or vh <= 0:
        raise LayoutError(f"{path}: cannot determine the SVG size (viewBox or width/height)")

    outline = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "path":
            outline.extend(_svg_path_points(element.get("d", "")))
        else:
            pts = _svg_polyline_points(tag, element)
            if pts is not None:
                outline.extend(pts)
    if len(outline) < 3:
        raise LayoutError(f"{path}: no supported outline elements found")

    # scale to fit inside the working grid, centered, aspect preserved
    h, w = shape
    scale = min((h - 1) / vh, (w - 1) / vw)
    off_y = ((h - 1) - vh * scale) / 2
    off_x = ((w - 1) - vw * scale) / 2
    points = [(y * scale + off_y, x * scale + off_x) for y, x in outline]

    # resample at equal arc length along the combined outline
    sampled = _perimeter_points(points, count)
    return _clockwise_from_9(_validate(sampled, shape))


def explicit(nails, shape):
    """Pass-through for generated layouts, with bounds validation."""
    return _validate([(n[0], n[1]) for n in nails], shape)
