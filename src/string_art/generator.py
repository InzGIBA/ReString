import logging
from dataclasses import dataclass
from time import process_time

import numpy as np

from string_art.canvas import (
    get_aa_line,
    init_canvas,
    pull_order_to_array_bw,
    pull_order_to_array_rgb,
)
from string_art.image_transformations import rgb2gray
from string_art.nails import scale_nails

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


def find_best_nail_position(current_position, nails, pic, orig_pic, strength, random_nails=None):
    best_improvement = -99999
    best_nail_position = None
    best_nail_idx = None

    if random_nails is not None:
        rng = np.random.default_rng(42)
        nail_ids = rng.choice(range(len(nails)), size=random_nails, replace=False)
        nails_and_ids = list(zip(nail_ids, nails[nail_ids]))
    else:
        nails_and_ids = enumerate(nails)

    for nail_idx, nail_position in nails_and_ids:
        overlayed_line, rr, cc = get_aa_line(current_position, nail_position, strength, pic)

        before_diff = np.abs(pic[rr, cc] - orig_pic[rr, cc])**2
        after_diff = np.abs(overlayed_line - orig_pic[rr, cc])**2

        improvement = np.sum(before_diff - after_diff)

        if improvement >= best_improvement:
            best_improvement = improvement
            best_nail_position = nail_position
            best_nail_idx = nail_idx

    return best_nail_idx, best_nail_position, best_improvement


def create_art(nails, orig_pic, pic, strength, i_limit=None, random_nails=None):
    start = process_time()
    iter_times = []

    current_position = nails[0]
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

        idx, best_position, best_improvement = find_best_nail_position(
            current_position,
            nails,
            pic,
            orig_pic,
            strength,
            random_nails,
        )

        if best_improvement <= 0:
            fails += 1
            continue

        pull_order.append(idx)
        best_line, rr, cc = get_aa_line(current_position, best_position, strength, pic)
        pic[rr, cc] = best_line

        current_position = best_position
        iter_times.append(process_time() - start_iter)

    logger.info(f"Time: {(process_time() - start):.2f}")
    logger.info(f"Avg iteration time: {np.mean(iter_times):.6f}")
    return pull_order


def generate_rgb(img, shape, nails, config: Config):
    strength = 0.1 if config.wb else -0.1

    r = img[:, :, 0]
    g = img[:, :, 1]
    b = img[:, :, 2]

    pic_r = init_canvas(shape, black=config.wb)
    pull_orders_r = create_art(nails, r, pic_r, strength, i_limit=config.pull_amount,
                               random_nails=config.random_nails)

    pic_g = init_canvas(shape, black=config.wb)
    pull_orders_g = create_art(nails, g, pic_g, strength, i_limit=config.pull_amount,
                               random_nails=config.random_nails)

    pic_b = init_canvas(shape, black=config.wb)
    pull_orders_b = create_art(nails, b, pic_b, strength, i_limit=config.pull_amount,
                               random_nails=config.random_nails)

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
