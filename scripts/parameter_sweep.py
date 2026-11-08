"""Parameter tuning sweeps for ReString (B/W pipeline, real portrait fixtures).

One sweep per CLI knob, each measuring render MSE against the canonical
reference rgb2gray(img)*0.9 (the generator's internal target), plus timing.
Charts + raw JSON land in docs/img/params/. The greedy sequence is
prefix-deterministic, so pull-count sweeps reuse one long run per photo.

Usage (each sweep is independently runnable):
    uv run python scripts/parameter_sweep.py --sweep pulls
    uv run python scripts/parameter_sweep.py --sweep nails
    uv run python scripts/parameter_sweep.py --sweep random
    uv run python scripts/parameter_sweep.py --sweep dims
    uv run python scripts/parameter_sweep.py --sweep layout
    uv run python scripts/parameter_sweep.py --sweep darken
"""

import argparse
import json
import logging
import time
from pathlib import Path

import matplotlib
import numpy as np
from PIL import Image

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from restring.canvas import init_canvas, pull_order_to_array_bw  # noqa: E402
from restring.generator import create_art  # noqa: E402
from restring.image_transformations import largest_square, resize, rgb2gray  # noqa: E402
from restring.nails import (  # noqa: E402
    create_circle_nail_positions,
    create_rectangle_nail_positions,
    scale_nails,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("sweep")

SIDE = 300
OUT = Path(__file__).parent.parent / "docs" / "img" / "params"
PHOTOS = {
    "male": "tests/data/portrait_male.png",
    "female": "tests/data/portrait_female.png",
}
PULL_SNAPSHOTS = [100, 300, 500, 1000, 1500, 2000, 3000, 4000, 5000, 6000, 7000]
STRENGTHS = [0.025, 0.05, 0.075, 0.1, 0.15, 0.2]


def mse(a, b):
    return float(np.mean((a - b) ** 2))


def load_photo(path):
    img = np.asarray(Image.open(path).convert("RGB"), dtype=float) / 255
    img = resize(largest_square(img), (SIDE, SIDE))
    return rgb2gray(img) * 0.9  # canonical reference = generator's internal target


def render(order, nails, out_side, strength):
    """Render a pull order at an arbitrary output resolution, as generate_bw does."""
    canvas = init_canvas((out_side, out_side))
    scaled = scale_nails(out_side / SIDE, out_side / SIDE, nails) if out_side != SIDE else nails
    return pull_order_to_array_bw(order, canvas, scaled, -strength)


def savefig(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=150)
    plt.close(fig)


def dump(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / f"{name}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)


def sweep_pulls():
    """-l / -s: one 7000-iteration greedy run per photo, render prefixes per strength."""
    results = {}
    for tag, path in PHOTOS.items():
        ref = load_photo(path)
        nails = create_circle_nail_positions((SIDE, SIDE), nail_step=4)
        t0 = time.perf_counter()
        order = create_art(nails, ref, init_canvas((SIDE, SIDE)), -0.05, i_limit=7000)
        elapsed = time.perf_counter() - t0
        ns = [n for n in PULL_SNAPSHOTS if n < len(order)]
        results[tag] = {"threads": len(order) - 1, "greedy_time_s": elapsed, "curves": {}}
        for s in STRENGTHS:
            results[tag]["curves"][str(s)] = [
                {"n": n, "mse": mse(render(order[: n + 1], nails, SIDE, s), ref)} for n in ns
            ]
        print(f"pulls {tag}: {len(order)-1} threads in {elapsed:.0f}s")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, (tag, r) in zip(axes, results.items()):
        for s in STRENGTHS:
            rows = r["curves"][str(s)]
            ax.plot([x["n"] for x in rows], [x["mse"] for x in rows], "o-", label=f"s={s}")
        ax.set_xscale("log")
        ax.set_title(f"{tag}: MSE vs число нитей")
        ax.set_xlabel("нитей (лог.)")
        ax.set_ylabel("MSE")
        ax.legend(fontsize=8)
    savefig(fig, "pulls_mse.png")

    # best strength per pull count + achieved mse
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for tag, r in results.items():
        ns = [x["n"] for x in r["curves"]["0.05"]]
        best_s = []
        for i in range(len(ns)):
            mses = {s: r["curves"][str(s)][i]["mse"] for s in STRENGTHS}
            best_s.append(float(min(mses, key=mses.get)))
        ax.plot(ns, best_s, "o-", label=f"{tag}: оптимальный -s")
    ax.set_xscale("log")
    ax.set_xlabel("число нитей (лог.)")
    ax.set_ylabel("оптимальная сила экспорта")
    ax.set_title("Оптимальный -s в зависимости от бюджета нитей")
    ax.legend()
    savefig(fig, "pulls_best_s.png")
    dump("pulls", results)


def sweep_nails():
    """-n: nail step sweep at a fixed iteration budget, equal-thread comparison."""
    steps = [1, 2, 3, 4, 6, 8]
    budget = 2000
    results = {}
    for tag, path in PHOTOS.items():
        ref = load_photo(path)
        rows = []
        for step in steps:
            nails = create_circle_nail_positions((SIDE, SIDE), nail_step=step)
            t0 = time.perf_counter()
            order = create_art(nails, ref, init_canvas((SIDE, SIDE)), -0.05, i_limit=budget)
            dt = time.perf_counter() - t0
            # equal-threads comparison at the minimum thread count across steps
            rows.append({
                "step": step,
                "nails": len(nails),
                "threads": len(order) - 1,
                "time_s": dt,
                "mse": mse(render(order, nails, SIDE, 0.05), ref),
            })
            print(f"nails {tag} step={step}: {len(nails)} nails, {len(order)-1} threads, {dt:.0f}s")
        results[tag] = rows

    fig, ax = plt.subplots(figsize=(8, 5))
    ax2 = ax.twinx()
    for tag, rows in results.items():
        ax.plot([r["nails"] for r in rows], [r["mse"] for r in rows], "o-", label=f"{tag}: MSE")
        ax2.plot([r["nails"] for r in rows], [r["time_s"] for r in rows], "s--", alpha=0.6,
                 label=f"{tag}: время {budget} итераций")
    ax.set_xlabel("число гвоздей (-n обратно пропорционален)")
    ax.set_ylabel("MSE (сила 0.05)")
    ax2.set_ylabel("секунды")
    ax.set_title(f"Качество и время vs число гвоздей ({budget} итераций)")
    ax.legend(loc="upper left", fontsize=8)
    ax2.legend(loc="upper right", fontsize=8)
    savefig(fig, "nails.png")
    dump("nails", results)


def sweep_random():
    """-r: random-nail subset size vs quality and speed."""
    subsets = [None, 25, 50, 100, 150, 211]
    budget = 2000
    results = {}
    for tag, path in PHOTOS.items():
        ref = load_photo(path)
        nails = create_circle_nail_positions((SIDE, SIDE), nail_step=4)
        rows = []
        for k in subsets:
            t0 = time.perf_counter()
            order = create_art(nails, ref, init_canvas((SIDE, SIDE)), -0.05,
                               i_limit=budget, random_nails=k)
            dt = time.perf_counter() - t0
            rows.append({
                "subset": k, "time_s": dt, "threads": len(order) - 1,
                "mse": mse(render(order, nails, SIDE, 0.05), ref),
            })
            print(f"random {tag} k={k}: {dt:.1f}s")
        results[tag] = rows

    fig, ax = plt.subplots(figsize=(8, 5))
    ax2 = ax.twinx()
    for tag, rows in results.items():
        xs = [211 if r["subset"] is None else r["subset"] for r in rows]
        ax.plot(xs, [r["mse"] for r in rows], "o-", label=f"{tag}: MSE")
        ax2.plot(xs, [r["time_s"] for r in rows], "s--", alpha=0.6, label=f"{tag}: время")
    ax.set_xlabel("размер случайной подвыборки гвоздей (-r)")
    ax.set_ylabel("MSE (сила 0.05)")
    ax2.set_ylabel("секунды")
    ax.set_title(f"-r: качество/скорость vs подвыборка ({budget} итераций, 211 гвоздей)")
    ax.legend(loc="center left", fontsize=8)
    ax2.legend(loc="center right", fontsize=8)
    savefig(fig, "random.png")
    dump("random", results)


def sweep_dims():
    """-d: export resolution renders from the existing 7000-pull orders (cheap)."""
    dims = [100, 200, 300, 450, 600]
    results = {}
    for tag, path in PHOTOS.items():
        ref = load_photo(path)
        nails = create_circle_nail_positions((SIDE, SIDE), nail_step=4)
        order = create_art(nails, ref, init_canvas((SIDE, SIDE)), -0.05, i_limit=3000)
        rows = []
        for d in dims:
            rendered = render(order, nails, d, 0.05)
            ref_d = resize(ref, (d, d))
            rows.append({"d": d, "mse": mse(rendered, ref_d)})
        results[tag] = rows
        print(f"dims {tag}: done")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for tag, rows in results.items():
        ax.plot([r["d"] for r in rows], [r["mse"] for r in rows], "o-", label=tag)
    ax.set_xlabel("размер экспорта -d")
    ax.set_ylabel("MSE против эталона в этом разрешении")
    ax.set_title("-d: разрешение экспорта (3000 нитей, сила 0.05)")
    ax.legend()
    savefig(fig, "dims.png")
    dump("dims", results)


def sweep_layout():
    """--rect vs circle at comparable nail counts."""
    budget = 2000
    results = {}
    for tag, path in PHOTOS.items():
        ref = load_photo(path)
        rows = []
        for layout in ("circle", "rect"):
            nails = (create_circle_nail_positions((SIDE, SIDE), nail_step=4) if layout == "circle"
                     else create_rectangle_nail_positions((SIDE, SIDE), nail_step=4))
            t0 = time.perf_counter()
            order = create_art(nails, ref, init_canvas((SIDE, SIDE)), -0.05, i_limit=budget)
            dt = time.perf_counter() - t0
            rows.append({"layout": layout, "nails": len(nails), "time_s": dt,
                         "mse": mse(render(order, nails, SIDE, 0.05), ref)})
            print(f"layout {tag} {layout}: {len(nails)} nails {dt:.0f}s")
        results[tag] = rows

    fig, ax = plt.subplots(figsize=(6, 4.5))
    width = 0.35
    for i, (tag, rows) in enumerate(results.items()):
        vals = {r["layout"]: r["mse"] for r in rows}
        ax.bar(i - width / 2, vals["circle"], width, label=f"{tag}: круг" if i == 0 else None,
               color="tab:blue")
        ax.bar(i + width / 2, vals["rect"], width, label=f"{tag}: квадрат" if i == 0 else None,
               color="tab:orange")
    ax.set_xticks(range(len(results)), list(results))
    ax.set_ylabel("MSE (сила 0.05, 2000 итераций)")
    ax.set_title("--rect vs круг (~211 гвоздей)")
    ax.legend()
    savefig(fig, "layout.png")
    dump("layout", results)


def sweep_darken():
    """Input darkening factor c (internal target = ref * c/0.9), measured vs the
    canonical reference - the Birsak et al. 'darker inputs approximate better' rule."""
    factors = [0.9, 0.7, 0.5]  # 0.9 = current behaviour
    budget = 2000
    results = {}
    for tag, path in PHOTOS.items():
        ref = load_photo(path)
        nails = create_circle_nail_positions((SIDE, SIDE), nail_step=4)
        rows = []
        for c in factors:
            target = ref * (c / 0.9)
            order = create_art(nails, target, init_canvas((SIDE, SIDE)), -0.05, i_limit=budget)
            rows.append({"c": c, "mse": mse(render(order, nails, SIDE, 0.05), ref)})
            print(f"darken {tag} c={c}: mse={rows[-1]['mse']:.4f}")
        results[tag] = rows

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    for tag, rows in results.items():
        ax.plot([r["c"] for r in rows], [r["mse"] for r in rows], "o-", label=tag)
    ax.invert_xaxis()
    ax.set_xlabel("множитель яркости входа c (меньше = темнее)")
    ax.set_ylabel("MSE против ИСХОДНОГО эталона")
    ax.set_title(f"Затемнение входа ({budget} итераций, сила 0.05)")
    ax.legend()
    savefig(fig, "darken.png")
    dump("darken", results)


SWEEPS = {"pulls": sweep_pulls, "nails": sweep_nails, "random": sweep_random,
          "dims": sweep_dims, "layout": sweep_layout, "darken": sweep_darken}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep", choices=list(SWEEPS), required=True)
    args = parser.parse_args()
    SWEEPS[args.sweep]()


if __name__ == "__main__":
    main()
