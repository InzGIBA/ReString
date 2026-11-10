# T-01 — `--weight`: importance-weighted greedy search

| | |
|---|---|
| Target | Q1 2027 · v1.2.0 |
| Depends on | none |
| Unlocks | perceptually better portraits; groundwork for face masks |
| Size | M (1–3 days) |
| Status | [x] done (f53d04d) |

## Why

The weighted scan is the **only alternative that beat plain greedy** in the
alternatives experiment: global MSE rises ~3%, but center MSE (the face, where
the viewer looks) falls **24–28%** at 500 and 2000 threads, for ~25% more time.
The algorithm already exists and is measured — it just never reached the user.

## Current state

- The Rust core has `weighted_search(nails, orig, weights, strength, i_limit, white)`
  (`rust/src/lib.rs:1133`), registered in the pymodule (`rust/src/lib.rs:1434`).
  It is a serial, experimental variant: it builds the line cache with
  `build_cache` (no `std::thread::scope` parallelism) and has **no
  `random_nails` support**.
- The weight map is built with numpy in `scripts/alternatives_experiment.py:54`
  (`make_weight_map`: Gaussian, sigma 100, peak 3.0, background 0.5, on the
  300 px grid). The runtime package cannot do this — numpy is banned by
  `tests/test_no_runtime_numpy.py`.
- Production search goes through `_core.create_art` (`rust/src/lib.rs:512`),
  called from `restring/generator.py:30` (`create_art` wrapper).
- The CLI (`src/restring/cli.py:14`) and `Config` (`src/restring/generator.py:11`)
  have no weighting field.

## What to build

1. **Merge weighting into the production path.** Extend `create_art` with an
   optional `weights: Option<&Image>` parameter (pyo3 signature:
   `weights=None`). When `None`, behavior must be **bit-identical** to today —
   the frozen golden pull orders (`tests/test_rust_core.py`) must pass
   unchanged. When present, use the `scan_candidates_weighted` scoring
   (`rust/src/lib.rs:1096`). Unlike the experimental `weighted_search`, the
   merged path keeps the parallel cache build and `random_nails`.
2. **Weight-map constructor in Rust.** New pyfunction
   `gaussian_weights(w: usize, h: usize, sigma: f64, peak: f64, bg: f64) -> Image`
   returning a grayscale map: `w(r,c) = bg + (peak - bg) * exp(-d²/2σ²)` with
   `d` the distance from the image center in pixels. This replaces the numpy
   builder and keeps the runtime dependency-free.
3. **Python plumbing.** Add `weight_peak: float | None = None` to `Config`.
   In `generate_bw` (`src/restring/generator.py:71`): when set, build the map
   with `sigma = side_len / 3` (reproduces the measured sigma 100 on the 300
   grid), `bg = 0.5`, and pass it through. B/W only in this task — RGB wiring
   waits for T-04's per-channel numbers.
4. **CLI.** `--weight <peak>` (float, suggested range 1.5–5.0, default off).
   Log the chosen sigma and peak at INFO.
5. **Tests.**
   - `weights=None` → existing goldens untouched.
   - `weights=Some` on the seeded golden fixture → new frozen golden order
     (add next to the existing ones).
   - E2E quality: on both portrait fixtures, `--weight 3` center-MSE (central
     50% box, as in the experiment doc) is at least 15% below plain greedy at
     2000 threads.
6. **Docs.** README flag row; `docs/tuning.md` row (recommended: 3.0 for
   portraits, off for non-portrait subjects) citing the experiment doc.

## Acceptance criteria

- [ ] `uv run restring -i p.png -o out.png --rect -l 2000 --weight 3` runs and
      concentrates threads on the center (visible in output, asserted by test).
- [ ] Default runs are bit-identical to v1.1.0 (goldens prove it).
- [ ] Weighted run is measurably better in the center box on both fixtures.
- [ ] README + tuning guide updated with the measured numbers.
- [ ] `weighted_search` experimental function kept (scripts depend on it) but
      documented as superseded in a code comment.

## Files touched

`rust/src/lib.rs`, `src/restring/generator.py`, `src/restring/cli.py`,
`tests/test_rust_core.py`, `tests/test_e2e_quality.py`, `README.md`,
`docs/tuning.md`.

## Out of scope

- Arbitrary user-supplied mask images (separate task if demanded).
- RGB weighting (needs T-04 data first).
- Re-measuring the experiment — `docs/research/alternatives-experiment.md`
  already carries the numbers.
