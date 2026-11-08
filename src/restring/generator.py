import logging
from dataclasses import dataclass

from restring import _core
from restring.canvas import init_canvas, pull_order_to_array_bw, pull_order_to_array_rgb

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


def create_art(nails, orig_pic, pic, strength, i_limit=None, random_nails=None):
    """Greedy pull-order search on a grayscale target Image (Rust core).

    `pic` is only used for its initial fill (white/black canvas). Returns
    (pull_order, final working canvas Image). With `random_nails=k` a fixed
    seeded subset of k candidates is scanned each iteration (deterministic).
    """
    order, final = _core.create_art(
        [(int(r), int(c)) for r, c in nails],
        orig_pic,
        float(strength),
        int(i_limit) if i_limit is not None else None,
        int(random_nails) if random_nails is not None else None,
        pic.pixel(0, 0, 0) >= 0.5,
    )
    return [int(i) for i in order], final


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
