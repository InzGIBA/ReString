import argparse
import hashlib
import logging
from pathlib import Path

from restring import _core
from restring.canvas import init_canvas, pull_order_to_array_bw, pull_order_to_array_rgb
from restring.generator import Config, generate_bw, generate_rgb, resolve_export_strength
from restring.image_transformations import largest_square, resize
from restring.nails import create_circle_nail_positions, create_rectangle_nail_positions
from restring.project import load as load_project
from restring.project import save as save_project

logger = logging.getLogger(__name__)

LONG_SIDE = 300


def build_parser():
    parser = argparse.ArgumentParser(description='Create string art with ReString')
    parser.add_argument('-i', action="store", dest="input_file")
    parser.add_argument('-o', action="store", dest="output_file", default="output.png")
    parser.add_argument('-d', action="store", type=int, dest="side_len", default=300)
    parser.add_argument('-s', action="store", type=float, dest="export_strength", default=None)
    parser.add_argument('-l', action="store", type=int, dest="pull_amount", default=None)
    parser.add_argument('-r', action="store", type=int, dest="random_nails", default=None)
    parser.add_argument('-r1', action="store", type=float, dest="radius1_multiplier", default=1)
    parser.add_argument('-r2', action="store", type=float, dest="radius2_multiplier", default=1)
    parser.add_argument('-n', action="store", type=int, dest="nail_step", default=4)
    parser.add_argument('--weight', action="store", type=float, dest="weight_peak", default=None)
    parser.add_argument('--min-chord', action="store", type=float, dest="min_chord", default=None)
    parser.add_argument('--project', action="store", dest="project", default=None)
    parser.add_argument('--project-out', action="store", dest="project_out", default=None)
    parser.add_argument('--wb', action="store_true")
    parser.add_argument('--rgb', action="store_true")
    parser.add_argument('--rect', action="store_true")
    return parser


def render_project(proj, args):
    """Re-render a loaded project with the current -s and -d, no search."""
    grid = proj.config.get("grid", LONG_SIDE)
    gh, gw = (grid, grid) if isinstance(grid, int) else (int(grid[0]), int(grid[1]))
    wb = bool(proj.config.get("wb", False))
    pulls = max(len(order) - 1 for order in proj.pull_orders)

    if proj.mode == "bw":
        magnitude = args.export_strength
        if magnitude is None:
            magnitude = resolve_export_strength(len(proj.pull_orders[0]) - 1)
            logger.info(f"Export strength: {magnitude:.3f} (auto, {len(proj.pull_orders[0]) - 1} pulls)")
        strength = magnitude if wb else -magnitude
        canvas = init_canvas((args.side_len, args.side_len), black=wb)
        result = pull_order_to_array_bw(proj.pull_orders[0], canvas, proj.nails,
                                        strength, shape=(gh, gw))
    else:
        strengths = []
        for order in proj.pull_orders:
            magnitude = args.export_strength
            if magnitude is None:
                magnitude = resolve_export_strength(len(order) - 1)
                logger.info(f"Export strength: {magnitude:.3f} (auto, {len(order) - 1} pulls)")
            strengths.append(magnitude if wb else -magnitude)
        canvas = init_canvas((args.side_len, args.side_len, 3), black=wb)
        result = pull_order_to_array_rgb(proj.pull_orders, canvas, proj.nails,
                                         strength=strengths, shape=(gh, gw))

    logger.info(f"Re-render from project: {pulls} pulls, no search")
    result.save_png(args.output_file)


def main(argv=None):
    strfmt = '[%(asctime)s] [%(name)s] [%(levelname)s]: %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'
    logging.basicConfig(level=logging.INFO, format=strfmt, datefmt=datefmt)

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.project and args.input_file:
        parser.error("--project and -i are mutually exclusive")
    if not args.project and not args.input_file:
        parser.error("either -i or --project is required")

    if args.project:
        proj = load_project(args.project)
        if args.rgb and proj.mode != "rgb":
            parser.error(f"--rgb does not match the project mode {proj.mode!r}")
        if not args.rgb and proj.mode == "rgb":
            parser.error("this project is an RGB run, pass --rgb to re-render it")
        render_project(proj, args)
        return

    config = Config(
        side_len=args.side_len,
        export_strength=args.export_strength,
        pull_amount=args.pull_amount,
        random_nails=args.random_nails,
        radius1_multiplier=args.radius1_multiplier,
        radius2_multiplier=args.radius2_multiplier,
        wb=args.wb,
        weight_peak=args.weight_peak,
        min_chord=args.min_chord,
    )

    img = _core.Image.load(args.input_file)

    if args.radius1_multiplier == 1 and args.radius2_multiplier == 1:
        img = resize(largest_square(img), (LONG_SIDE, LONG_SIDE))

    h, w, _ = img.shape()
    shape = (h, w)

    if args.rect:
        nails = create_rectangle_nail_positions(shape, args.nail_step)
    else:
        nails = create_circle_nail_positions(shape, args.nail_step,
                                             args.radius1_multiplier, args.radius2_multiplier)

    logger.info(f"Nails amount: {len(nails)}")

    if args.rgb:
        result, orders = generate_rgb(img, shape, nails, config)
        mode = "rgb"
    else:
        result, order = generate_bw(img, shape, nails, config)
        orders = [order]
        mode = "bw"

    if args.project_out:
        digest = hashlib.sha256(Path(args.input_file).read_bytes()).hexdigest()
        save_project(
            args.project_out,
            mode=mode,
            config={
                "grid": h if h == w else [h, w],
                "wb": args.wb,
                "nail_step": args.nail_step,
                "layout": "rect" if args.rect else "circle",
                "pull_budget": args.pull_amount,
                "weight": args.weight_peak,
                "min_chord": args.min_chord,
                "random_nails": args.random_nails,
            },
            nails=nails,
            pull_orders=orders,
            input_digest=digest,
        )
        logger.info(f"Project written: {args.project_out}")

    result.save_png(args.output_file)


if __name__ == '__main__':
    main()
