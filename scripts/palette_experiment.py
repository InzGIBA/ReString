"""Palette experiment: rgb against cmy, cmyk and the DMC starter set.

Equal total pull budgets (3000 split across threads) on the portrait
fixtures. Metrics: color MSE at the 600 px export, per-thread pull counts,
search time. Pre-registered bar: a
palette ships as recommended only on a 5 percent or better color MSE
improvement over rgb at an equal budget.

    uv run python scripts/palette_experiment.py
"""

import json
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from restring import _core, palettes
from restring.canvas import init_canvas, pull_order_to_array_palette
from restring.generator import separate_targets
from restring.image_transformations import largest_square, resize
from restring.nails import create_rectangle_nail_positions

TOTAL_BUDGET = 3000
EXPORT = 600
STRENGTH = -0.05
OUT = Path(__file__).parent.parent / "docs" / "img"
DMC = Path(__file__).parent.parent / "examples" / "palettes" / "dmc-starter.json"
PHOTOS = {
    "male": "tests/data/portrait_male.png",
    "female": "tests/data/portrait_female.png",
}


def run_palette(target, nails, threads, total_budget):
    """One greedy run per thread, orders padded and interleaved (the
    generate_palette structure, budgeted explicitly)."""
    budgets = [max(1, total_budget // len(threads))] * len(threads)
    t0 = time.perf_counter()
    targets = separate_targets(target, threads, (300, 300))
    orders = []
    for budget, thread_target in zip(budgets, targets):
        order, _ = _core.create_art(nails, thread_target, STRENGTH, budget, None, True)
        orders.append([int(i) for i in order])
    search_s = time.perf_counter() - t0
    pulls = [len(o) - 1 for o in orders]
    padded = max(len(o) for o in orders)
    orders = [o + [o[-1]] * (padded - len(o)) for o in orders]
    img = pull_order_to_array_palette(orders, init_canvas((EXPORT, EXPORT, 3)), nails,
                                      [t.rgb for t in threads], STRENGTH, shape=(300, 300))
    return img, pulls, search_s


def main():
    results = {}
    # the 20-thread DMC starter exceeds the CLI cap of 8 deliberately: this
    # script measures what large palettes would buy before any cap debate
    dmc = [palettes.ThreadColor(e["name"], tuple(e["rgb"]))
           for e in json.loads(DMC.read_text()) if "rgb" in e]
    palettes_to_test = {
        "rgb": palettes.builtin_palette("rgb"),
        "cmy": palettes.builtin_palette("cmy"),
        "cmyk": palettes.builtin_palette("cmyk"),
        "dmc-starter": dmc,
    }

    for tag, path in PHOTOS.items():
        img = resize(largest_square(_core.Image.load(path)), (300, 300))
        reference = resize(largest_square(_core.Image.load(path)), (EXPORT, EXPORT))
        ref_np = np.asarray(reference.tolist())
        nails = create_rectangle_nail_positions((300, 300), nail_step=4)
        # the target for separation is the RGB image itself; gray(0.9) is unused here
        rows = []

        for name, threads in palettes_to_test.items():
            img_out, pulls, search_s = run_palette(img, nails, threads, TOTAL_BUDGET)
            rendered = np.asarray(img_out.tolist())
            mse = float(np.mean((rendered - ref_np) ** 2))
            rows.append({
                "palette": name, "k": len(threads),
                "pulls_per_thread": pulls, "search_s": round(search_s, 2),
                "mse": round(mse, 4),
            })
            print(f"{tag} {name} (k={len(threads)}): mse={mse:.4f} pulls={pulls} {search_s:.1f}s")

        results[tag] = rows

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "palette_experiment.json").write_text(json.dumps(results, indent=1))

    # chart: color MSE per palette
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    names = list(palettes_to_test)
    for ax, tag in zip(axes, results):
        vals = [next(r["mse"] for r in results[tag] if r["palette"] == n) for n in names]
        ax.bar(names, vals, color=["#c22", "#2aa", "#a6a", "#986"])
        ax.set_title(f"{tag}: color MSE (less is better)")
        ax.set_ylabel("MSE at 600 px")
        for i, v in enumerate(vals):
            ax.text(i, v, f"{v:.4f}", ha="center", va="bottom", fontsize=8)
    fig.suptitle(f"Palette comparison at an equal total budget of {TOTAL_BUDGET} pulls")
    fig.tight_layout()
    fig.savefig(OUT / "palette_experiment.png", dpi=150)
    print("chart: docs/img/palette_experiment.png")

    # pre-registered bar: >=5% color MSE improvement over rgb at equal budget
    print("\nadoption check (needs >=5% color MSE gain over rgb on both fixtures):")
    for tag, rows in results.items():
        base = next(r for r in rows if r["palette"] == "rgb")
        for r in rows:
            if r["palette"] == "rgb":
                continue
            gain = (base["mse"] - r["mse"]) / base["mse"] * 100
            verdict = "RECOMMEND" if gain >= 5.0 else "no"
            print(f"{tag} {r['palette']}: {gain:+.1f}% vs rgb -> {verdict}")


if __name__ == "__main__":
    main()
