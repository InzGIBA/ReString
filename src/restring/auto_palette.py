"""Palette suggestions from the photo itself: k-means over the pixels,
optionally snapped to a floss chart (the bundled DMC starter or any palette
JSON). Pure Python and seeded, so a suggestion reproduces exactly.

The spec grammar is `auto:K[:chart]`: K threads, chart is `dmc` for the
bundled starter chart or a path to a palette JSON file.
"""

import random
from pathlib import Path

from restring import palettes
from restring.palettes import ThreadColor

DMC_CHART = Path(__file__).parent / "data" / "dmc.json"
SAMPLE_SIDE = 64      # clustering sample: enough color coverage, fast in pure Python
MAX_ITERATIONS = 30


def parse_spec(spec):
    """auto:K[:chart] -> (k, chart_path_or_None). Raises ValueError."""
    parts = str(spec).split(":")
    if len(parts) < 2 or len(parts) > 3:
        raise ValueError(f"auto palette needs auto:K[:chart], got {spec!r}")
    try:
        k = int(parts[1])
    except ValueError:
        raise ValueError(f"auto palette thread count must be an int, got {parts[1]!r}") from None
    if k < 1:
        raise ValueError(f"auto palette needs at least 1 thread, got {k}")
    chart = None
    if len(parts) == 3:
        chart = DMC_CHART if parts[2].lower() == "dmc" else Path(parts[2])
        if not chart.is_file():
            raise ValueError(f"auto palette chart not found: {parts[2]}")
    return k, chart


def _dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def kmeans_colors(img, k, seed=42):
    """K-means centroids of the image colors, k-means++ init, Lloyd rounds.
    The image is sampled down to 64x64 first; the result is deterministic."""
    h, w = img.shape()[:2]
    small = img.resize(SAMPLE_SIDE, SAMPLE_SIDE) if max(h, w) > SAMPLE_SIDE else img
    pixels = [tuple(px) for row in small.tolist() for px in row]
    rng = random.Random(seed)

    centers = [pixels[rng.randrange(len(pixels))]]
    for _ in range(1, k):
        weights = [min(_dist2(p, c) for c in centers) for p in pixels]
        total = sum(weights)
        if total <= 0.0:
            centers.append(pixels[rng.randrange(len(pixels))])
            continue
        pick = rng.random() * total
        acc = 0.0
        for p, weight in zip(pixels, weights):
            acc += weight
            if acc >= pick:
                centers.append(p)
                break

    for _ in range(MAX_ITERATIONS):
        clusters = [[] for _ in centers]
        for p in pixels:
            best = min(range(k), key=lambda i: _dist2(p, centers[i]))
            clusters[best].append(p)
        updated = [
            tuple(sum(c) / len(cluster) for c in zip(*cluster)) if cluster else centers[i]
            for i, cluster in enumerate(clusters)
        ]
        shift = max(_dist2(old, new) for old, new in zip(centers, updated))
        centers = updated
        if shift < 1e-6:
            break
    return centers


def snap_to_chart(threads, chart):
    """Nearest chart color per thread, duplicates dropped: two threads of
    the same floss color buy nothing."""
    snapped = []
    seen = set()
    for thread in threads:
        best = min(chart, key=lambda c: _dist2(thread.rgb, c.rgb))
        if best.name in seen:
            continue
        seen.add(best.name)
        snapped.append(ThreadColor(best.name, best.rgb))
    return snapped


def suggest_palette(img, k, *, chart=None, seed=42):
    """K ThreadColors from the photo; with a chart (a ThreadColor list) the
    colors snap to the nearest chart entries."""
    centers = kmeans_colors(img, k, seed)
    threads = [ThreadColor(f"auto {i + 1}", tuple(round(c, 4) for c in center))
               for i, center in enumerate(centers)]
    if chart is not None:
        threads = snap_to_chart(threads, chart)
    return threads


def suggest_from_spec(img, spec, *, seed=42):
    """Resolve an auto:K[:chart] spec against the image."""
    k, chart_path = parse_spec(spec)
    chart = palettes.load_palette(chart_path, max_threads=None) if chart_path else None
    return suggest_palette(img, k, chart=chart, seed=seed)