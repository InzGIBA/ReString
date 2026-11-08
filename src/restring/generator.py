import logging
from dataclasses import dataclass
from time import process_time

from restring.canvas import (
    init_canvas,
    line_aa,
    pull_order_to_array_bw,
    pull_order_to_array_rgb,
)

try:  # compiled Rust core (built automatically by uv/maturin when available)
    from restring import _core
except ImportError:  # pragma: no cover - numpy fallback path
    _core = None

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Generation parameters shared by the B/W and RGB pipelines."""

    side_len: int = 300
    export_strength: float = 0.1
    pull_amount: int | None = None
    random_nails: int | None = None
    radius1_multiplier: float = 1
    radius2_multiplier: float = 1
    wb: bool = False


def _random_subset_ids(nail_count, random_nails):
    # the original implementation re-seeded default_rng(42) on every iteration,
    # i.e. it always worked with the same subset — both backends share it
    # (numpy lives in the dev dependency group)
    import numpy as np

    return np.random.default_rng(42).choice(range(nail_count), size=random_nails, replace=False)


def create_art(nails, orig_pic, pic, strength, i_limit=None, random_nails=None, line_cache=None):
    """Greedy pull-order search on a grayscale target Image.

    `pic` is only used for its initial fill (white/black canvas). Returns
    (pull_order, final working canvas Image). Uses the Rust core; falls back
    to the vectorized numpy implementation when the extension is unavailable.
    """
    subset = None
    if random_nails is not None:
        subset = [int(i) for i in _random_subset_ids(len(nails), random_nails)]

    if _core is not None:
        order, final = _core.create_art(
            [(int(r), int(c)) for r, c in nails],
            orig_pic,
            float(strength),
            int(i_limit) if i_limit is not None else None,
            subset,
            pic.pixel(0, 0, 0) >= 0.5,
        )
        return [int(i) for i in order], final

    return _create_art_numpy(nails, orig_pic, pic, strength, i_limit, subset)


# --- numpy fallback (dev dependency; reference implementation for tests) ----

def build_line_cache(nails):
    """Precompute anti-aliased line pixels for every ordered nail pair.

    Returns one CSR-style record per source nail i:
        (rr, cc, val, starts, targets)
    where segment k covers the line i -> targets[k] over pixels
    rr[starts[k]:starts[k+1]] (the last segment runs to the end).
    """
    import numpy as np

    n = len(nails)
    caches = []
    total_pixels = 0
    for i in range(n):
        p0 = nails[i]
        rrs, ccs, vals, starts, targets = [], [], [], [0], []
        for j in range(n):
            if j == i:
                continue
            rr, cc, val = line_aa(p0[0], p0[1], nails[j][0], nails[j][1])
            rrs.append(rr)
            ccs.append(cc)
            vals.append(val)
            starts.append(starts[-1] + len(rr))
            targets.append(j)
        if rrs:
            rr = np.concatenate(rrs).astype(np.int32)
            cc = np.concatenate(ccs).astype(np.int32)
            val = np.concatenate(vals).astype(np.float32)
        else:
            rr = np.asarray([], dtype=np.int32)
            cc = np.asarray([], dtype=np.int32)
            val = np.asarray([], dtype=np.float32)
        total_pixels += len(rr)
        caches.append((rr, cc, val, np.asarray(starts[:-1], dtype=np.int64), np.asarray(targets)))
    logger.info(
        f"Line cache: {n * (n - 1)} lines, {total_pixels / 1e6:.1f}M pixels "
        f"(~{total_pixels * 12 / 1e6:.0f} MB)"
    )
    return caches


def _scan_from(cache, pic, orig_pic, strength, current_idx, subset_ids=None):
    """Vectorized candidate scan: cumsum segment sums, last-max tie-breaking."""
    import numpy as np

    rr, cc, val, starts, targets = cache
    bounds = np.append(starts, len(rr))

    if subset_ids is None:
        seg_positions = np.arange(len(targets))
    else:
        seg_positions = np.searchsorted(targets, np.asarray(subset_ids)[np.asarray(subset_ids) != current_idx])
    seg_starts = bounds[seg_positions]
    seg_ends = bounds[seg_positions + 1]

    cur_px = pic[rr, cc]
    new_px = np.clip(cur_px + strength * val, 0, 1)
    improvement_px = (cur_px - orig_pic[rr, cc]) ** 2 - (new_px - orig_pic[rr, cc]) ** 2
    cum = np.concatenate(([0.0], np.cumsum(improvement_px)))
    seg_improvement = cum[seg_ends] - cum[seg_starts]

    best = len(seg_improvement) - 1 - np.argmax(seg_improvement[::-1])
    return (int(targets[seg_positions[best]]),
            (int(seg_starts[best]), int(seg_ends[best])),
            float(seg_improvement[best]))


def _create_art_numpy(nails, orig_pic, pic, strength, i_limit, subset_ids):
    import numpy as np

    from restring import _core as core_mod

    orig = np.asarray(orig_pic.tolist(), dtype=float)
    white = pic.pixel(0, 0, 0) >= 0.5
    work = np.full(orig.shape, 1.0 if white else 0.0)
    subset = list(subset_ids) if subset_ids is not None else None

    start = process_time()
    caches = build_line_cache(nails)
    logger.info(f"Line cache built in {process_time() - start:.2f}s")

    current_idx = 0
    pull_order = [0]
    i = 0
    fails = 0

    while True:
        i += 1
        if i % 500 == 0:
            logger.info(f"Iteration: {i}")

        if i_limit is None:
            if fails >= 3:
                break
        elif i > i_limit:
            break

        rr, cc, val, _, _ = caches[current_idx]
        best_idx, (seg_start, seg_end), best_improvement = _scan_from(
            caches[current_idx], work, orig, strength, current_idx, subset
        )

        if best_improvement <= 0:
            fails += 1
            continue

        pull_order.append(best_idx)
        seg = slice(seg_start, seg_end)
        work[rr[seg], cc[seg]] = np.clip(work[rr[seg], cc[seg]] + strength * val[seg], 0, 1)
        current_idx = best_idx

    logger.info(f"Time: {(process_time() - start):.2f}")
    return pull_order, core_mod.Image.from_nested(work.tolist())


def generate_rgb(img, shape, nails, config: Config):
    strength = 0.1 if config.wb else -0.1

    # one greedy run per channel on a shared nail grid
    orders = []
    for channel in range(3):
        order, _ = create_art(nails, img.channel(channel),
                              init_canvas(shape, black=config.wb), strength,
                              i_limit=config.pull_amount,
                              random_nails=config.random_nails)
        orders.append(order)

    max_pulls = max(len(o) for o in orders)
    orders = [o + [o[-1]] * (max_pulls - len(o)) for o in orders]

    out_h = int(config.side_len * config.radius1_multiplier)
    out_w = int(config.side_len * config.radius2_multiplier)
    logger.info((out_h, out_w, 3))

    export = config.export_strength if config.wb else -config.export_strength
    result = pull_order_to_array_rgb(
        orders,
        init_canvas((out_h, out_w, 3), black=config.wb),
        nails,
        strength=export,
        shape=shape,
    )
    return result, orders


def generate_bw(img, shape, nails, config: Config):
    strength = 0.05 if config.wb else -0.05

    target = img.gray(0.9)
    pull_order, _ = create_art(
        nails, target, init_canvas(shape, black=config.wb), strength,
        i_limit=config.pull_amount, random_nails=config.random_nails,
    )

    out_h = int(config.side_len * config.radius1_multiplier)
    out_w = int(config.side_len * config.radius2_multiplier)
    export = config.export_strength if config.wb else -config.export_strength
    result = pull_order_to_array_bw(
        pull_order,
        init_canvas((out_h, out_w), black=config.wb),
        nails,
        export,
        shape=shape,
    )
    return result, pull_order
