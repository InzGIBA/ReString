"""Thread model experiment: how much quality does thread thickness buy?

Pre-registered question :: at what
thread width does the thick-render MSE at N pulls match the hairline MSE at
2N pulls? Everything renders at a fixed 1200 px export, physical board
400 mm, thread widths 0.15 / 0.2 / 0.3 mm, both portrait fixtures, rectangle
nails at step 4, working strength 0.05.

    uv run python scripts/thread_model_experiment.py
"""

import json
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
CANVAS_MM = 400.0
WIDTHS_MM = [0.15, 0.2, 0.3]
BUDGETS = [500, 2000]
STRENGTH = -0.05
OUT = Path(__file__).parent.parent / "docs" / "img"
PHOTOS = {
    "male": "tests/data/portrait_male.png",
    "female": "tests/data/portrait_female.png",
}


def render_mse(order, nails, reference, thread_px):
    canvas = init_canvas((EXPORT, EXPORT))
    if thread_px is None:
        img = pull_order_to_array_bw(order, canvas, nails, STRENGTH, shape=(300, 300))
    else:
        img = pull_order_to_array_bw(order, canvas, nails, STRENGTH, shape=(300, 300),
                                     thread_px=thread_px)
    rendered = np.asarray(img.tolist())
    return float(np.mean((rendered - reference) ** 2))


def main():
    results = {}

    for tag, path in PHOTOS.items():
        source = largest_square(_core.Image.load(path))
        ref_img = resize(source, (EXPORT, EXPORT))
        reference = ref_img.gray(0.9)
        ref_np = np.asarray(reference.tolist())
        nails = create_rectangle_nail_positions((300, 300), nail_step=4)
        target = resize(source, (300, 300)).gray(0.9)

        # one search, prefixes give the budgets (greedy is prefix-stable)
        order, _ = _core.create_art(nails, target, STRENGTH, 2000, None, True)
        order = [int(i) for i in order]
        rows = []

        for n in BUDGETS:
            prefix = order[: n + 1]
            double = min(2 * n, len(order) - 1)
            double_prefix = order[: double + 1]

            hairline_n = render_mse(prefix, nails, ref_np, None)
            hairline_2n = render_mse(double_prefix, nails, ref_np, None)
            rows.append({"config": f"hairline_{n}", "width_mm": 0.0, "pulls": n,
                         "mse": round(hairline_n, 4)})
            rows.append({"config": f"hairline_{double}", "width_mm": 0.0, "pulls": double,
                         "mse": round(hairline_2n, 4)})
            print(f"{tag} hairline {n}: mse={hairline_n:.4f}")
            print(f"{tag} hairline {double}: mse={hairline_2n:.4f}")

            for width in WIDTHS_MM:
                thread_px = width * EXPORT / CANVAS_MM
                mse = render_mse(prefix, nails, ref_np, thread_px)
                rows.append({"config": f"thick_{width:g}mm_{n}", "width_mm": width,
                             "pulls": n, "thread_px": round(thread_px, 2),
                             "mse": round(mse, 4)})
                print(f"{tag} thick {width}mm ({thread_px:.2f} px) at {n}: mse={mse:.4f}")

        results[tag] = rows

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "thread_model_experiment.json").write_text(json.dumps(results, indent=1))

    # chart: MSE against thread width at each budget, hairline reference lines
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, budget in zip(axes, BUDGETS):
        for tag, rows in results.items():
            vals = [next(r["mse"] for r in rows if r["config"] == f"thick_{w:g}mm_{budget}")
                    for w in WIDTHS_MM]
            ax.plot(WIDTHS_MM, vals, marker="o", label=f"{tag}, thick at {budget}")
            double = min(2 * budget, max(r["pulls"] for r in rows
                                         if r["config"].startswith("hairline")))
            hairline_double = next(r["mse"] for r in rows if r["config"] == f"hairline_{double}")
            ax.axhline(hairline_double, linestyle=":", alpha=0.6,
                       label=f"{tag}, hairline at {double}")
        ax.set_xticks(WIDTHS_MM, [f"{w:g} mm" for w in WIDTHS_MM])
        ax.set_xlabel("thread width (thread_px at export: 0.45 / 0.6 / 0.9)")
        ax.set_title(f"MSE at {budget} pulls")
        ax.legend(fontsize=8)
    fig.suptitle("Thread thickness against the hairline: quality per pull budget")
    fig.tight_layout()
    fig.savefig(OUT / "thread_model_experiment.png", dpi=150)
    print("chart: docs/img/thread_model_experiment.png")

    # pre-registered question: width where thick(N) matches hairline(2N)
    print("\nmatch point (thick at N vs hairline at 2N):")
    for tag, rows in results.items():
        for n in BUDGETS:
            double = min(2 * n, max(r["pulls"] for r in rows if r["config"].startswith("hairline")))
            hairline_double = next(r["mse"] for r in rows if r["config"] == f"hairline_{double}")
            thick_rows = [r for r in rows if r["config"].startswith("thick_") and r["pulls"] == n]
            best = min(thick_rows, key=lambda r: abs(r["mse"] - hairline_double))
            print(f"{tag} N={n}: hairline {double} mse={hairline_double:.4f}; nearest thick "
                  f"{best['width_mm']}mm ({best['thread_px']} px) mse={best['mse']:.4f}")


if __name__ == "__main__":
    main()
