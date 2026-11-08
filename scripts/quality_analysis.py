"""Quality-vs-pull-count analysis for ReString.

Real string art uses ~3000-7000 thread pulls. This script measures when the
rendered picture reaches its best quality and when it starts degrading, and
how the optimum shifts with the export strength (-s).

Method: the greedy pull sequence is prefix-deterministic (an N-pull run
produces exactly the first N pulls of a longer run), so ONE full greedy run
per image/mode plus cheap prefix renders cover every snapshot point.

Usage:
    uv run python scripts/quality_analysis.py --mode bw  --photo tests/data/portrait_woman_1.jpg
    uv run python scripts/quality_analysis.py --mode bw  --photo tests/data/portrait_man_1.jpg
    uv run python scripts/quality_analysis.py --mode rgb --photo tests/data/portrait_woman_1.jpg

Writes charts and metrics into docs/img/.
"""

import argparse
import json
import logging
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from _bridge import image_to_numpy  # noqa: E402

from restring import _core  # noqa: E402
from restring.canvas import (  # noqa: E402
    init_canvas,
    line_aa,
    pull_order_to_array_bw,
    pull_order_to_array_rgb,
)
from restring.generator import create_art  # noqa: E402
from restring.image_transformations import (  # noqa: E402
    largest_square,
    resize,
)
from restring.metrics import ssim  # noqa: E402
from restring.nails import create_circle_nail_positions  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("quality_analysis")


def get_aa_line(from_pos, to_pos, strength, picture):
    """Overlay an AA line on a numpy canvas (this script's replay helper;
    the runtime package itself is numpy-free)."""
    rr, cc, val = line_aa(from_pos[0], from_pos[1], to_pos[0], to_pos[1])
    rr, cc, val = np.asarray(rr), np.asarray(cc), np.asarray(val)
    line = np.clip(picture[rr, cc] + strength * val, 0, 1)
    return line, rr, cc

LONG_SIDE = 300
MAX_PULLS = 7000
SNAPSHOTS = [50, 100, 200, 300, 500, 700, 1000, 1500, 2000, 3000, 4000, 5000, 6000, 7000]
MONTAGE_NS = [100, 500, 1000, 2000, 4000, 7000]
EXPORT_STRENGTHS = [0.05, 0.1, 0.15, 0.2]

OUT_DIR = Path(__file__).parent.parent / "docs" / "img"


def mse(a, b):
    return float(np.mean((a - b) ** 2))


def corr(a, b):
    return float(np.corrcoef(a.ravel(), b.ravel())[0, 1])


def load_working_image(path):
    """Mirror restring.cli preprocessing: RGB load, square-crop, resize to 300."""
    return resize(largest_square(_core.Image.load(path)), (LONG_SIDE, LONG_SIDE))


def simulate_working(order, nails, target, strength, snapshot_set):
    """Replay the pull order on the working canvas, snapshot the internal MSE.

    This replicates what create_art optimizes: the working simulation with its
    own (lower) thread strength.
    """
    pic = np.ones(target.shape)  # the working canvas this script replays
    current = nails[order[0]]
    snapshots = {}
    for i, idx in enumerate(order[1:], start=1):
        line, rr, cc = get_aa_line(current, nails[idx], strength, pic)
        pic[rr, cc] = line
        current = nails[idx]
        if i in snapshot_set:
            snapshots[i] = mse(pic, target)
    return snapshots


def degradation_points(ns, values, k=1.05):
    """Return (argmin N, degradation-onset N) — onset = first N past the
    minimum where the metric is k times worse than the best."""
    best_i = int(np.argmin(values))
    onset = None
    for i in range(best_i + 1, len(values)):
        if values[i] > values[best_i] * k:
            onset = ns[i]
            break
    return ns[best_i], onset


def run_bw(photo, tag):
    target_img = load_working_image(photo).gray(0.9)
    target = image_to_numpy(target_img)
    shape = target.shape
    nails = create_circle_nail_positions(shape, nail_step=4)
    logger.info(f"bw: {len(nails)} nails, greedy run up to {MAX_PULLS} pulls")

    order, _ = create_art(nails, target_img, init_canvas(shape), -0.05, i_limit=MAX_PULLS)
    threads = len(order) - 1
    logger.info(f"bw: greedy produced {threads} improving pulls")
    snap_set = {n for n in SNAPSHOTS if n <= threads}
    working = simulate_working(order, nails, target, -0.05, snap_set)

    ns = sorted(snap_set)
    results = {"threads": threads, "strengths": {}, "working_mse": {str(n): working[n] for n in ns}}

    for s in EXPORT_STRENGTHS:
        rows = []
        for n in ns:
            render_img = pull_order_to_array_bw(order[: n + 1], init_canvas(shape), nails, -s,
                                                shape=shape)
            render = image_to_numpy(render_img)
            rows.append({
                "n": n,
                "mse": mse(render, target),
                "ssim": ssim(target_img, render_img),
                "corr": corr(render, target),
                "mean": float(render.mean()),
            })
        results["strengths"][str(s)] = rows
        logger.info(f"bw: export strength {s} done")

    # charts
    fig, ax = plt.subplots(figsize=(8, 5))
    default = results["strengths"]["0.1"]
    ax.plot(ns, [r["mse"] for r in default], "o-", label="рендер (сила нити 0.1)")
    ax.plot(ns, [working[n] for n in ns], "s--", label="рабочая симуляция (сила 0.05)")
    n_best, n_deg = degradation_points(ns, [r["mse"] for r in default])
    ax.axvline(n_best, color="crimson", ls=":", label=f"оптимум N* = {n_best}")
    if n_deg:
        ax.axvline(n_deg, color="darkorange", ls=":", label=f"деградация >5% ({n_deg})")
    ax.set_xscale("log")
    ax.set_xlabel("Число нитей (лог. шкала)")
    ax.set_ylabel("MSE против эталона")
    ax.set_title("Ч/Б: ошибка рендера и внутренней симуляции vs число нитей")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"bw_mse_curves_{tag}.png", dpi=150)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    ax1.plot(ns, [r["ssim"] for r in default], "o-")
    ax1.set_xscale("log")
    ax1.set_xlabel("Число нитей")
    ax1.set_ylabel("SSIM")
    ax1.set_title("SSIM рендера (сила 0.1)")
    best_ssim_n = ns[int(np.argmax([r["ssim"] for r in default]))]
    ax1.axvline(best_ssim_n, color="crimson", ls=":")
    ax2.plot(ns, [r["corr"] for r in default], "o-", color="tab:green")
    ax2.set_xscale("log")
    ax2.set_xlabel("Число нитей")
    ax2.set_ylabel("Корреляция")
    ax2.set_title("Корреляция с эталоном (сила 0.1)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"bw_ssim_corr_{tag}.png", dpi=150)

    fig, ax = plt.subplots(figsize=(8, 5))
    for s in EXPORT_STRENGTHS:
        rows = results["strengths"][str(s)]
        ax.plot([r["n"] for r in rows], [r["mse"] for r in rows], "o-",
                label=f"сила экспорта {s}")
    ax.set_xscale("log")
    ax.set_xlabel("Число нитей (лог. шкала)")
    ax.set_ylabel("MSE рендера")
    ax.set_title("Ч/Б: оптимум зависит от силы нити при экспорте")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"export_strength_family_{tag}.png", dpi=150)

    montage_ns = [n for n in MONTAGE_NS if n <= threads]
    fig, axes = plt.subplots(1, len(montage_ns), figsize=(3 * len(montage_ns), 3.4))
    for ax, n in zip(axes, montage_ns):
        render_img = pull_order_to_array_bw(order[: n + 1], init_canvas(shape), nails, -0.1,
                                            shape=shape)
        ax.imshow(image_to_numpy(render_img), cmap="gray", vmin=0, vmax=1)
        ax.set_title(f"N = {n}")
        ax.axis("off")
    fig.suptitle("Ч/Б, сила нити 0.1: эволюция картины")
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"bw_montage_{tag}.png", dpi=150)

    return results


def run_rgb(photo, tag):
    img = load_working_image(photo)
    img_np = image_to_numpy(img)
    shape = (LONG_SIDE, LONG_SIDE)
    nails = create_circle_nail_positions(shape, nail_step=4)
    logger.info(f"rgb: {len(nails)} nails, 3 greedy runs up to {MAX_PULLS} pulls")

    orders = []
    for channel in range(3):
        order, _ = create_art(nails, img.channel(channel), init_canvas(shape), -0.1,
                              i_limit=MAX_PULLS)
        orders.append(order)
        logger.info(f"rgb: channel {channel} -> {len(order) - 1} pulls")

    ns = [n for n in SNAPSHOTS if n <= min(len(o) for o in orders) - 1]
    rows = []
    for n in ns:
        # truncate each channel order to n+1 pulls, padding shorter ones with their last nail
        padded = [o[: n + 1] if len(o) >= n + 1 else o + [o[-1]] * (n + 1 - len(o)) for o in orders]
        render_img = pull_order_to_array_rgb(padded, init_canvas(shape + (3,)), nails,
                                             strength=-0.1, shape=shape)
        render = image_to_numpy(render_img)
        rows.append({
            "n": n,
            "mse": mse(render, img_np),
            "ch_mse": [mse(render[:, :, c], img_np[:, :, c]) for c in range(3)],
        })
        logger.info(f"rgb: snapshot {n} done")

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(ns, [r["mse"] for r in rows], "o-", label="RGB (все каналы)")
    for c, name in enumerate("RGB"):
        ax.plot(ns, [r["ch_mse"][c] for r in rows], "--", label=f"канал {name}")
    n_best, n_deg = degradation_points(ns, [r["mse"] for r in rows])
    ax.axvline(n_best, color="crimson", ls=":", label=f"оптимум N* = {n_best}")
    if n_deg:
        ax.axvline(n_deg, color="darkorange", ls=":", label=f"деградация >5% ({n_deg})")
    ax.set_xscale("log")
    ax.set_xlabel("Число нитей (лог. шкала)")
    ax.set_ylabel("MSE против эталона")
    ax.set_title("RGB: ошибка рендера vs число нитей (сила нити 0.1)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"rgb_mse_curves_{tag}.png", dpi=150)

    return {"threads": [len(o) - 1 for o in orders], "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["bw", "rgb"], required=True)
    parser.add_argument("--photo", required=True)
    parser.add_argument("--tag", default=None, help="suffix for output files (default: photo stem)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = args.tag or Path(args.photo).stem

    if args.mode == "bw":
        results = run_bw(args.photo, tag)
        out_file = OUT_DIR / f"metrics_bw_{tag}.json"
    else:
        results = run_rgb(args.photo, tag)
        out_file = OUT_DIR / f"metrics_rgb_{tag}.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    logger.info(f"metrics written to {out_file}")


if __name__ == "__main__":
    main()
