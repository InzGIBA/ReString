"""Minimum chord distance experiment: does banning short pulls help?

Sweeps the --min-chord threshold on the face fixtures, rectangle nails at
step 4, budgets 500 and 2000 threads. Metric per threshold: global render
MSE, center MSE (central 50 percent box), run time and average chord length.
Adoption rule (pre-registered in tasks/02-min-chord-distance.md): a default
ships only if a threshold improves global MSE by 3 percent or more at an
equal budget; otherwise the flag ships with default off.

    uv run python scripts/min_chord_experiment.py
"""

import json
import math
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from restring import _core
from restring.image_transformations import largest_square, resize
from restring.nails import create_rectangle_nail_positions

SIDE = 300
OUT = Path(__file__).parent.parent / "docs" / "img"
PHOTOS = {
    "male": "tests/data/portrait_male.png",
    "female": "tests/data/portrait_female.png",
}
STRENGTH = -0.05
EXPORT = -0.05
THRESHOLDS = [None, 5.0, 10.0, 20.0, 30.0, 100.0, 200.0, 250.0, 300.0]
BUDGETS = [500, 2000]


def setup(path):
    img = resize(largest_square(_core.Image.load(path)), (SIDE, SIDE))
    target = img.gray(0.9)
    nails = create_rectangle_nail_positions((SIDE, SIDE), nail_step=4)
    return img, target, nails


def render(order, nails):
    return _core.render_bw(list(order), nails, EXPORT, SIDE, SIDE, SIDE, SIDE, True)


def render_mse(order, nails, target):
    return _core.mse(render(order, nails), target)


def center_mse(order, nails, target):
    """MSE inside the central 50% box (the face region)."""
    r = np.asarray(render(order, nails).tolist())
    t = np.asarray(target.tolist())
    box = (slice(SIDE // 4, 3 * SIDE // 4), slice(SIDE // 4, 3 * SIDE // 4))
    return float(np.mean((r[box] - t[box]) ** 2))


def avg_chord_length(order, nails):
    pts = [nails[j] for j in order]
    d = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    return sum(d) / len(d)


def main():
    results = {}

    for tag, path in PHOTOS.items():
        _, target, nails = setup(path)
        rows = []

        for budget in BUDGETS:
            for thr in THRESHOLDS:
                label = f"mc{thr:g}_{budget}" if thr is not None else f"base_{budget}"
                t0 = time.perf_counter()
                order, _ = _core.create_art(nails, target, STRENGTH, budget, None, True,
                                            None, thr)
                dt = time.perf_counter() - t0
                row = {
                    "config": label,
                    "time_s": round(dt, 2),
                    "threads": len(order) - 1,
                    "avg_chord_px": round(avg_chord_length(order, nails), 1),
                    "mse": round(render_mse(order, nails, target), 4),
                    "center_mse": round(center_mse(order, nails, target), 4),
                }
                rows.append(row)
                print(f"{tag} {label}: mse={row['mse']} center={row['center_mse']} "
                      f"chord={row['avg_chord_px']}px {row['time_s']}s")

        results[tag] = rows

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "min_chord_experiment.json").write_text(json.dumps(results, indent=1))

    # chart: global and center MSE against the threshold, per fixture and budget
    thresholds_plot = [t if t is not None else 0 for t in THRESHOLDS]  # 0 = unfiltered
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, metric, title in (
        (axes[0], "mse", "Global MSE (less is better)"),
        (axes[1], "center_mse", "Center MSE (face box)"),
    ):
        for budget in BUDGETS:
            for k, tag in enumerate(results):
                vals = [next(r[metric] for r in results[tag]
                             if r["config"] == (f"base_{budget}" if t == 0 else f"mc{t:g}_{budget}"))
                        for t in thresholds_plot]
                ax.plot(thresholds_plot, vals, marker="o",
                        label=f"{tag}, {budget} threads")
        ax.set_xticks(thresholds_plot)
        ax.set_xlabel("min chord (px, 0 = off)")
        ax.set_title(title)
        ax.legend(fontsize=8)
    fig.suptitle("Minimum chord distance: MSE against threshold")
    fig.tight_layout()
    fig.savefig(OUT / "min_chord_experiment.png", dpi=150)
    print("chart: docs/img/min_chord_experiment.png")

    # adoption check: >=3% global MSE gain at an equal budget?
    print("\nadoption check (needs >=3% global MSE gain at equal budget):")
    for tag, rows in results.items():
        for budget in BUDGETS:
            base = next(r for r in rows if r["config"] == f"base_{budget}")
            for r in rows:
                if r["config"].endswith(f"_{budget}") and r["config"] != f"base_{budget}":
                    gain = (base["mse"] - r["mse"]) / base["mse"] * 100
                    verdict = "ADOPT" if gain >= 3.0 else "no"
                    print(f"{tag} {r['config']}: {gain:+.1f}% global MSE vs baseline -> {verdict}")


if __name__ == "__main__":
    main()
