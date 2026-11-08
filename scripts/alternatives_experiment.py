"""Alternative algorithm experiment: importance, asymmetric, multi-scale, local search.

Compares four alternatives to plain greedy on the face fixtures, rectangle
nails, budgets 500 and 2000 threads. Metric: render MSE at s=0.05.

    uv run python scripts/alternatives_experiment.py
"""

import json
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from restring import _core
from restring.image_transformations import largest_square, resize
from restring.nails import create_circle_nail_positions, create_rectangle_nail_positions

SIDE = 300
OUT = Path(__file__).parent.parent / "docs" / "img"
PHOTOS = {
    "male": "tests/data/portrait_male.png",
    "female": "tests/data/portrait_female.png",
}
STRENGTH = -0.05
EXPORT = -0.05


def setup(path):
    img = resize(largest_square(_core.Image.load(path)), (SIDE, SIDE))
    target = img.gray(0.9)
    nails = create_rectangle_nail_positions((SIDE, SIDE), nail_step=4)
    return img, target, nails


def render_mse(order, nails, target):
    render = _core.render_bw(list(order), nails, EXPORT, SIDE, SIDE, SIDE, SIDE, True)
    return _core.mse(render, target)


def center_mse(order, nails, target):
    """MSE inside the central 50% box (importance region)."""
    render = _core.render_bw(list(order), nails, EXPORT, SIDE, SIDE, SIDE, SIDE, True)
    r = np.asarray(render.tolist())
    t = np.asarray(target.tolist())
    box = (slice(SIDE // 4, 3 * SIDE // 4), slice(SIDE // 4, 3 * SIDE // 4))
    return float(np.mean((r[box] - t[box]) ** 2))


def make_weight_map(sigma=100.0, peak=3.0, bg=0.5):
    yy, xx = np.mgrid[0:SIDE, 0:SIDE]
    cy, cx = SIDE / 2, SIDE / 2
    gauss = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))
    w = bg + (peak - bg) * gauss
    return _core.Image.from_nested(w.tolist())


def multiscale(img, target, nails, coarse_budget, fine_budget):
    """Coarse pass at 64x64, then fine pass at 300x300 starting from coarse canvas."""
    coarse_side = 64
    img_c = resize(img, (coarse_side, coarse_side))
    target_c = img_c.gray(0.9)
    nails_c = create_circle_nail_positions((coarse_side, coarse_side), nail_step=4)

    _, coarse_canvas = _core.create_art(nails_c, target_c, STRENGTH, coarse_budget, None, True)
    # upscale the coarse canvas to the fine grid
    canvas_np = np.asarray(coarse_canvas.tolist())
    # use bilinear resize through a temporary Image
    from restring.image_transformations import resize as img_resize
    canvas_img = _core.Image.from_nested(canvas_np.tolist())
    canvas_up = img_resize(canvas_img, (SIDE, SIDE))

    order_fine, final = _core.create_art_from(nails, target, canvas_up, STRENGTH, fine_budget, True)
    return order_fine, final


def run_config(label, fn):
    t0 = time.perf_counter()
    order, final = fn()
    dt = time.perf_counter() - t0
    return {"config": label, "time_s": round(dt, 2), "threads": len(order) - 1, "order": list(order), "final": final}


def main():
    results = {}
    weights = make_weight_map()

    for tag, path in PHOTOS.items():
        img, target, nails = setup(path)
        rows = []

        configs = [
            # baselines
            ("greedy_500", lambda: _core.create_art(nails, target, STRENGTH, 500, None, True)),
            ("greedy_2000", lambda: _core.create_art(nails, target, STRENGTH, 2000, None, True)),
            # importance weighting
            ("weighted_500", lambda: _core.weighted_search(nails, target, weights, STRENGTH, 500, True)),
            ("weighted_2000", lambda: _core.weighted_search(nails, target, weights, STRENGTH, 2000, True)),
            # asymmetric penalties (alpha=2: over-darkening costs 2x)
            ("asym_500", lambda: _core.asymmetric_search(nails, target, 2.0, STRENGTH, 500, True)),
            ("asym_2000", lambda: _core.asymmetric_search(nails, target, 2.0, STRENGTH, 2000, True)),
            # multi-scale: coarse 200 + fine 300 = 500 total
            ("multiscale_500", lambda: multiscale(img, target, nails, 200, 300)),
            # multi-scale: coarse 500 + fine 1500 = 2000 total
            ("multiscale_2000", lambda: multiscale(img, target, nails, 500, 1500)),
        ]

        for label, fn in configs:
            row = run_config(label, fn)
            rows.append(row)
            print(f"{tag} {label}: {row['time_s']}s, {row['threads']} threads")

        # local search: greedy 500 then 2 sweeps
        order_g500 = next(r for r in rows if r["config"] == "greedy_500")["order"]
        t0 = time.perf_counter()
        order_ls, final_ls = _core.local_search(nails, target, order_g500, STRENGTH, 2)
        dt = time.perf_counter() - t0
        rows.append({"config": "local_search_500+2s", "time_s": round(dt, 2),
                      "threads": len(order_ls) - 1, "order": list(order_ls), "final": final_ls})
        print(f"{tag} local_search_500+2s: {dt:.1f}s, {len(order_ls)-1} threads")

        # compute quality for every row
        for row in rows:
            row["mse"] = round(render_mse(row["order"], nails, target), 4)
            row["center_mse"] = round(center_mse(row["order"], nails, target), 4)
            print(f"  {row['config']}: mse={row['mse']}, center={row['center_mse']}")

        # cleanup for JSON
        for row in rows:
            row.pop("order")
            row.pop("final")
        results[tag] = rows

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "alternatives_experiment.json").write_text(json.dumps(results, indent=1))

    # chart
    configs = [r["config"] for r in results["male"]]
    x = np.arange(len(configs))
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    for ax, metric, title in (
        (axes[0], "mse", "Global MSE (less is better)"),
        (axes[1], "center_mse", "Center MSE (importance zone)"),
        (axes[2], "time_s", "Time (s)"),
    ):
        width = 0.35
        for k, tag in enumerate(results):
            vals = [next(r[metric] for r in results[tag] if r["config"] == c) for c in configs]
            ax.bar(x + (k - 0.5) * width, vals, width, label=tag)
        ax.set_xticks(x, configs, rotation=40, ha="right", fontsize=8)
        ax.set_title(title)
        ax.legend()
    fig.suptitle("Alternatives to greedy: importance, asymmetric, multi-scale, local search")
    fig.tight_layout()
    fig.savefig(OUT / "alternatives_experiment.png", dpi=150)
    print("chart: docs/img/alternatives_experiment.png")


if __name__ == "__main__":
    main()
