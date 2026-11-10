"""Public API: one call in, a typed result out.

`generate(source, options)` runs the full pipeline the CLI runs — load,
crop/resample, nails, search, render — and returns a `Result` with the
image, the pull orders and the statistics. Internal modules (`generator`,
`cli`) stay importable but are not the documented contract; see docs/api.md.
"""

import hashlib
import logging
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path

from restring import _core, layouts, palettes
from restring.generator import Config, _run_bw, _run_palette, resolve_export_strength
from restring.image_transformations import largest_rect, largest_square, resize
from restring.nails import create_circle_nail_positions, create_rectangle_nail_positions

logger = logging.getLogger(__name__)

Layout = str
"""Layout spec: circle | rect | polygon:sides[:count] | star:points:inner[:count]
| rings:r:count,r:count | svg:file.svg[:count], optional @aspect suffix."""


@dataclass(slots=True)
class Stats:
    """Run statistics."""

    pulls_per_thread: list[int]
    nails: int
    elapsed_s: float


@dataclass(slots=True)
class GenerateOptions:
    """Everything the search and render need. Defaults match the CLI's
    balanced preset."""

    layout: Layout = "rect"
    nail_step: int = 4
    pulls: int | None = None           # None = run to exhaustion
    strength: float | None = None      # None = auto (docs/tuning.md rule)
    palette: str | Path = "bw"         # bw | wb | rgb | cmy | cmyk | JSON file
    grid: int = 300
    export_size: int = 300
    weight: float | None = None
    min_chord: float | None = None
    rollback: bool = False
    realistic: bool = False
    canvas_size: float = 400
    thread_width: float = 0.2
    radius1_multiplier: float = 1      # export height multiplier
    radius2_multiplier: float = 1      # export width multiplier


@dataclass(slots=True)
class Result:
    """Everything a finished run produced."""

    image: _core.Image
    pull_orders: list[list[int]]
    nails: list[tuple[int, int]]
    options: GenerateOptions
    stats: Stats


def parse_layout_spec(spec: str) -> tuple:
    """Parse a layout spec into (builder(shape, nail_step) -> nails, label,
    aspect). Raises ValueError on malformed specs."""
    aspect = 1.0
    text = spec
    if "@" in text:
        text, aspect_text = text.rsplit("@", 1)
        try:
            aspect = float(aspect_text)
        except ValueError:
            raise ValueError(f"layout aspect must be a number, got {aspect_text!r}") from None
        if not 0.1 <= aspect <= 10.0:
            raise ValueError(f"layout aspect must sit in 0.1..10, got {aspect}")

    parts = text.split(":")
    name = parts[0]
    default_count = 300
    if name not in ("circle", "rect", "polygon", "star", "rings", "svg"):
        raise ValueError(f"unknown layout {name!r}; see docs/layouts.md")
    def as_int(value_text, what, minimum):
        try:
            value = int(value_text)
        except ValueError:
            raise ValueError(f"layout {what} must be an int, got {value_text!r}") from None
        if value < minimum:
            raise ValueError(f"layout {what} must be >= {minimum}, got {value}")
        return value

    def as_float(value_text, what):
        try:
            return float(value_text)
        except ValueError:
            raise ValueError(f"layout {what} must be a number, got {value_text!r}") from None

    if name == "star" and len(parts) < 3:
        raise ValueError("layout star needs star:points:inner[:count]")

    def builder(shape, nail_step):
        if name in ("circle", "rect"):
            if name == "rect":
                return create_rectangle_nail_positions(shape, nail_step)
            return create_circle_nail_positions(shape, nail_step)
        if name == "polygon":
            sides = as_int(parts[1], "polygon sides", 3) if len(parts) > 1 else 5
            count = as_int(parts[2], "polygon count", 3) if len(parts) > 2 else default_count
            return layouts.polygon(shape, sides, count)
        if name == "star":
            if len(parts) < 3:
                raise ValueError("layout star needs star:points:inner[:count]")
            spikes = as_int(parts[1], "star points", 3)
            inner = as_float(parts[2], "star inner radius")
            count = as_int(parts[3], "star count", 3) if len(parts) > 3 else default_count
            return layouts.star(shape, spikes, inner, count)
        if name == "rings":
            values = ":".join(parts[1:]).replace(",", ":").split(":")
            if len(values) < 2 or len(values) % 2:
                raise ValueError("layout rings needs rings:r:count,r:count")
            specs = []
            for i in range(0, len(values), 2):
                specs.append((as_float(values[i], "ring radius"),
                              as_int(values[i + 1], "ring count", 3)))
            return layouts.rings(shape, specs)
        if name == "svg":
            if len(parts) < 2:
                raise ValueError("layout svg needs svg:file.svg[:count]")
            path = ":".join(parts[1:-1]) if len(parts) > 2 else parts[1]
            count = as_int(parts[-1], "svg count", 3) if len(parts) > 2 else default_count
            return layouts.from_svg(path, shape, count)
        raise ValueError(f"unknown layout {name!r}; see docs/layouts.md")

    label = text
    return builder, label, aspect


def _load(source):
    """Path, bytes (PNG/JPEG, decoded through a temp file) or an Image."""
    if isinstance(source, _core.Image):
        return source
    if isinstance(source, bytes):
        suffix = ".png" if source[:8].startswith(b"\x89PNG") else ".jpg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(source)
            temp_path = handle.name
        try:
            return _core.Image.load(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)
    return _core.Image.load(str(source))


def _resolve_threads(palette_spec):
    """Resolve the palette spec: (None, wb) for bw/wb, a thread list for the
    rest."""
    lowered = str(palette_spec).lower()
    if lowered == "bw":
        return None, False
    if lowered == "wb":
        return None, True
    threads = palettes.resolve_palette(palette_spec)
    if len(threads) > palettes.MAX_THREADS:
        raise ValueError(f"palette with {len(threads)} threads exceeds the cap of {palettes.MAX_THREADS}")
    return threads, False


def generate(source, options: GenerateOptions | None = None) -> Result:
    """Run the full pipeline: load, crop/resample, nails, greedy search,
    render. Returns a Result with the image, the pull orders and stats."""
    options = options or GenerateOptions()
    started = time.perf_counter()

    img = _load(source)
    builder, _label, aspect = parse_layout_spec(options.layout)

    if aspect != 1.0:
        img = largest_rect(img, aspect)
        img = resize(img, (options.grid, int(round(options.grid * aspect))))
    else:
        img = resize(largest_square(img), (options.grid, options.grid))

    h, w = img.shape()[:2]
    shape = (h, w)
    nails = builder(shape, options.nail_step)

    threads, wb = _resolve_threads(options.palette)

    config = Config(
        radius1_multiplier=options.radius1_multiplier,
        radius2_multiplier=options.radius2_multiplier,
        side_len=options.export_size,
        export_strength=options.strength,
        pull_amount=options.pulls,
        random_nails=None,
        wb=wb,
        weight_peak=options.weight,
        min_chord=options.min_chord,
        realistic=options.realistic,
        canvas_size=options.canvas_size,
        thread_width=options.thread_width,
        rollback=options.rollback,
    )

    if threads is None:
        result, order = _run_bw(img, shape, nails, config)
        orders = [order]
    else:
        result, orders = _run_palette(img, shape, nails, config, threads)

    stats = Stats(
        pulls_per_thread=[len(order) - 1 for order in orders],
        nails=len(nails),
        elapsed_s=round(time.perf_counter() - started, 2),
    )
    resolved = replace(options)
    return Result(image=result, pull_orders=orders,
                  nails=[(int(n[0]), int(n[1])) for n in nails],
                  options=resolved, stats=stats)


def export_strength(pull_count: int) -> float:
    """The fitted export strength for a pull count (the auto rule)."""
    return resolve_export_strength(pull_count)


def project_digest(source_path: str | Path) -> str:
    """SHA-256 digest of an input file, for project provenance fields."""
    digest = hashlib.sha256()
    with Path(source_path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
