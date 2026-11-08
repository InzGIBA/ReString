import argparse
import logging

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
from skimage.transform import resize

from restring.generator import Config, generate_bw, generate_rgb
from restring.image_transformations import largest_square
from restring.nails import create_circle_nail_positions, create_rectangle_nail_positions

logger = logging.getLogger(__name__)

LONG_SIDE = 300


def build_parser():
    parser = argparse.ArgumentParser(description='Create string art with ReString')
    parser.add_argument('-i', action="store", dest="input_file")
    parser.add_argument('-o', action="store", dest="output_file", default="output.png")
    parser.add_argument('-d', action="store", type=int, dest="side_len", default=300)
    parser.add_argument('-s', action="store", type=float, dest="export_strength", default=0.1)
    parser.add_argument('-l', action="store", type=int, dest="pull_amount", default=None)
    parser.add_argument('-r', action="store", type=int, dest="random_nails", default=None)
    parser.add_argument('-r1', action="store", type=float, dest="radius1_multiplier", default=1)
    parser.add_argument('-r2', action="store", type=float, dest="radius2_multiplier", default=1)
    parser.add_argument('-n', action="store", type=int, dest="nail_step", default=4)
    parser.add_argument('--wb', action="store_true")
    parser.add_argument('--rgb', action="store_true")
    parser.add_argument('--rect', action="store_true")
    return parser


def main(argv=None):
    strfmt = '[%(asctime)s] [%(name)s] [%(levelname)s]: %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'
    logging.basicConfig(level=logging.INFO, format=strfmt, datefmt=datefmt)

    args = build_parser().parse_args(argv)

    config = Config(
        side_len=args.side_len,
        export_strength=args.export_strength,
        pull_amount=args.pull_amount,
        random_nails=args.random_nails,
        radius1_multiplier=args.radius1_multiplier,
        radius2_multiplier=args.radius2_multiplier,
        wb=args.wb,
    )

    img = mpimg.imread(args.input_file)

    if np.any(img > 100):
        img = img / 255

    if args.radius1_multiplier == 1 and args.radius2_multiplier == 1:
        img = largest_square(img)
        img = resize(img, (LONG_SIDE, LONG_SIDE))

    shape = (len(img), len(img[0]))

    if args.rect:
        nails = create_rectangle_nail_positions(shape, args.nail_step)
    else:
        nails = create_circle_nail_positions(shape, args.nail_step,
                                             args.radius1_multiplier, args.radius2_multiplier)

    logger.info(f"Nails amount: {len(nails)}")

    if args.rgb:
        result, _ = generate_rgb(img, shape, nails, config)
    else:
        result, _ = generate_bw(img, shape, nails, config)
        # logger.info(
        #     f"Thread pull order by nail index:\n{'-'.join([str(idx) for idx in pull_order])}"
        # )

    mpimg.imsave(args.output_file, result, cmap=plt.get_cmap("gray"), vmin=0.0, vmax=1.0)


if __name__ == '__main__':
    main()
