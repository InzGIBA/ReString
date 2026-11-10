# T-02 — `--min-chord`: minimum chord distance

| | |
|---|---|
| Target | Q1 2027 · v1.2.0 |
| Depends on | none |
| Unlocks | less wasted thread, cleaner short-pull clutter |
| Size | M (1–3 days) |
| Status | [ ] not started |

## Why

Ranked improvement candidate #1 in `docs/research/related-work.md`: the
canonical kaspermeerts gist uses `MIN_DISTANCE=20` on 288 pins, and every
descendant project keeps some form of it. Short pulls spend a thread segment
to darken 3–5 pixels — wasteful against a long chord that moves the whole
canvas. ReString has no such constraint today.

## Current state

- The greedy scan (`scan_candidates`, `rust/src/lib.rs:634`) evaluates **every**
  candidate `j != i` reachable in the CSR line cache built by `build_sources`
  (`rust/src/lib.rs:472`).
- `create_art` (`rust/src/lib.rs:512`) exposes no geometry options beyond
  `random_nails`.
- Python `Config` and CLI have no corresponding fields
  (`src/restring/generator.py:11`, `src/restring/cli.py:14`).

## What to build

1. **Core: candidate filter.** Add `min_chord: Option<f64>` (Euclidean distance
   in working-grid pixels) to `create_art`. After the line cache is built,
   precompute per source nail `i` a `Vec<bool>` mask over its `targets` —
   `allow[j] = dist(nails[i], nails[j]) >= min_chord`. The scan skips masked
   candidates. The mask is computed once per run; the scan loop gains one
   branch per candidate.
   - `None` must leave the pull orders **bit-identical** (goldens).
   - Distance in pixels, not nail indices: the circle and rectangle layouts
     have different index-to-distance mappings, and custom layouts (T-13)
     break index reasoning entirely.
2. **Dead-end recovery.** If the current nail has no allowed candidate (can
   happen with large thresholds on sparse layouts), fall back to the best
   **masked-out** candidate for one pull instead of stalling — mirrors the
   Hirnmoder rim-walk recovery noted in the survey. Log once at DEBUG.
3. **Python + CLI.** `min_chord: float | None = None` in `Config`;
   `--min-chord <px>` flag. Suggested starting values for measurement:
   5, 10, 20, 30 px on the 300 grid.
4. **Measurement (research doc).** Script `scripts/min_chord_experiment.py`
   following `scripts/alternatives_experiment.py`: both fixtures, rect layout
   step 4 (298 nails), budgets 500/2000, threshold sweep. Report global and
   center MSE, time, and average chord length. Adopt a default only if a
   threshold shows ≥3% global MSE improvement at equal budget; otherwise ship
   the flag with default off and document the curve in
   `docs/research/min-chord-experiment.md`.
5. **Tests.** `None` path golden-identical; a small-grid golden with threshold
   set; dead-end recovery covered by a constructed sparse case; e2e CLI flag
   smoke test.

## Acceptance criteria

- [ ] `--min-chord 20` changes the pull order and removes sub-20px chords
      (test asserts no consecutive nail pair closer than the threshold, except
      documented recovery pulls).
- [ ] Default behavior unchanged (goldens).
- [ ] Research doc with the threshold-vs-MSE curve exists and the tuning guide
      cites it.
- [ ] No measurable slowdown without the flag (benchmark before/after).

## Files touched

`rust/src/lib.rs`, `src/restring/generator.py`, `src/restring/cli.py`,
`scripts/min_chord_experiment.py` (new), `tests/test_rust_core.py`,
`tests/test_cli_e2e.py`, `README.md`, `docs/tuning.md`,
`docs/research/min-chord-experiment.md` (new).

## Out of scope

- `MIN_LOOP`-style recent-nail memory (kaspermeerts' second rule) — separate
  experiment if the chord filter alone underdelivers.
- Penalizing long chords (thread economy mode) — opposite direction, needs its
  own measurement.
