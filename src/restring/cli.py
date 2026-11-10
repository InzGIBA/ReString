import argparse
import json
import logging
from pathlib import Path

from restring import _core, api, palettes
from restring.animation import animate_project
from restring.canvas import init_canvas, pull_order_to_array_bw, pull_order_to_array_rgb
from restring.generator import resolve_export_strength
from restring.image_transformations import largest_rect, largest_square, resize
from restring.layouts import LayoutError
from restring.poster import poster_svg, thread_lengths_mm
from restring.project import load as load_project
from restring.project import save as save_project

logger = logging.getLogger(__name__)

LONG_SIDE = 300
RGB_TRIPLE = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]


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
    parser.add_argument('--poster', action="store", dest="poster", default=None)
    parser.add_argument('--number-every', action="store", type=int, dest="number_every", default=10)
    parser.add_argument('--poster-preview', action="store_true")
    parser.add_argument('--anim', action="store", dest="anim", default=None)
    parser.add_argument('--anim-frames', action="store", type=int, dest="anim_frames", default=180)
    parser.add_argument('--wb', action="store_true")
    parser.add_argument('--rgb', action="store_true")
    parser.add_argument('--palette', action="store", dest="palette", default=None,
                        help="thread palette: built-in name (rgb, cmy, cmyk) or a JSON "
                             "palette file path")
    parser.add_argument('--rect', action="store_true")
    parser.add_argument('--layout', action="store", dest="layout", default=None,
                        help="nail layout spec: circle | rect | polygon:sides[:count] | "
                             "star:points:inner[:count] | rings:r:count,r:count | "
                             "svg:file.svg[:count], with an optional @aspect suffix "
                             "(e.g. polygon:5@1.5) for non-square boards")
    parser.add_argument('--realistic', action="store_true")
    parser.add_argument('--rollback', action="store_true")
    parser.add_argument('--metrics', action="store", dest="metrics", default=None,
                        help="write a quality report JSON (MSE, correlation, plain and "
                             "blurred SSIM of the render against the working target); "
                             "generate mode only")
    parser.add_argument('--canvas-size', action="store", type=float, dest="canvas_size",
                        default=None,
                        help="board size in mm: poster printing size (default 260), or the "
                             "physical size behind --realistic (default 400)")
    parser.add_argument('--thread-width', action="store", type=float, dest="thread_width",
                        default=0.2)
    return parser


def write_poster(proj, args):
    canvas_size = args.canvas_size if args.canvas_size is not None else 260
    svg = poster_svg(proj, canvas_size_mm=canvas_size,
                     number_every=args.number_every, show_preview=args.poster_preview)
    Path(args.poster).write_text(svg)
    logger.info(f"Poster written: {args.poster}")


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

    if args.metrics and args.project:
        parser.error("--metrics needs -i: the working target is unknown for --project runs")

    if args.project:
        proj = load_project(args.project)
        if args.rgb and proj.mode != "rgb":
            parser.error(f"--rgb does not match the project mode {proj.mode!r}")
        if not args.rgb and proj.mode == "rgb":
            parser.error("this project is an RGB run, pass --rgb to re-render it")
        render_project(proj, args)
        if args.poster:
            write_poster(proj, args)
        if args.anim:
            animate_project(proj, args.anim, export_strength=args.export_strength,
                            size=args.side_len, frames=args.anim_frames)
        return

    if args.poster and not args.project_out:
        parser.error("--poster needs --project or --project-out")
    if args.anim and not args.project:
        parser.error("--anim needs --project")

    if args.layout and args.rect:
        parser.error("--rect and --layout are mutually exclusive")
    layout_spec = args.layout or ("rect" if args.rect else "circle")
    try:
        _builder, _label, aspect = api.parse_layout_spec(layout_spec)
    except ValueError as exc:
        parser.error(f"bad --layout: {exc}")

    palette_spec = "wb" if args.wb else ("rgb" if args.rgb else (args.palette or "bw"))
    if args.rgb and args.palette:
        logger.info("--rgb given, ignoring --palette")
    try:
        threads, _wb = api._resolve_threads(palette_spec)
    except (palettes.PaletteError, ValueError) as exc:
        parser.error(str(exc))
    mode = "rgb" if threads is not None else "bw"
    if args.project_out and mode == "rgb" and [t.rgb for t in threads] != RGB_TRIPLE:
        parser.error("--project-out supports bw and the rgb palette only; other "
                     "palettes carry no stored colors in format version 1")

    options = api.GenerateOptions(
        layout=layout_spec,
        nail_step=args.nail_step,
        pulls=args.pull_amount,
        strength=args.export_strength,
        palette=palette_spec,
        grid=LONG_SIDE,
        export_size=args.side_len,
        weight=args.weight_peak,
        min_chord=args.min_chord,
        rollback=args.rollback,
        realistic=args.realistic,
        canvas_size=args.canvas_size if args.canvas_size is not None else 400,
        thread_width=args.thread_width,
    )
    try:
        run = api.generate(args.input_file, options)
    except (ValueError, LayoutError) as exc:
        parser.error(f"bad --layout: {exc}")
    logger.info(f"Nails amount: {run.stats.nails}")

    if args.project_out:
        digest = api.project_digest(args.input_file)
        grid = LONG_SIDE if aspect == 1.0 else [LONG_SIDE, int(round(LONG_SIDE * aspect))]
        proj = save_project(
            args.project_out,
            mode=mode,
            config={
                "grid": grid,
                "wb": args.wb,
                "nail_step": args.nail_step,
                "layout": layout_spec,
                "pull_budget": args.pull_amount,
                "weight": args.weight_peak,
                "min_chord": args.min_chord,
                "random_nails": args.random_nails,
            },
            nails=run.nails,
            pull_orders=run.pull_orders,
            input_digest=digest,
        )
        canvas_mm = args.canvas_size if args.canvas_size is not None else 260
        lengths_mm = thread_lengths_mm(proj, canvas_mm)
        if mode == "rgb":
            logger.info("Thread lengths: " + "/".join(f"{length / 1000:.0f}" for length in lengths_mm) + " m")
        else:
            logger.info(f"Thread length: {lengths_mm[0] / 1000:.0f} m")
        logger.info(f"Project written: {args.project_out}")
        if args.poster:
            write_poster(proj, args)

    run.image.save_png(args.output_file)

    if args.metrics:
        out_h, out_w = run.image.shape()[:2]
        target_source = _core.Image.load(args.input_file)
        if aspect != 1.0:
            target_img = resize(largest_rect(target_source, aspect),
                                (LONG_SIDE, int(round(LONG_SIDE * aspect))))
        else:
            target_img = resize(largest_square(target_source), (LONG_SIDE, LONG_SIDE))
        target_resized = resize(target_img, (out_h, out_w))
        target_gray = target_resized.gray(1.0)
        render_gray = run.image if mode == "bw" else run.image.gray(1.0)
        report = {
            "mode": mode,
            "pulls": max(len(o) - 1 for o in run.pull_orders),
            "nails": run.stats.nails,
            "export": [out_h, out_w],
            "elapsed_s": run.stats.elapsed_s,
            "mse": round(_core.mse(render_gray, target_gray), 4),
            "corr": round(_core.corr(render_gray, target_gray), 4),
            "ssim": round(_core.ssim(render_gray, target_gray), 4),
            "blurred_ssim": round(_core.ssim_blur(render_gray, target_gray, 2), 4),
        }
        Path(args.metrics).write_text(json.dumps(report, indent=1))
        logger.info(f"Metrics: mse={report['mse']} corr={report['corr']} "
                    f"ssim={report['ssim']} blurred_ssim={report['blurred_ssim']} "
                    f"pulls={report['pulls']} in {report['elapsed_s']}s -> {args.metrics}")


if __name__ == '__main__':
    main()
