# T-15 — Best-prefix rollback on stagnation

| | |
|---|---|
| Target | Q3 2027 · v1.4.0 |
| Depends on | none |
| Unlocks | strictly-better outputs at the same budget |
| Size | S (under a day) |
| Status | [ ] not started |

## Why

The search stops after 3 pulls with no improvement
(`docs/architecture.md`, Greedy search) — but those 3 failing pulls (and any
plateau excursion before them) stay in the order and in the render:
zero-improvement pulls still darken pixels along their chord. damione1's
project rolls back to the best prefix on stagnation (survey, improvement
candidate #4), and ReString's prefix-deterministic search makes the rollback
trivial: track when the error was lowest and truncate there.

## Current state

- `create_art` (`rust/src/lib.rs:512-`): the loop scans, applies the best
  pull, and counts `fails`; at `fails == 3` it returns the full
  `pull_order` — including the failing pulls.
- The chosen pull's error delta is computed during the scan, so a running
  error total costs nothing to maintain (no extra O(w·h) pass).

## What to build

1. **Rust**: in `create_art`, maintain `running_error` (initial error of the
   blank canvas vs target) updated by each applied pull's delta, and
   `best_len`/`best_error` updated whenever `running_error` hits a new
   minimum. On exit (stagnation **or** budget), add a `rollback: bool`
   parameter: when true, return `order[..best_len]` instead of the full
   order. Default `false` — **frozen goldens must not move**.
2. **Expose**: `rollback` parameter through the pyo3 signature and the
   Python wrapper `create_art` (`src/restring/generator.py:23`); `Config`
   field `rollback: bool = False`; CLI `--rollback` store_true flag.
3. **Sanity property**: with `rollback`, the returned prefix is never worse —
   its working-canvas MSE is ≤ the full order's. This holds by construction
   (minimum tracking); the test asserts it numerically anyway on the seeded
   fixture, comparing `_core.mse(final_canvas, target)` for both variants.
4. **Measurement** (`scripts/rollback_experiment.py`, small): both fixtures,
   budgets 2000/3000 (stagnation territory per the saturation data in
   `docs/research/pull-count-quality.md`): how many pulls get rolled back on
   average, MSE before/after, and whether the render changes visibly.
   Expectation to pre-register: small but consistent gains at high budgets;
   near-zero at 500. Doc: `docs/research/rollback-experiment.md`.
5. **Decision hook**: if the gains are ≥1% MSE at 2000+ pulls on both
   fixtures, propose flipping the default in the **next** release (goldens
   re-pinned deliberately, in its own PR — this task does not re-pin).

## Acceptance criteria

- [ ] Default path bit-identical (all existing goldens pass untouched).
- [ ] `--rollback` never increases MSE (property test + fixture numbers).
- [ ] Rollback length reported at INFO: `Rolled back 7 of 2861 pulls`.
- [ ] Research doc with the pre-registered expectation and the outcome.

## Files touched

`rust/src/lib.rs`, `src/restring/generator.py`, `src/restring/cli.py`,
`scripts/rollback_experiment.py` (new),
`docs/research/rollback-experiment.md` (new), `tests/test_rust_core.py`,
`README.md`, `docs/tuning.md`.

## Out of scope

- Rolling back to a prefix and **continuing** the search from it (restart
  after rollback) — that is multi-start territory (T-17); keep this task
  pure truncation.
- Re-pinning existing goldens or changing defaults.
