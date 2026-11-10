"""Generation performance benchmarks.

Measures the greedy pipeline end to end: full runs at several iteration
budgets and nail counts, the -r mode, per-iteration extrapolation and the
line-cache build share. Run twice — once with --label before, once after a
change — then --plot renders the comparison chart.

    uv run python scripts/benchmark.py --label before
    uv run python scripts/benchmark.py --label after
    uv run python scripts/benchmark.py --plot
"""

import argparse
import json
import time
from pathlib import Path

OUT = Path(__file__).parent.parent / "docs" / "img"
SIDE = 300
PHOTO = "tests/data/portrait_male.png"


def timed(fn):
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", choices=["before", "after", "split"], default=None)
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()

    if args.plot:
        return plot()

    from restring import _core
    from restring.canvas import init_canvas
    from restring.generator import create_art
    from restring.image_transformations import largest_square, resize
    from restring.nails import create_circle_nail_positions

    img = resize(largest_square(_core.Image.load(PHOTO)), (SIDE, SIDE))
    target = img.gray(0.9)

    results = {}

    # full runs at -n 4 (the default preset nail count)
    nails4 = create_circle_nail_positions((SIDE, SIDE), nail_step=4)
    for iters in (300, 2000, 7000):
        _, dt = timed(lambda: create_art(nails4, target, init_canvas((SIDE, SIDE)),
                                         -0.05, i_limit=iters))
        results[f"full_n4_{iters}"] = dt

    # nail-count scaling at 2000 iterations
    for step in (2, 3, 6):
        nails = create_circle_nail_positions((SIDE, SIDE), nail_step=step)
        _, dt = timed(lambda: create_art(nails, target, init_canvas((SIDE, SIDE)),
                                         -0.05, i_limit=2000))
        results[f"full_n{step}_2000"] = dt

    # per-iteration and cache-build extrapolation at -n 4:
    # t(N) = build + N * per_iter -> solve from two points
    _, t_a = timed(lambda: create_art(nails4, target, init_canvas((SIDE, SIDE)), -0.05, i_limit=50))
    _, t_b = timed(lambda: create_art(nails4, target, init_canvas((SIDE, SIDE)), -0.05, i_limit=250))
    per_iter = (t_b - t_a) / 200
    results["per_iteration_ms_n4"] = per_iter * 1000
    results["cache_build_ms_n4"] = (t_a - 50 * per_iter) * 1000

    # random-nails mode
    _, dt = timed(lambda: create_art(nails4, target, init_canvas((SIDE, SIDE)),
                                     -0.05, i_limit=2000, random_nails=50))
    results["random50_2000"] = dt

    # CLI end to end
    from restring.cli import main as cli_main
    _, dt = timed(lambda: cli_main(["-i", PHOTO, "-o", "/tmp/bench_out.png",
                                    "-d", "300", "-n", "4", "-l", "300"]))
    results["cli_300"] = dt

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "benchmark.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data[args.label or "run"] = results
    path.write_text(json.dumps(data, indent=1))
    units = {"per_iteration_ms_n4", "cache_build_ms_n4"}
    print(f"[{args.label}] " + "  ".join(
        f"{k}={v:.1f}ms" if k in units else f"{k}={v:.3f}s" for k, v in results.items()))


def plot():
    import matplotlib
    import numpy as np

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = json.loads((OUT / "benchmark.json").read_text())
    if not {"before", "after"} <= data.keys():
        print("need both --label before and --label after runs first")
        return

    keys = [k for k in data["before"] if k in data["after"]]
    labels = {
        "full_n4_300": "300 итер., -n 4", "full_n4_2000": "2000 итер., -n 4",
        "full_n4_7000": "7000 итер., -n 4", "full_n2_2000": "2000 итер., -n 2",
        "full_n3_2000": "2000 итер., -n 3", "full_n6_2000": "2000 итер., -n 6",
        "per_iteration_ms_n4": "мс/итерацию, -n 4", "cache_build_ms_n4": "сборка кэша, мс",
        "random50_2000": "-r 50, 2000 итер.", "cli_300": "CLI 300 нитей",
    }
    x = np.arange(len(keys))
    before = [data["before"][k] for k in keys]
    after = [data["after"][k] for k in keys]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(x - 0.35, before, 0.7, label="до")
    ax.bar(x + 0.35, after, 0.7, label="после")
    ax.set_xticks(x, [labels.get(k, k) for k in keys], rotation=20, ha="right")
    ax.set_ylabel("время (с; мс для ms-метрик)")
    ax.set_title("Бенчмарки генерации: до и после инкрементального кэша")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "benchmark.png", dpi=150)
    for k, b, a in zip(keys, before, after):
        print(f"{k:>22}: {b:.4f} -> {a:.4f}  ({b / a:.1f}x)")


if __name__ == "__main__":
    main()
