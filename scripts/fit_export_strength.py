"""Fit the auto export-strength constant: s*(L) = k / L.

Loads the existing sweep data (docs/img/params/pulls.json, produced by
`scripts/parameter_sweep.py --sweep pulls`), takes the best hand-tuned
strength at each pull count, and fits a one-parameter power law with the
exponent fixed at -1: least squares in log space, log s = log k - log L.
Prints k, the residual band and the anchor cross-check.

    uv run python scripts/fit_export_strength.py
"""

import json
import math
from pathlib import Path

import numpy as np

DATA = Path(__file__).parent.parent / "docs" / "img" / "params" / "pulls.json"


def best_strengths(data):
    """(pull_count, best strength, best mse, fixture) rows over all curves."""
    rows = []
    for tag, result in data.items():
        curves = result["curves"]
        strengths = sorted(float(s) for s in curves)
        # the curve grids share the same pull counts
        pull_counts = sorted({p["n"] for pts in curves.values() for p in pts})
        for n in pull_counts:
            scored = []
            for s in strengths:
                pts = {p["n"]: p["mse"] for p in curves[f"{s:g}"]}
                scored.append((pts[n], s))
            mse, s = min(scored)
            rows.append((n, s, mse, tag))
    return rows


def main():
    data = json.loads(DATA.read_text())
    all_rows = best_strengths(data)

    # grid-censored points: the best strength equals the sweep grid maximum,
    # so the true optimum sits at or beyond the edge and would bias k down
    grid_max = max(float(s) for s in next(iter(data.values()))["curves"])
    rows = [r for r in all_rows if r[1] < grid_max]
    censored = len(all_rows) - len(rows)
    print(f"points: {len(rows)} uncensored, {censored} dropped (best s at the grid max {grid_max:g})")

    log_terms = [math.log(s) + math.log(n) for n, s, _, _ in rows]
    log_k = float(np.mean(log_terms))
    residual = float(np.std(log_terms))
    k = math.exp(log_k)

    print(f"k = {k:.1f}   residual band: / x{math.exp(residual):.2f} (multiplicative, 1 sigma)")
    print("\nanchors:")
    for n_anchor in (100, 300, 500, 1000, 1500, 2000):
        sel = sorted({(n, s) for n, s, _, _ in all_rows if n == n_anchor})
        for n, s in sel:
            print(f"  n={n:>5}: measured best s={s:g}, fit s={k / n:.3f}")
    print("\nresolved values with k embedded (clamp 0.03..0.3):")
    for n in (50, 300, 1000, 1927, 3000, 7000):
        s = min(0.3, max(0.03, k / n))
        print(f"  n={n:>5}: auto s={s:.3f}")


if __name__ == "__main__":
    main()
