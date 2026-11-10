import logging
from dataclasses import dataclass

from restring import _core
from restring.canvas import init_canvas, pull_order_to_array_bw, pull_order_to_array_rgb

logger = logging.getLogger(__name__)

# fitted s*(L) = k / L, least squares in log space over the uncensored points
# of docs/img/params/pulls.json (k = 104.0, residual band x1.06); re-run
# scripts/fit_export_strength.py to refit. The ceiling is 0.2, not 0.3: the
# sweep grid tops out at 0.2 and that value wins every count up to 500 pulls,
# while 0.3 measured worse than a blank canvas on synthetic fixtures.
AUTO_EXPORT_K = 104.0
AUTO_EXPORT_FLOOR = 0.03
AUTO_EXPORT_CEIL = 0.2


def resolve_export_strength(pull_count):
    """Auto export strength from the actual pull count, clamped to 0.03..0.2.

    The 1/L law and the constant come from scripts/fit_export_strength.py.
    Anchors: measured best s is 0.1 at 1000 pulls and 0.05 at 2000 pulls.
    """
    return min(AUTO_EXPORT_CEIL, max(AUTO_EXPORT_FLOOR, AUTO_EXPORT_K / pull_count))


@dataclass
class Config:
    """Generation parameters shared by the B/W and RGB pipelines."""

    side_len: int = 300
    export_strength: float | None = None
    pull_amount: int | None = None
    random_nails: int | None = None
    radius1_multiplier: float = 1
    radius2_multiplier: float = 1
    wb: bool = False
    weight_peak: float | None = None
    min_chord: float | None = None


def create_art(nails, orig_pic, pic, strength, i_limit=None, random_nails=None, weights=None,
               min_chord=None):
    """Greedy pull-order search on a grayscale target Image (Rust core).

    `pic` is only used for its initial fill (white/black canvas). Returns
    (pull_order, final working canvas Image). With `random_nails=k` a fixed
    seeded subset of k candidates is scanned each iteration (deterministic).
    With `weights` set to a grayscale Image of the target shape, each pixel's
    error contribution is multiplied by the weight value, so threads
    concentrate on high-weight regions. With `min_chord` set, candidates
    closer than the distance in working-grid pixels are skipped; on a dead
    end the search takes the best masked-out pull once and logs at DEBUG.
    """
    order, final = _core.create_art(
        [(int(r), int(c)) for r, c in nails],
        orig_pic,
        float(strength),
        int(i_limit) if i_limit is not None else None,
        int(random_nails) if random_nails is not None else None,
        pic.pixel(0, 0, 0) >= 0.5,
        weights,
        float(min_chord) if min_chord is not None else None,
    )
    return [int(i) for i in order], final


def generate_rgb(img, shape, nails, config: Config):
    strength = 0.1 if config.wb else -0.1

    # one greedy run per channel on a shared nail grid
    orders = []
    exports = []
    for channel in range(3):
        order, _ = create_art(nails, img.channel(channel),
                              init_canvas(shape, black=config.wb), strength,
                              i_limit=config.pull_amount,
                              random_nails=config.random_nails,
                              min_chord=config.min_chord)
        orders.append(order)
        magnitude = config.export_strength
        if magnitude is None:
            magnitude = resolve_export_strength(len(order) - 1)
            logger.info(f"Export strength: {magnitude:.3f} (auto, {len(order) - 1} pulls)")
        exports.append(magnitude if config.wb else -magnitude)

    max_pulls = max(len(o) for o in orders)
    orders = [o + [o[-1]] * (max_pulls - len(o)) for o in orders]

    out_h = int(config.side_len * config.radius1_multiplier)
    out_w = int(config.side_len * config.radius2_multiplier)
    logger.info((out_h, out_w, 3))

    result = pull_order_to_array_rgb(
        orders,
        init_canvas((out_h, out_w, 3), black=config.wb),
        nails,
        strength=exports,
        shape=shape,
    )
    return result, orders


def generate_bw(img, shape, nails, config: Config):
    strength = 0.05 if config.wb else -0.05

    target = img.gray(0.9)
    weights = None
    if config.weight_peak is not None:
        # sigma = side / 3 reproduces the measured sigma 100 on the 300 px
        # grid, bg 0.5 (docs/research/alternatives-experiment.md)
        sigma = max(shape) / 3
        weights = _core.gaussian_weights(shape[1], shape[0], sigma, config.weight_peak, 0.5)
        logger.info(f"Importance weighting: peak {config.weight_peak}, sigma {sigma:.1f}, bg 0.5")
    pull_order, _ = create_art(
        nails, target, init_canvas(shape, black=config.wb), strength,
        i_limit=config.pull_amount, random_nails=config.random_nails,
        weights=weights, min_chord=config.min_chord,
    )

    out_h = int(config.side_len * config.radius1_multiplier)
    out_w = int(config.side_len * config.radius2_multiplier)
    magnitude = config.export_strength
    if magnitude is None:
        magnitude = resolve_export_strength(len(pull_order) - 1)
        logger.info(f"Export strength: {magnitude:.3f} (auto, {len(pull_order) - 1} pulls)")
    export = magnitude if config.wb else -magnitude
    result = pull_order_to_array_bw(
        pull_order,
        init_canvas((out_h, out_w), black=config.wb),
        nails,
        export,
        shape=shape,
    )
    return result, pull_order
