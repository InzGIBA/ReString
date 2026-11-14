"""Serialization for `.restring` project files (schema versions 1 and 2).

A project stores the nail layout and the pull orders, so any tool can
re-render a result without re-running the search. Plain JSON: stdlib only,
the runtime package stays dependency-free. Version 2 adds the "palette"
mode with stored thread colors. The schema and the compatibility promise
live in docs/project-format.md.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from restring.palettes import ThreadColor

FORMAT_NAME = "restring-project"
FORMAT_VERSION = 2
SUPPORTED_VERSIONS = (1, 2)


class ProjectError(ValueError):
    """Raised for malformed or unsupported project files."""


@dataclass
class Project:
    """A loaded project file.

    mode is "bw" (one pull order), "rgb" (three per-channel orders, padding
    kept as part of the interleaving contract with render_rgb) or "palette"
    (K orders with stored thread colors, version 2). nails are (row, col)
    pairs in working-grid pixels. config carries the search-time settings;
    render-only fields (-s, -d) stay outside and are chosen fresh at
    re-render time.
    """

    mode: str
    config: dict
    nails: list
    pull_orders: list
    input_digest: str
    created: str = ""
    version: int = FORMAT_VERSION
    restring_version: str = ""
    palette: list | None = None


def save(path, *, mode, config, nails, pull_orders, input_digest, palette=None):
    """Write a project file and return the equivalent Project object.

    `palette` is a list of ThreadColor, required for mode "palette" and
    rejected for the other modes (bw and rgb carry implicit colors).
    """
    import restring

    if mode == "palette":
        if not palette:
            raise ProjectError("mode 'palette' needs a palette of thread colors")
        if len(palette) != len(pull_orders):
            raise ProjectError("palette needs one thread color per pull order")
    elif palette is not None:
        raise ProjectError(f"mode {mode!r} carries implicit colors, pass palette only for 'palette'")

    data = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "mode": mode,
        "config": dict(config),
        "nails": [[int(r), int(c)] for r, c in nails],
        "pull_orders": [[int(i) for i in order] for order in pull_orders],
        "input_digest": input_digest,
        "restring_version": restring.__version__,
    }
    if mode == "palette":
        data["palette"] = [{"name": t.name, "rgb": [float(v) for v in t.rgb]} for t in palette]
    Path(path).write_text(json.dumps(data))
    return Project(
        mode=mode,
        config=dict(config),
        nails=[(int(n[0]), int(n[1])) for n in data["nails"]],
        pull_orders=[list(order) for order in data["pull_orders"]],
        input_digest=input_digest,
        created=data["created"],
        version=FORMAT_VERSION,
        restring_version=data["restring_version"],
        palette=list(palette) if palette is not None else None,
    )


def _load_palette(entries, order_count):
    if not isinstance(entries, list) or len(entries) != order_count:
        raise ProjectError(f"palette mode needs one color per pull order ({order_count})")
    threads = []
    for entry in entries:
        if not isinstance(entry, dict) or "rgb" not in entry:
            raise ProjectError(f"palette entries must be objects with 'rgb', got {entry!r}")
        rgb = entry["rgb"]
        if (not isinstance(rgb, list) or len(rgb) != 3
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in rgb)):
            raise ProjectError(f"palette 'rgb' must be [r, g, b] floats, got {rgb!r}")
        if not all(0.0 <= float(v) <= 1.0 for v in rgb):
            raise ProjectError(f"palette 'rgb' values must sit in 0..1, got {rgb!r}")
        threads.append(ThreadColor(str(entry.get("name", "thread")), tuple(float(v) for v in rgb)))
    return threads


def load(path):
    """Read and validate a project file. Raises ProjectError on any problem."""
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ProjectError("project file must be a JSON object")
    if data.get("format") != FORMAT_NAME:
        raise ProjectError(f"not a restring project: format {data.get('format')!r}")
    version = data.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise ProjectError(f"unsupported project format version {version!r}, "
                           f"expected one of {SUPPORTED_VERSIONS}")

    mode = data.get("mode")
    modes = ("bw", "rgb") if version == 1 else ("bw", "rgb", "palette")
    if mode not in modes:
        raise ProjectError(f"mode must be one of {modes}, got {mode!r}")

    orders = data.get("pull_orders")
    if mode == "palette":
        if not isinstance(orders, list) or not orders:
            raise ProjectError("palette mode needs a non-empty list of pull orders")
        expected = len(orders)
    else:
        expected = 1 if mode == "bw" else 3
        if not isinstance(orders, list) or len(orders) != expected:
            raise ProjectError(f"mode {mode!r} needs {expected} pull order(s), got {orders!r}")

    nails = data.get("nails")
    if not isinstance(nails, list) or not nails or not all(
        isinstance(n, list) and len(n) == 2 for n in nails
    ):
        raise ProjectError("nails must be a non-empty list of [row, col] pairs")

    nail_count = len(nails)
    for order in orders:
        if not isinstance(order, list):
            raise ProjectError("pull orders must be lists of nail indices")
        for index in order:
            if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < nail_count:
                raise ProjectError(f"nail index {index!r} out of range 0..{nail_count - 1}")

    config = data.get("config")
    if not isinstance(config, dict):
        raise ProjectError("missing config object")

    palette = _load_palette(data.get("palette"), len(orders)) if mode == "palette" else None

    return Project(
        mode=mode,
        config=config,
        nails=[(int(n[0]), int(n[1])) for n in nails],
        pull_orders=[list(order) for order in orders],
        input_digest=data.get("input_digest", ""),
        created=data.get("created", ""),
        version=version,
        restring_version=data.get("restring_version", ""),
        palette=palette,
    )
