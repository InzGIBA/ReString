"""Rollback experiment: what does truncating to the best prefix buy?

Pre-registered expectation: small but
consistent gains at high budgets, near-zero at 500. Budgets 2000 and 3000
(3000 crosses rect saturation, so the stagnation exit fires), plus one
run-to-exhaustion pass per fixture. Decision hook: 1 percent or better MSE
at 2000+ pulls on both fixtures proposes flipping the default in the next
release; this task does not re-pin anything.

    uv run python scripts/rollback_experiment.py
"""

import json
from pathlib import Path

from restring import _core
from restring.image_transformations import largest_square, resize
from restring.nails import create_rectangle_nail_positions

SIDE = 300
EXPORT = 300
STRENGTH = -0.05
OUT = Path(__file__).parent.parent / "docs" / "img"
PHOTOS = {
    "male": "tests/data/portrait_male.png",
    "female": "tests/data/portrait_female.png",
}


def render_mse(order, nails, reference):
    img = _core.render_bw(list(order), nails, STRENGTH, SIDE, SIDE, EXPORT, EXPORT, True)
    return _core.mse(img, reference)


def main():
    results = {}
    for tag, path in PHOTOS.items():
        target = resize(largest_square(_core.Image.load(path)), (SIDE, SIDE)).gray(0.9)
        reference = target
        nails = create_rectangle_nail_positions((SIDE, SIDE), nail_step=4)
        rows = []
        runs = [("budget_2000", 2000), ("budget_3000", 3000), ("exhaustion", None)]
        for label, budget in runs:
            full, final_full = _core.create_art(nails, target, STRENGTH, budget, None, True)
            short, final_short = _core.create_art(nails, target, STRENGTH, budget, None, True,
                                                  None, None, True)
            pulls_full = len(full) - 1
            pulls_short = len(short) - 1
            rolled = pulls_full - pulls_short
            mse_full = render_mse(full, nails, reference)
            mse_short = render_mse(short, nails, reference)
            gain = (mse_full - mse_short) / mse_full * 100
            rows.append({
                "run": label, "pulls_full": pulls_full, "pulls_rolled": rolled,
                "mse_full": round(mse_full, 4), "mse_rollback": round(mse_short, 4),
                "gain_percent": round(gain, 2),
                "order_is_prefix": list(short) == list(full)[: len(short)],
            })
            print(f"{tag} {label}: {pulls_full} pulls, rolled back {rolled}, "
                  f"mse {mse_full:.4f} -> {mse_short:.4f} ({gain:+.2f}%)")
        results[tag] = rows

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "rollback_experiment.json").write_text(json.dumps(results, indent=1))

    print("\ndecision hook (>=1% MSE gain at 2000+ pulls on both fixtures):")
    for tag, rows in results.items():
        for r in rows:
            if r["pulls_full"] >= 2000:
                verdict = "PROPOSE default flip" if r["gain_percent"] >= 1.0 else "keep default off"
                print(f"{tag} {r['run']}: {r['gain_percent']:+.2f}% -> {verdict}")


if __name__ == "__main__":
    main()
