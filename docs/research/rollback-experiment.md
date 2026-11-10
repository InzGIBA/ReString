# Best-prefix rollback on stagnation

Expectation pre-registered before the measurement: rolling back to the best-error prefix on stagnation buys small but consistent gains at high budgets, near-zero at 500. A rollback flag ships if the gains reach 1 percent of MSE at 2000+ pulls on both fixtures.

Outcome: the mechanism has nothing to roll back. Zero pulls rolled back in every run, on both fixtures, at both budgets and at exhaustion. MSE is bit-identical with and without the flag. The decision hook resolves to keep the default off.

## Why the premise does not hold

The task reasoned that "those 3 failing pulls (and any plateau excursion before them) stay in the order". Reading the scan (`create_art`, rust/src/lib.rs) shows otherwise: when the best candidate improvement drops to zero or below, the loop increments the fail counter and jumps to the next iteration **without pushing a pull**. Failing scans are discarded before application. Every pull that enters the order carries a strictly positive improvement, so the canvas error decreases monotonically pull over pull. The best prefix is always the whole order.

The recovery path obeys the same rule: a dead-end pull (the min-chord recovery path) is applied only when its improvement is positive.

The machinery still shipped, because it is free and provably safe: `create_art` tracks the running error (each pull's improvement telescopes into the true canvas SSE), remembers the minimum, and with `rollback = true` truncates to that prefix, logging `Rolled back N of M pulls` at INFO when it fires. The property test (`tests/test_rust_core.py::test_rollback_prefix_never_worse`) asserts the truncated order is a prefix of the full order and its canvas MSE is never higher.

## Measurement

Both fixtures, rectangle nails at step 4, budgets 2000 and 3000 plus run-to-exhaustion. The 3000 budget crosses rect saturation (2500 to 2670 pulls), so the stagnation exit fires in every run:

| Fixture | Run | Pulls | Rolled back | MSE | Gain |
|---|---|---|---|---|---|
| male | budget 2000 | 2000 | 0 | 0.0291 | +0.00 percent |
| male | budget 3000 | 2670 | 0 | 0.0185 | +0.00 percent |
| male | exhaustion | 2670 | 0 | 0.0185 | +0.00 percent |
| female | budget 2000 | 2000 | 0 | 0.0303 | +0.00 percent |
| female | budget 3000 | 2513 | 0 | 0.0220 | +0.00 percent |
| female | exhaustion | 2513 | 0 | 0.0220 | +0.00 percent |

Script: `scripts/rollback_experiment.py`, raw data `docs/img/rollback_experiment.json`.

## Verdict

Improvement candidate #4 (damione1's rollback) closes for this code base: the stagnation guard already prevents non-improving pulls from entering the order, so best-prefix truncation is a no-op. `--rollback` ships default off and never changes any output. The guard itself is load-bearing: if a future feature ever applies non-improving pulls (a plateau-walk search, for instance), the rollback tracking is already in place to clean up after it.
