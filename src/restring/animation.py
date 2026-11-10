"""Winding animation: GIF from a project, no search.

Frames come from the Rust core (raw or downsampled snapshotting), so the
frame assembly stays dependency-free; the GIF encoder lives in the image
crate behind the `gif` feature.
"""

import logging
from pathlib import Path

from restring import _core
from restring.generator import resolve_export_strength

logger = logging.getLogger(__name__)

FPS = 30
SIZE_LIMIT_BYTES = 25 * 1024 * 1024


def animate_project(project, out_path, *, export_strength=None, size=600, frames=180):
    """Write an animated GIF of the winding sequence to `out_path`."""
    grid = project.config.get("grid", 300)
    gh, gw = (grid, grid) if isinstance(grid, int) else (int(grid[0]), int(grid[1]))
    wb = bool(project.config.get("wb", False))
    white = not wb

    if project.mode == "bw":
        magnitude = export_strength
        if magnitude is None:
            magnitude = resolve_export_strength(len(project.pull_orders[0]) - 1)
        strength = magnitude if wb else -magnitude
        images = _core.animate_bw(project.pull_orders[0], project.nails, strength,
                                  gh, gw, size, size, white, frames)
    else:
        strengths = []
        for order in project.pull_orders:
            magnitude = export_strength
            if magnitude is None:
                magnitude = resolve_export_strength(len(order) - 1)
            strengths.append(magnitude if wb else -magnitude)
        images = _core.animate_rgb(project.pull_orders, project.nails, strengths,
                                   gh, gw, size, size, white, frames)

    _core.save_gif(str(out_path), images, FPS)
    file_bytes = Path(out_path).stat().st_size
    if file_bytes > SIZE_LIMIT_BYTES:
        logger.warning(f"Animation is {file_bytes / 1024 / 1024:.1f} MB, over the 25 MB "
                       f"target; halving fps to {FPS // 2} for playback. Re-render with "
                       f"-d 450 (or smaller) for a smaller file.")
        _core.save_gif(str(out_path), images, FPS // 2)
        file_bytes = Path(out_path).stat().st_size
    logger.info(f"Animation written: {out_path} ({len(images)} frames, "
                f"{file_bytes / 1024 / 1024:.1f} MB)")
