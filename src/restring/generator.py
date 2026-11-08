import logging
from dataclasses import dataclass
from time import process_time

import numpy as np

from restring.canvas import (
    init_canvas,
    line_aa,
    pull_order_to_array_bw,
    pull_order_to_array_rgb,
)
from restring.image_transformations import rgb2gray
from restring.nails import scale_nails

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


def build_line_cache(nails):
    """Precompute anti-aliased line pixels for every ordered nail pair.

    Returns one CSR-style record per source nail i:
        (rr, cc, val, starts, targets)
    where segment k covers the line i -> targets[k] over pixels
    rr[starts[k]:starts[k+1]] (the last segment runs to the end). With this the
    greedy candidate scan for one source nail is a handful of vectorized numpy
    operations instead of a Python loop that re-rasterizes every candidate line
    on every iteration.
    """
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
        rr = np.concatenate(rrs).astype(np.int32)
        cc = np.concatenate(ccs).astype(np.int32)
        val = np.concatenate(vals).astype(np.float32)
        total_pixels += len(rr)
        caches.append((rr, cc, val, np.asarray(starts[:-1], dtype=np.int64), np.asarray(targets)))
    logger.info(
        f"Line cache: {n * (n - 1)} lines, {total_pixels / 1e6:.1f}M pixels "
        f"(~{total_pixels * 12 / 1e6:.0f} MB)"
    )
    return caches


def _scan_from(cache, pic, orig_pic, strength, current_idx, subset_ids=None):
    """Vectorized replacement of the per-candidate find-best loop.

    Returns (best_nail_idx, segment_slice, best_improvement) with the same
    last-maximum tie-breaking as the original `>=` comparison loop. Segment
    sums use cumsum differences, which stays correct for non-contiguous
    random-nail subsets (unlike a plain reduceat over filtered starts).

    Note: in random-nails mode the original could evaluate a degenerate
    self-line (one darkened pixel); it can never win against real candidates,
    so the self-line is simply excluded here.
    """
    rr, cc, val, starts, targets = cache
    bounds = np.append(starts, len(rr))  # segment k spans bounds[k]:bounds[k+1]

    if subset_ids is None:
        seg_positions = np.arange(len(targets))
    else:
        seg_positions = np.searchsorted(targets, subset_ids[subset_ids != current_idx])
    seg_starts = bounds[seg_positions]
    seg_ends = bounds[seg_positions + 1]

    cur_px = pic[rr, cc]
    new_px = np.clip(cur_px + strength * val, 0, 1)
    improvement_px = (cur_px - orig_pic[rr, cc]) ** 2 - (new_px - orig_pic[rr, cc]) ** 2
    cum = np.concatenate(([0.0], np.cumsum(improvement_px)))
    seg_improvement = cum[seg_ends] - cum[seg_starts]

    best = len(seg_improvement) - 1 - np.argmax(seg_improvement[::-1])  # last max
    return (int(targets[seg_positions[best]]),
            (int(seg_starts[best]), int(seg_ends[best])),
            float(seg_improvement[best]))


def create_art(nails, orig_pic, pic, strength, i_limit=None, random_nails=None, line_cache=None):
    start = process_time()
    iter_times = []

    cache_build = process_time()
    caches = line_cache if line_cache is not None else build_line_cache(nails)
    logger.info(f"Line cache built in {process_time() - cache_build:.2f}s")

    # the original implementation re-seeded default_rng(42) on every iteration,
    # i.e. it always worked with the same subset — reproduce that exactly
    subset_ids = None
    if random_nails is not None:
        subset_ids = np.random.default_rng(42).choice(
            range(len(nails)), size=random_nails, replace=False
        )

    current_idx = 0
    pull_order = [0]

    i = 0
    fails = 0

    while True:
        start_iter = process_time()

        i += 1

        if i % 500 == 0:
            logger.info(f"Iteration: {i}")

        if i_limit is None:
            if fails >= 3:
                break
        else:
            if i > i_limit:
                break

        rr, cc, val, _, _ = caches[current_idx]
        best_idx, (seg_start, seg_end), best_improvement = _scan_from(
            caches[current_idx], pic, orig_pic, strength, current_idx, subset_ids
        )

        if best_improvement <= 0:
            fails += 1
            continue

        pull_order.append(best_idx)
        seg = slice(seg_start, seg_end)
        pic[rr[seg], cc[seg]] = np.clip(pic[rr[seg], cc[seg]] + strength * val[seg], 0, 1)

        current_idx = best_idx
        iter_times.append(process_time() - start_iter)

    logger.info(f"Time: {(process_time() - start):.2f}")
    logger.info(f"Avg iteration time: {np.mean(iter_times):.6f}")
    return pull_order


def generate_rgb(img, shape, nails, config: Config):
    strength = 0.1 if config.wb else -0.1

    r = img[:, :, 0]
    g = img[:, :, 1]
    b = img[:, :, 2]

    # one line cache shared by all three channels (the same nail grid)
    shared_cache = build_line_cache(nails)

    pic_r = init_canvas(shape, black=config.wb)
    pull_orders_r = create_art(nails, r, pic_r, strength, i_limit=config.pull_amount,
                               random_nails=config.random_nails, line_cache=shared_cache)

    pic_g = init_canvas(shape, black=config.wb)
    pull_orders_g = create_art(nails, g, pic_g, strength, i_limit=config.pull_amount,
                               random_nails=config.random_nails, line_cache=shared_cache)

    pic_b = init_canvas(shape, black=config.wb)
    pull_orders_b = create_art(nails, b, pic_b, strength, i_limit=config.pull_amount,
                               random_nails=config.random_nails, line_cache=shared_cache)

    max_pulls = np.max([len(pull_orders_r), len(pull_orders_g), len(pull_orders_b)])
    pull_orders_r = pull_orders_r + [pull_orders_r[-1]] * (max_pulls - len(pull_orders_r))
    pull_orders_g = pull_orders_g + [pull_orders_g[-1]] * (max_pulls - len(pull_orders_g))
    pull_orders_b = pull_orders_b + [pull_orders_b[-1]] * (max_pulls - len(pull_orders_b))

    pull_orders = [pull_orders_r, pull_orders_g, pull_orders_b]

    color_image_dimens = int(config.side_len * config.radius1_multiplier), \
        int(config.side_len * config.radius2_multiplier), 3
    blank = init_canvas(color_image_dimens, black=config.wb)

    logger.info(color_image_dimens)

    scaled_nails = scale_nails(color_image_dimens[1] / shape[1], color_image_dimens[0] / shape[0], nails)

    return pull_order_to_array_rgb(
        pull_orders,
        blank,
        scaled_nails,
        (np.array((1., 0., 0.,)), np.array((0., 1., 0.,)), np.array((0., 0., 1.,))),
        config.export_strength if config.wb else -config.export_strength
    ), pull_orders


def generate_bw(img, shape, nails, config: Config):
    strength = 0.05 if config.wb else -0.05

    orig_pic = rgb2gray(img) * 0.9
    image_dimens = int(config.side_len * config.radius1_multiplier), int(config.side_len * config.radius2_multiplier)

    pic = init_canvas(shape, black=config.wb)
    pull_order = create_art(nails, orig_pic, pic, strength, i_limit=config.pull_amount,
                            random_nails=config.random_nails)
    blank = init_canvas(image_dimens, black=config.wb)

    scaled_nails = scale_nails(image_dimens[1] / shape[1], image_dimens[0] / shape[0], nails)

    return pull_order_to_array_bw(
        pull_order,
        blank,
        scaled_nails,
        config.export_strength if config.wb else -config.export_strength
    ), pull_order
