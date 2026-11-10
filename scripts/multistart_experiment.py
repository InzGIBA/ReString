"""Multi-start greedy experiment: start diversity against the same compute.

Variations under test (pre-registered in tasks/17-multistart-research.md):
S starting nails (nail-list rotations) and S subset seeds (`-r 100`, seeds
42 upward), each run at budget B, best run kept; controls at matched total
compute (greedy with B*S pulls) and at B. Verdict rule: adopt nothing unless
multi-start at total budget B*S beats greedy at B*S by 3 percent or better
MSE on both fixtures — the lookahead result predicts it will not.

    uv run python scripts/multistart_experiment.py
"""

import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from restring import _core
from restring.image_transformations import largest_square, resize
from restring.nails import create_rectangle_nail_positions

SIDE = 300
STRENGTH = -0.05
BUDGETS = [500, 1000, 2000]
STARTS = [2, 4, 8, 16]
SUBSET = 100
OUT = Path(__file__).parent.parent / "docs" / "img"
PHOTOS = {
    "male": "tests/data/portrait_male.png",
    "female": "tests/data/portrait_female.png",
}


def render_mse(order, nails, reference):
    img = _core.render_bw(list(order), nails, STRENGTH, SIDE, SIDE, SIDE, SIDE, True)
    return _core.mse(img, reference)


def run(nails, target, budget, seed=None):
    t0 = time.perf_counter()
    order, final = _core.create_art(nails, target, STRENGTH, budget, SUBSET if seed is not None else None,
                                    True, None, None, False, seed)
    dt = time.perf_counter() - t0
    return order, final, _core.mse(final, target), dt


def main():
    results = {}

    for tag, path in PHOTOS.items():
        target = resize(largest_square(_core.Image.load(path)), (SIDE, SIDE)).gray(0.9)
        nails = create_rectangle_nail_positions((SIDE, SIDE), nail_step=4)
        rows = []

        for budget in BUDGETS:
            # controls: greedy at B and at every B*S the variations will claim
            control_budgets = sorted(set([budget] + [budget * s for s in STARTS]))
            for control in control_budgets:
                if any(r["config"] == f"greedy_{control}" for r in rows):
                    continue
                order, final, mse, dt = run(nails, target, control)
                rows.append({"config": f"greedy_{control}", "compute": control, "mse": round(mse, 4),
                             "time_s": round(dt, 2)})
                print(f"{tag} greedy {control}: mse={mse:.4f} ({dt:.2f}s)")

            for s in STARTS:
                # S starting nails: rotate the nail list, budget B per run
                t0 = time.perf_counter()
                mses = []
                for i in range(s):
                    offset = i * len(nails) // s  # starts evenly spread over the ring
                    rotated = nails[offset:] + nails[:offset]
                    _, final, _, _ = run(rotated, target, budget)
                    mses.append(_core.mse(final, target))
                dt = time.perf_counter() - t0
                best = min(mses)
                rows.append({"config": f"starts{s}_B{budget}", "compute": budget * s,
                             "mse": round(best, 4), "time_s": round(dt, 2)})
                print(f"{tag} starts {s} @ B={budget}: best mse={best:.4f} ({dt:.2f}s)")

                # S subset seeds: -r 100, seeds 42.., budget B per run
                t0 = time.perf_counter()
                mses = []
                for i in range(s):
                    _, final, _, _ = run(nails, target, budget, seed=42 + i)
                    mses.append(_core.mse(final, target))
                dt = time.perf_counter() - t0
                best = min(mses)
                rows.append({"config": f"seeds{s}_B{budget}", "compute": budget * s,
                             "mse": round(best, 4), "time_s": round(dt, 2)})
                print(f"{tag} seeds {s} @ B={budget}: best mse={best:.4f} ({dt:.2f}s)")

        results[tag] = rows

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "multistart_experiment.json").write_text(json.dumps(results, indent=1))

    # figure: MSE against total compute, multistart points against the greedy curve
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, tag in zip(axes, results):
        rows = results[tag]
        greedy = sorted([(r["compute"], r["mse"]) for r in rows
                         if r["config"].startswith("greedy")])
        ax.plot([c for c, _ in greedy], [m for _, m in greedy], "o-", label="greedy (compute control)")
        for name, marker in (("starts", "s"), ("seeds", "^")):
            pts = [(r["compute"], r["mse"]) for r in rows if r["config"].startswith(name)]
            ax.plot([c for c, _ in pts], [m for _, m in pts], marker, label=f"multi-{name} (best of S)")
        ax.set_xscale("log")
        ax.set_xlabel("total compute (pull budget)")
        ax.set_ylabel("render MSE")
        ax.set_title(tag)
        ax.legend(fontsize=8)
    fig.suptitle("Multi-start greedy: best of S runs against the greedy compute curve")
    fig.tight_layout()
    fig.savefig(OUT / "multistart_experiment.png", dpi=150)
    print("chart: docs/img/multistart_experiment.png")

    # pre-registered verdict: multi-start at B*S vs greedy at B*S
    print("\nverdict (adopt needs >=3% MSE gain of best-of-S at B*S over greedy at B*S, both fixtures):")
    for tag, rows in results.items():
        for s in STARTS:
            for budget in BUDGETS:
                control = next(r for r in rows if r["config"] == f"greedy_{budget * s}")
                for kind in ("starts", "seeds"):
                    best = next(r for r in rows if r["config"] == f"{kind}{s}_B{budget}")
                    gain = (control["mse"] - best["mse"]) / control["mse"] * 100
                    verdict = "ADOPT" if gain >= 3.0 else "no"
                    print(f"{tag} {kind} S={s} B={budget} (compute {budget * s}): "
                          f"{gain:+.1f}% vs greedy -> {verdict}")


if __name__ == "__main__":
    main()
