"""Adaptive nail placement experiment: gradient-scored vs uniform perimeters.

Question: does
placing the same nail count where the Sobel gradient is dense beat uniform
perimeters? Adopt (--adaptive, default off) only on a 3 percent or better
global MSE or an 8 percent or better center MSE improvement at equal nail
count on both fixtures; otherwise the negative closes the question.

    uv run python scripts/adaptive_nails_experiment.py
"""

import json
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from restring import _core
from restring import _core as core
from restring.adaptive import adaptive_perimeter_nails, uniform_perimeter_nails
from restring.image_transformations import largest_square, resize

SIDE = 300
EXPORT = 600
COUNTS = [211, 298, 422]
BUDGETS = [500, 2000]
LAYOUTS = ["circle", "rect"]
STRENGTH = -0.05
OUT = Path(__file__).parent.parent / "docs" / "img"
PHOTOS = {
    "male": "tests/data/portrait_male.png",
    "female": "tests/data/portrait_female.png",
}


def render_mse(order, nails, reference_np, box=None):
    img = _core.render_bw(list(order), nails, STRENGTH, SIDE, SIDE, EXPORT, EXPORT, True)
    rendered = np.asarray(img.tolist())
    diff = (rendered - reference_np) ** 2
    if box is not None:
        r0, r1, c0, c1 = box
        return float(np.mean(diff[r0:r1, c0:c1]))
    return float(np.mean(diff))


def main():
    results = {}

    for tag, path in PHOTOS.items():
        img = resize(largest_square(core.Image.load(path)), (SIDE, SIDE))
        target = img.gray(0.9)
        gradient = core.gradient_magnitude(img)
        reference = resize(largest_square(core.Image.load(path)), (EXPORT, EXPORT)).gray(0.9)
        ref_np = np.asarray(reference.tolist())
        box = (EXPORT // 4, 3 * EXPORT // 4, EXPORT // 4, 3 * EXPORT // 4)  # central 50 percent

        rows = []
        for layout in LAYOUTS:
            for count in COUNTS:
                uniform = uniform_perimeter_nails((SIDE, SIDE), count, layout)
                adaptive = adaptive_perimeter_nails((SIDE, SIDE), count, gradient, layout)
                assert len(uniform) == count and len(adaptive) == count
                for budget in BUDGETS:
                    t0 = time.perf_counter()
                    order_u, _ = _core.create_art(uniform, target, STRENGTH, budget, None, True)
                    t_uniform = time.perf_counter() - t0
                    t0 = time.perf_counter()
                    order_a, _ = _core.create_art(adaptive, target, STRENGTH, budget, None, True)
                    t_adaptive = time.perf_counter() - t0

                    mse_u = render_mse(order_u, uniform, ref_np)
                    mse_a = render_mse(order_a, adaptive, ref_np)
                    center_u = render_mse(order_u, uniform, ref_np, box)
                    center_a = render_mse(order_a, adaptive, ref_np, box)
                    rows.append({
                        "layout": layout, "count": count, "budget": budget,
                        "mse_uniform": round(mse_u, 4), "mse_adaptive": round(mse_a, 4),
                        "center_uniform": round(center_u, 4), "center_adaptive": round(center_a, 4),
                        "time_uniform_s": round(t_uniform, 2), "time_adaptive_s": round(t_adaptive, 2),
                    })
                    print(f"{tag} {layout} n={count} budget={budget}: uniform={mse_u:.4f} "
                          f"adaptive={mse_a:.4f} | center {center_u:.4f} vs {center_a:.4f}")

        results[tag] = rows

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "adaptive_nails_experiment.json").write_text(json.dumps(results, indent=1))

    # chart: adaptive/uniform MSE ratio per count and budget
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, layout in zip(axes, LAYOUTS):
        labels = [f"n={c}\n{b}" for c in COUNTS for b in BUDGETS]
        x = np.arange(len(labels))
        for k, tag in enumerate(results):
            ratios = [next(r["mse_adaptive"] / r["mse_uniform"] for r in results[tag]
                           if r["layout"] == layout and r["count"] == c and r["budget"] == b)
                      for c in COUNTS for b in BUDGETS]
            ax.bar(x + (k - 0.5) * 0.35, ratios, 0.35, label=tag)
        ax.axhline(1.0, linestyle="--", alpha=0.5)
        ax.set_xticks(x, labels, fontsize=8)
        ax.set_ylabel("adaptive / uniform global MSE")
        ax.set_title(layout)
        ax.legend(fontsize=8)
    fig.suptitle("Adaptive nail placement against uniform perimeters at equal nail count")
    fig.tight_layout()
    fig.savefig(OUT / "adaptive_nails_experiment.png", dpi=150)
    print("chart: docs/img/adaptive_nails_experiment.png")

    # pre-registered verdict: adopt only on >=3% global or >=8% center gain on
    # both fixtures (every layout, count and budget)
    print("\nverdict (adopt needs >=3% global or >=8% center MSE gain on both fixtures, all facets):")
    all_global, all_center = [], []
    for tag, rows in results.items():
        for r in rows:
            global_gain = (r["mse_uniform"] - r["mse_adaptive"]) / r["mse_uniform"] * 100
            center_gain = (r["center_uniform"] - r["center_adaptive"]) / r["center_uniform"] * 100
            all_global.append(global_gain)
            all_center.append(center_gain)
            print(f"{tag} {r['layout']} n={r['count']} budget={r['budget']}: "
                  f"global {global_gain:+.1f}%, center {center_gain:+.1f}%")
    print(f"\nsummary: global gain min {min(all_global):+.1f}%, max {max(all_global):+.1f}%; "
          f"center gain min {min(all_center):+.1f}%, max {max(all_center):+.1f}%")


if __name__ == "__main__":
    main()
