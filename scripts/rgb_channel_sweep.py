"""RGB per-channel sweep: working strength, budget split, export, stopping.

The RGB pipeline never got measured defaults: all three channels share one
working strength (0.1), equal budgets, and stop at the same iteration count
with the shortest channels padded by repeating their last nail. This script
sweeps all four unknowns on the portrait fixtures and reports global color
MSE, per-channel MSE, grayscale SSIM and the padded-pull share.

Verdict rules are pre-registered: adopt a
pipeline change only on >=5 percent global color MSE improvement on both
fixtures; record negative results with the same care.

    uv run python scripts/rgb_channel_sweep.py
"""

import json
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from restring import _core
from restring.canvas import init_canvas, pull_order_to_array_rgb
from restring.image_transformations import largest_square, resize
from restring.nails import create_rectangle_nail_positions

SIDE = 300
OUT = Path(__file__).parent.parent / "docs" / "img"
PHOTOS = {
    "male": "tests/data/portrait_male.png",
    "female": "tests/data/portrait_female.png",
}
BUDGET = 2000
WORK_GRID = [0.03, 0.05, 0.1, 0.15]  # working strength, all channels; 0.1 = current default
EXPORT_GRID = 0.1
AUTO_K = 104.0  # fitted constant (scripts/fit_export_strength.py)
EXPORT_FLOOR, EXPORT_CEIL = 0.03, 0.2


def setup(path):
    img = resize(largest_square(_core.Image.load(path)), (SIDE, SIDE))
    nails = create_rectangle_nail_positions((SIDE, SIDE), nail_step=4)
    return img, nails


def channel_targets(img):
    return [img.channel(c) for c in range(3)]


def gray_target(img):
    return img.gray(0.9)


def run_orders(targets, nails, work, budgets, stop):
    """One greedy run per channel at the given working strength and budgets."""
    orders = []
    for target, budget in zip(targets, budgets):
        limit = None if stop == "exhaustion" else budget
        order, _ = _core.create_art(nails, target, -work, limit, None, True)
        orders.append([int(i) for i in order])
    return orders


def resolve_auto(pull_count):
    return min(EXPORT_CEIL, max(EXPORT_FLOOR, AUTO_K / pull_count))


def render(orders, nails, exports):
    padded = max(len(o) for o in orders)
    filled = [o + [o[-1]] * (padded - len(o)) for o in orders]
    img = pull_order_to_array_rgb(
        filled, init_canvas((SIDE, SIDE, 3)), nails, strength=exports,
        shape=(SIDE, SIDE))
    return img


def main():
    results = {}

    for tag, path in PHOTOS.items():
        img, nails = setup(path)
        targets = channel_targets(img)
        target_gray = gray_target(img)
        ref_rgb = np.asarray(img.tolist())
        rows = []

        # variance of each channel target drives the proportional budget split
        variances = [float(np.var(np.asarray(t.tolist()))) for t in targets]
        var_sum = sum(variances)
        split_budgets = [max(1, round(BUDGET * v / var_sum)) for v in variances]

        facets = []
        # A: working strength sweep, equal budgets, auto export, budgeted
        for work in WORK_GRID:
            facets.append({
                "label": f"work{work:g}", "work": work, "budgets": [BUDGET] * 3,
                "stop": "budgeted", "export": "auto",
            })
        # B: equal vs variance-proportional budgets (at the default work 0.1)
        facets.append({
            "label": "budget_var", "work": 0.1, "budgets": split_budgets,
            "stop": "budgeted", "export": "auto",
        })
        # C: exhaustion instead of the budget (at the default work 0.1)
        facets.append({
            "label": "stop_exhaust", "work": 0.1, "budgets": [BUDGET] * 3,
            "stop": "exhaustion", "export": "auto",
        })
        # D: fixed export 0.1 vs auto (same orders as the baseline facet)
        facets.append({
            "label": "export_fixed", "work": 0.1, "budgets": [BUDGET] * 3,
            "stop": "budgeted", "export": "fixed",
        })

        cached_orders = {}
        for facet in facets:
            key = (facet["work"], tuple(facet["budgets"]), facet["stop"])
            if key not in cached_orders:
                t0 = time.perf_counter()
                cached_orders[key] = run_orders(targets, nails, facet["work"],
                                                facet["budgets"], facet["stop"])
                facet["run_time_s"] = round(time.perf_counter() - t0, 2)
            orders = cached_orders[key]

            padded = max(len(o) for o in orders)
            pad_share = sum(padded - len(o) for o in orders) / (3 * padded)
            # non-WB renders darken a white canvas: the export strength is negative
            if facet["export"] == "fixed":
                exports = [-EXPORT_GRID] * 3
            else:
                exports = [-resolve_auto(len(o) - 1) for o in orders]

            render_img = render(orders, nails, exports)
            rendered = np.asarray(render_img.tolist())
            global_mse = float(np.mean((rendered - ref_rgb) ** 2))
            per_channel = [float(np.mean((rendered[:, :, c] - ref_rgb[:, :, c]) ** 2))
                           for c in range(3)]
            gray_render = render_img.gray(1.0)
            ssim_val = float(_core.ssim(gray_render, target_gray))

            rows.append({
                "config": facet["label"],
                "work": facet["work"],
                "budgets": facet["budgets"],
                "stop": facet["stop"],
                "export": facet["export"],
                "pulls_per_channel": [len(o) - 1 for o in orders],
                "pad_share": round(pad_share, 4),
                "time_s": facet.get("run_time_s"),
                "global_mse": round(global_mse, 4),
                "channel_mse": [round(v, 4) for v in per_channel],
                "ssim": round(ssim_val, 4),
            })
            print(f"{tag} {facet['label']}: mse={global_mse:.4f} "
                  f"ssim={ssim_val:.3f} pad={pad_share:.3f}")

        results[tag] = {"variances": [round(v, 4) for v in variances], "rows": rows}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "rgb_channel_sweep.json").write_text(json.dumps(results, indent=1))

    # chart: per-facet global MSE and SSIM against the work0.1 baseline
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, metric, title in ((axes[0], "global_mse", "Global color MSE"),
                              (axes[1], "ssim", "Grayscale SSIM")):
        labels = [r["config"] for r in results["male"]["rows"]]
        x = np.arange(len(labels))
        for k, tag in enumerate(results):
            vals = [next(r[metric] for r in results[tag]["rows"] if r["config"] == c)
                    for c in labels]
            ax.bar(x + (k - 0.5) * 0.35, vals, 0.35, label=tag)
        ax.set_xticks(x, labels, rotation=30, ha="right", fontsize=8)
        ax.set_title(title)
        ax.legend()
    fig.suptitle("RGB channel sweep: working strength, budgets, stopping, export")
    fig.tight_layout()
    fig.savefig(OUT / "rgb_channel_sweep.png", dpi=150)
    print("chart: docs/img/rgb_channel_sweep.png")

    # adoption check against the work0.1 baseline (pre-registered: >=5% on both)
    print("\nadoption check (needs >=5% global MSE gain on both fixtures):")
    for tag, data in results.items():
        base = next(r for r in data["rows"] if r["config"] == "work0.1")
        for r in data["rows"]:
            if r["config"] == "work0.1":
                continue
            gain = (base["global_mse"] - r["global_mse"]) / base["global_mse"] * 100
            print(f"{tag} {r['config']}: {gain:+.1f}% global MSE vs baseline")


if __name__ == "__main__":
    main()
