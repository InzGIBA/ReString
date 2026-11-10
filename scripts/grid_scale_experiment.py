"""Working grid scale experiment: does searching above 300 px pay?

The pipeline is tuned around a 300 x 300 working grid. This script searches
at 300, 450 and 600 (nail count held at 300 via the rect nail step), renders
every result at a fixed 1200 px export and compares quality against the time
cost. Working strength is swept {0.05, 0.1} so the verdict is about the grid,
not a mistuned constant: at 600 a 1-px line darkens 4x fewer pixels relative
to the canvas.

Verdict rules pre-registered in tasks/05-working-grid-scale.md: keep 300 if
the gain stays under 3 percent MSE or the time grows past 3x; otherwise a
`-g/--grid` flag lands.

    uv run python scripts/grid_scale_experiment.py
"""

import json
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from restring import _core
from restring.canvas import init_canvas, pull_order_to_array_bw
from restring.image_transformations import largest_square, resize
from restring.nails import create_rectangle_nail_positions

EXPORT = 1200
GRIDS = [300, 450, 600]
WORK_GRID = [0.05, 0.1]
BUDGETS = [500, 2000]
NAIL_TARGET = 300  # nails held fixed: step = grid * 4 / 300
EXPORT_STRENGTH = -0.05
OUT = Path(__file__).parent.parent / "docs" / "img"
PHOTOS = {
    "male": "tests/data/portrait_male.png",
    "female": "tests/data/portrait_female.png",
}


def timed(fn):
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


def main():
    results = {}

    for tag, path in PHOTOS.items():
        source = largest_square(_core.Image.load(path))
        ref_img = resize(source, (EXPORT, EXPORT))
        reference = ref_img.gray(0.9)
        ref_np = np.asarray(reference.tolist())
        rows = []

        for grid in GRIDS:
            img = resize(source, (grid, grid))
            target = img.gray(0.9)
            step = max(1, grid * 4 // NAIL_TARGET)
            nails = create_rectangle_nail_positions((grid, grid), step)
            nails_int = [(int(r), int(c)) for r, c in nails]

            for work in WORK_GRID:
                # cache build: an immediate break scans nothing
                _, cache_s = timed(lambda: _core.create_art(nails_int, target, -work, 0, None, True))
                for budget in BUDGETS:
                    (order, _), total_s = timed(
                        lambda: _core.create_art(nails_int, target, -work, budget, None, True))
                    search_s = total_s - cache_s
                    render = pull_order_to_array_bw(
                        [int(i) for i in order], init_canvas((EXPORT, EXPORT)), nails,
                        EXPORT_STRENGTH, shape=(grid, grid))
                    rendered = np.asarray(render.tolist())
                    mse = float(np.mean((rendered - ref_np) ** 2))
                    ssim = float(_core.ssim(render, reference))
                    rows.append({
                        "grid": grid, "work": work, "budget": budget,
                        "nails": len(nails_int),
                        "cache_s": round(cache_s, 3),
                        "search_s": round(search_s, 3),
                        "threads": len(order) - 1,
                        "mse": round(mse, 4), "ssim": round(ssim, 4),
                    })
                    print(f"{tag} grid{grid} work{work:g} n{budget}: mse={mse:.4f} "
                          f"ssim={ssim:.3f} cache={cache_s:.2f}s search={search_s:.2f}s")

        results[tag] = rows

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "grid_scale_experiment.json").write_text(json.dumps(results, indent=1))

    # chart: quality and time against the grid, per budget (work 0.05)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, (metric, title) in zip(axes, (("mse", "Render MSE at 1200 px export"),
                                          ("search_s", "Search time (s)"))):
        for budget in BUDGETS:
            for k, tag in enumerate(results):
                vals = [next(r[metric] for r in results[tag]
                             if r["grid"] == g and r["work"] == 0.05 and r["budget"] == budget)
                        for g in GRIDS]
                ax.plot(GRIDS, vals, marker="o", label=f"{tag}, {budget} pulls")
        ax.set_xticks(GRIDS)
        ax.set_xlabel("working grid (px)")
        ax.set_title(title)
        ax.legend()
    fig.suptitle("Working grid scale: quality and time at fixed 1200 px export")
    fig.tight_layout()
    fig.savefig(OUT / "grid_scale_experiment.png", dpi=150)
    print("chart: docs/img/grid_scale_experiment.png")

    # verdict check at the production working strength 0.05
    print("\nverdict check (keep 300 if gain <3% MSE or time >3x):")
    for tag, rows in results.items():
        for budget in BUDGETS:
            base = next(r for r in rows if r["grid"] == 300 and r["work"] == 0.05
                        and r["budget"] == budget)
            for grid in GRIDS[1:]:
                row = next(r for r in rows if r["grid"] == grid and r["work"] == 0.05
                           and r["budget"] == budget)
                gain = (base["mse"] - row["mse"]) / base["mse"] * 100
                time_mult = (row["cache_s"] + row["search_s"]) / (base["cache_s"] + base["search_s"])
                verdict = "ADOPT" if gain >= 3.0 and time_mult <= 3.0 else "keep 300"
                print(f"{tag} grid{grid} n{budget}: {gain:+.1f}% MSE, time x{time_mult:.1f} -> {verdict}")


if __name__ == "__main__":
    main()
