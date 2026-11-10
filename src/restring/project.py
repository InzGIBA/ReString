"""Serialization for `.restring` project files (schema version 1).

A project stores the nail layout and the pull orders, so any tool can
re-render a result without re-running the search. Plain JSON: stdlib only,
the runtime package stays dependency-free. The schema and the compatibility
promise live in docs/project-format.md.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

FORMAT_NAME = "restring-project"
FORMAT_VERSION = 1


class ProjectError(ValueError):
    """Raised for malformed or unsupported project files."""


@dataclass
class Project:
    """A loaded project file.

    mode is "bw" (one pull order) or "rgb" (three per-channel orders, padding
    kept as part of the interleaving contract with render_rgb). nails are
    (row, col) pairs in working-grid pixels. config carries the search-time
    settings; render-only fields (-s, -d) stay outside and are chosen fresh
    at re-render time.
    """

    mode: str
    config: dict
    nails: list
    pull_orders: list
    input_digest: str
    created: str = ""
    version: int = FORMAT_VERSION
    restring_version: str = ""


def save(path, *, mode, config, nails, pull_orders, input_digest):
    """Write a project file. `restring_version` records the writing version."""
    import restring

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
    Path(path).write_text(json.dumps(data))


def load(path):
    """Read and validate a project file. Raises ProjectError on any problem."""
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ProjectError("project file must be a JSON object")
    if data.get("format") != FORMAT_NAME:
        raise ProjectError(f"not a restring project: format {data.get('format')!r}")
    version = data.get("version")
    if version != FORMAT_VERSION:
        raise ProjectError(f"unsupported project format version {version!r}, expected {FORMAT_VERSION}")

    mode = data.get("mode")
    if mode not in ("bw", "rgb"):
        raise ProjectError(f"mode must be 'bw' or 'rgb', got {mode!r}")

    orders = data.get("pull_orders")
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

    return Project(
        mode=mode,
        config=config,
        nails=[(int(n[0]), int(n[1])) for n in nails],
        pull_orders=[list(order) for order in orders],
        input_digest=data.get("input_digest", ""),
        created=data.get("created", ""),
        version=version,
        restring_version=data.get("restring_version", ""),
    )
