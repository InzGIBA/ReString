"""Lookahead experiment: beam width and 100-step receding horizon.

Compares greedy against beam search of several widths and against
receding-horizon search (MPC) with a 100-step rollout, plus greedy controls
with equal wall-clock budgets. Quality metric: render MSE at export
strength 0.05 on the two face fixtures, rectangle nails, budget 500 threads.

    uv run python scripts/beam_experiment.py
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
from restring.nails import create_rectangle_nail_positions

SIDE = 300
BUDGET = 500
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
    return target, nails


def quality(order, nails, target):
    render = _core.render_bw(list(order), nails, EXPORT, SIDE, SIDE, SIDE, SIDE, True)
    return _core.mse(render, target)


def run(label, fn):
    t0 = time.perf_counter()
    order, _ = fn()
    dt = time.perf_counter() - t0
    return {"config": label, "time_s": dt, "threads": len(order) - 1}


def main():
    results = {}
    for tag, path in PHOTOS.items():
        target, nails = setup(path)
        rows = []

        configs = [
            ("greedy_500", lambda: _core.create_art(nails, target, STRENGTH, BUDGET, None, True)),
            ("beam_5", lambda: _core.beam_search(nails, target, STRENGTH, BUDGET, None, True, 5)),
            ("beam_25", lambda: _core.beam_search(nails, target, STRENGTH, BUDGET, None, True, 25)),
            ("beam_100", lambda: _core.beam_search(nails, target, STRENGTH, BUDGET, None, True, 100)),
            ("beam_298", lambda: _core.beam_search(nails, target, STRENGTH, BUDGET, None, True, 298)),
            ("horizon100_b4", lambda: _core.horizon_search(nails, target, STRENGTH, BUDGET, 100, 4, None, True)),
            ("horizon100_b8", lambda: _core.horizon_search(nails, target, STRENGTH, BUDGET, 100, 8, None, True)),
        ]
        for label, fn in configs:
            row = run(label, fn)
            rows.append(row)
            print(f"{tag} {label}: {row['time_s']:.1f}s, {row['threads']} threads")

        # greedy controls at bigger budgets for the time-matched comparison
        controls = []
        for budget in (1000, 2000):
            row = run(f"greedy_{budget}", lambda b=budget: _core.create_art(nails, target, STRENGTH, b, None, True))
            rows.append(row)
            controls.append(budget)
            print(f"{tag} greedy_{budget}: {row['time_s']:.1f}s, {row['threads']} threads")

        # quality for every row
        for row in rows:
            order, _ = {
                "greedy": lambda b=500: _core.create_art(nails, target, STRENGTH, b, None, True),
            }.get(row["config"][:6], lambda: None)() if False else (None, None)
        # simpler: recompute quality per config label
        def order_for(cfg):
            if cfg.startswith("greedy_"):
                budget = int(cfg.split("_")[1])
                return _core.create_art(nails, target, STRENGTH, budget, None, True)[0]
            if cfg.startswith("beam_"):
                wdt = int(cfg.split("_")[1])
                return _core.beam_search(nails, target, STRENGTH, BUDGET, None, True, wdt)[0]
            if cfg.startswith("horizon100_b"):
                wdt = int(cfg.split("_b")[1])
                return _core.horizon_search(nails, target, STRENGTH, BUDGET, 100, wdt, None, True)[0]
            raise ValueError(cfg)

        for row in rows:
            row["mse"] = quality(order_for(row["config"]), nails, target)
            print(f"  {row['config']}: mse={row['mse']:.4f}")

        results[tag] = rows

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "beam_experiment.json").write_text(json.dumps(results, indent=1))

    # chart: MSE per config, both photos
    configs = [r["config"] for r in results["male"]]
    x = np.arange(len(configs))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    for ax, metric, label in ((ax1, "mse", "render MSE (меньше = лучше)"), (ax2, "time_s", "время, с")):
        width = 0.35
        for k, tag in enumerate(results):
            vals = [next(r[metric] for r in results[tag] if r["config"] == c) for c in configs]
            ax.bar(x + (k - 0.5) * width, vals, width, label=tag)
        ax.set_xticks(x, configs, rotation=30, ha="right")
        ax.set_title(label)
        ax.legend()
    fig.suptitle(f"Lookahead против жадного, rect 300 гвоздей, бюджет {BUDGET} нитей (greedy-контроли с большим бюджетом)")
    fig.tight_layout()
    fig.savefig(OUT / "beam_experiment.png", dpi=150)
    print("chart: docs/img/beam_experiment.png")


if __name__ == "__main__":
    main()
