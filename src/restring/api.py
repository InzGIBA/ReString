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

from restring import _core, auto_palette, layouts, palettes
from restring.generator import (
    Config,
    _continue_bw,
    _run_bw,
    _run_palette,
    continue_palette,
    resolve_export_strength,
)
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
    palette: str | Path = "bw"         # bw | wb | rgb | cmy | cmyk | auto:K[:chart] | JSON file
    max_threads: int = 8               # palette cap, lift for long floss runs
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
    random_nails: int | None = None    # scan a fixed seeded subset of k candidates
    seed: int | None = None            # subset seed, core default 42
    crop: tuple | None = None          # (x0, y0, x1, y1) fractions of the source, 0..1
    contrast: float = 1.0              # around mid-gray, > 1 hardens
    gamma: float = 1.0                 # power on 0..1, < 1 brightens
    invert: bool = False               # negative of the photo
    weight_map: str | Path | None = None  # grayscale PNG of per-pixel search weights


@dataclass(slots=True)
class Result:
    """Everything a finished run produced. `palette` carries the resolved
    thread colors for color runs (None for bw/wb), including auto palettes."""

    image: _core.Image
    pull_orders: list[list[int]]
    nails: list[tuple[int, int]]
    options: GenerateOptions
    stats: Stats
    palette: list | None = None


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


def _resolve_threads(palette_spec, img=None, max_threads=None):
    """Resolve the palette spec: (None, wb) for bw/wb, a thread list for the
    rest. `auto:K[:chart]` needs the preprocessed working image."""
    if max_threads is None:
        max_threads = palettes.MAX_THREADS
    lowered = str(palette_spec).lower()
    if lowered == "bw":
        return None, False
    if lowered == "wb":
        return None, True
    if lowered.startswith("auto:"):
        if img is None:
            raise ValueError("auto palette needs the source image")
        threads = auto_palette.suggest_from_spec(img, palette_spec)
    else:
        threads = palettes.resolve_palette(palette_spec, max_threads=max_threads)
    if len(threads) > max_threads:
        raise ValueError(f"palette with {len(threads)} threads exceeds the cap of {max_threads}")
    return threads, False


def _crop_fractions(img, crop):
    """Crop by (x0, y0, x1, y1) fractions of the source, validated 0..1."""
    if len(crop) != 4 or not all(0.0 <= float(v) <= 1.0 for v in crop):
        raise ValueError(f"crop must be four fractions in 0..1, got {crop!r}")
    x0, y0, x1, y1 = (float(v) for v in crop)
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"crop needs x1 > x0 and y1 > y0, got {crop!r}")
    h, w = img.shape()[:2]
    return img.crop(int(round(x0 * w)), int(round(y0 * h)),
                    int(round(x1 * w)), int(round(y1 * h)))


def _prepare(img, *, crop, contrast, gamma, invert, grid, aspect):
    """The shared image pipeline: user crop, aspect crop, resample, adjust."""
    if contrast <= 0 or gamma <= 0:
        raise ValueError("contrast and gamma must be > 0")
    if crop is not None:
        img = _crop_fractions(img, crop)
    if aspect != 1.0:
        img = largest_rect(img, aspect)
        img = resize(img, (grid, int(round(grid * aspect))))
    else:
        img = resize(largest_square(img), (grid, grid))
    if contrast != 1.0 or gamma != 1.0 or invert:
        img = img.adjust(contrast, gamma, invert)
    return img


def generate(source, options: GenerateOptions | None = None) -> Result:
    """Run the full pipeline: load, crop/resample, nails, greedy search,
    render. Returns a Result with the image, the pull orders and stats."""
    options = options or GenerateOptions()
    started = time.perf_counter()

    img = _load(source)
    builder, _label, aspect = parse_layout_spec(options.layout)
    img = _prepare(img, crop=options.crop, contrast=options.contrast, gamma=options.gamma,
                   invert=options.invert, grid=options.grid, aspect=aspect)

    h, w = img.shape()[:2]
    shape = (h, w)
    nails = builder(shape, options.nail_step)

    threads, wb = _resolve_threads(options.palette, img, options.max_threads)

    config = Config(
        radius1_multiplier=options.radius1_multiplier,
        radius2_multiplier=options.radius2_multiplier,
        side_len=options.export_size,
        export_strength=options.strength,
        pull_amount=options.pulls,
        random_nails=options.random_nails,
        seed=options.seed,
        wb=wb,
        weight_peak=options.weight,
        min_chord=options.min_chord,
        realistic=options.realistic,
        canvas_size=options.canvas_size,
        thread_width=options.thread_width,
        rollback=options.rollback,
        weight_map=str(options.weight_map) if options.weight_map is not None else None,
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
                  options=resolved, stats=stats, palette=threads)


def continue_project(source, project, extra_pulls: int, *, strength=None, export_size=300) -> Result:
    """Continue a saved project with more pulls on the same uncut thread.

    `source` is the original photo (the project stores only its digest).
    Every thread replays its stored order and resumes from its last nail;
    `extra_pulls` is the per-thread budget for the new tail. The returned
    orders are the stored orders plus the new pulls, prefix unchanged.
    """
    if extra_pulls < 1:
        raise ValueError("extra_pulls must be >= 1")
    started = time.perf_counter()

    img = _load(source)
    layout_spec = project.config.get("layout", "rect")
    _builder, _label, aspect = parse_layout_spec(layout_spec)
    grid = project.config.get("grid", 300)
    gh, gw = (grid, grid) if isinstance(grid, int) else (int(grid[0]), int(grid[1]))
    crop = project.config.get("crop")
    img = _prepare(img, crop=tuple(crop) if crop else None,
                   contrast=project.config.get("contrast", 1.0),
                   gamma=project.config.get("gamma", 1.0),
                   invert=bool(project.config.get("invert", False)),
                   grid=gh, aspect=aspect)
    if img.shape()[:2] != (gh, gw):
        img = resize(img, (gh, gw))
    shape = (gh, gw)
    nails = project.nails
    wb = bool(project.config.get("wb", False))

    config = Config(
        side_len=export_size,
        export_strength=strength,
        pull_amount=extra_pulls,
        random_nails=project.config.get("random_nails"),
        seed=project.config.get("seed"),
        wb=wb,
        weight_peak=project.config.get("weight"),
        min_chord=project.config.get("min_chord"),
        weight_map=project.config.get("weight_map"),
    )

    if project.mode == "bw":
        result, order = _continue_bw(img, shape, nails, config, project.pull_orders[0])
        orders = [order]
        palette_spec = "wb" if wb else "bw"
    else:
        threads = project.palette if project.mode == "palette" else palettes.builtin_palette("rgb")
        result, orders = continue_palette(img, shape, nails, config, threads, project.pull_orders)
        palette_spec = "rgb"
        if project.mode == "palette":
            palette_spec = next(
                (name for name in ("rgb", "cmy", "cmyk")
                 if [t.rgb for t in palettes.builtin_palette(name)] == [t.rgb for t in threads]),
                "custom")

    stats = Stats(
        pulls_per_thread=[len(order) - 1 for order in orders],
        nails=len(nails),
        elapsed_s=round(time.perf_counter() - started, 2),
    )
    options = GenerateOptions(
        layout=layout_spec,
        nail_step=project.config.get("nail_step", 4),
        pulls=extra_pulls,
        strength=strength,
        palette=palette_spec,
        grid=max(gh, gw),
        export_size=export_size,
        weight=project.config.get("weight"),
        min_chord=project.config.get("min_chord"),
        random_nails=project.config.get("random_nails"),
        seed=project.config.get("seed"),
    )
    return Result(image=result, pull_orders=orders,
                  nails=[(int(n[0]), int(n[1])) for n in nails],
                  options=options, stats=stats,
                  palette=None if project.mode == "bw" else threads)


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
