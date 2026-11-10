"""Thread palettes: named colors for the K-thread pipeline.

Palettes are data, not code: built-ins cover the compatibility RGB triple and
the subtractive CMY/CMYK sets, and JSON palette files load any custom set
(embroidery floss charts and the like). Additive-on-white rendering treats a
thread color as the channels it darkens, so subtractive primaries are plain
RGB triples: cyan is (0, 1, 1) because cyan ink absorbs red.
"""

import json
from dataclasses import dataclass
from pathlib import Path

MAX_THREADS = 8


class PaletteError(ValueError):
    """Raised for malformed palettes or palette files."""


@dataclass
class ThreadColor:
    name: str
    rgb: tuple  # (r, g, b), sRGB floats 0..1


def _builtin_threads():
    return {
        "rgb": [
            ThreadColor("red", (1.0, 0.0, 0.0)),
            ThreadColor("green", (0.0, 1.0, 0.0)),
            ThreadColor("blue", (0.0, 0.0, 1.0)),
        ],
        "cmy": [
            ThreadColor("cyan", (0.0, 1.0, 1.0)),
            ThreadColor("magenta", (1.0, 0.0, 1.0)),
            ThreadColor("yellow", (1.0, 1.0, 0.0)),
        ],
        "cmyk": [
            ThreadColor("cyan", (0.0, 1.0, 1.0)),
            ThreadColor("magenta", (1.0, 0.0, 1.0)),
            ThreadColor("yellow", (1.0, 1.0, 0.0)),
            ThreadColor("black", (1.0, 1.0, 1.0)),
        ],
    }


def builtin_palette(name):
    """Return a built-in palette by name (rgb, cmy, cmyk)."""
    try:
        return list(_builtin_threads()[name])
    except KeyError:
        known = ", ".join(sorted(_builtin_threads()))
        raise PaletteError(f"unknown palette {name!r}, built-ins: {known}") from None


def _parse_thread(entry, source):
    if not isinstance(entry, dict):
        raise PaletteError(f"{source}: palette entries must be objects, got {entry!r}")
    if "rgb" not in entry:
        if "comment" in entry:
            return None  # header/comment entry in a palette file
        raise PaletteError(f"{source}: palette entry missing 'rgb': {entry!r}")
    name = entry.get("name", "thread")
    rgb = entry["rgb"]
    if (not isinstance(rgb, list) or len(rgb) != 3
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in rgb)):
        raise PaletteError(f"{source}: 'rgb' must be [r, g, b] floats, got {rgb!r}")
    if not all(0.0 <= float(v) <= 1.0 for v in rgb):
        raise PaletteError(f"{source}: 'rgb' values must sit in 0..1, got {rgb!r}")
    return ThreadColor(str(name), tuple(float(v) for v in rgb))


def load_palette(path):
    """Load a palette JSON file: a list of {"name", "rgb": [r, g, b]} entries.
    Entries with a "comment" instead of "rgb" are skipped (file headers)."""
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list):
        raise PaletteError(f"palette file must be a JSON list, got {type(data).__name__}")
    threads = []
    for entry in data:
        thread = _parse_thread(entry, path)
        if thread is not None:
            threads.append(thread)
    if not threads:
        raise PaletteError(f"{path}: palette file carries no thread colors")
    if len(threads) > MAX_THREADS:
        raise PaletteError(f"{path}: {len(threads)} threads exceeds the cap of {MAX_THREADS}")
    return threads


def resolve_palette(spec):
    """A palette spec is a built-in name or a path to a JSON palette file."""
    if spec in _builtin_threads():
        return builtin_palette(spec)
    return load_palette(spec)
