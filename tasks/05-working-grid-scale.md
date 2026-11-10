# T-05 — Working grid above 300 px (research + optional flag)

| | |
|---|---|
| Target | Q1 2027 · v1.2.0 |
| Depends on | none |
| Unlocks | finer detail for large boards; informs physical-size presets |
| Size | M (1–3 days) |
| Status | [ ] not started |

## Why

Second item of the README roadmap: "Test the working grid above 300 px."
Everything is tuned around a 300×300 working grid (`LONG_SIDE` in
`src/restring/cli.py:11`), and `docs/tuning.md` warns that exporting above the
working grid hurts. Whether **searching** above 300 helps has never been
measured — 600² quadruples the pixel work per scan, so the answer decides
where compute is best spent.

## Current state

- The 300 constant appears in exactly one production place: `cli.py:11`
  (`LONG_SIDE = 300`), feeding `resize(largest_square(img), (300, 300))`.
- `Config.side_len` (`src/restring/generator.py:14`) already flows through the
  pipeline — `create_art` and the renderers take whatever grid they are given.
- Cost model to verify, not assume: line cache build is O(nails² × line
  length) and parallel (`rust/src/lib.rs:537`); each scan is O(cache pixels);
  so 600² ≈ 4× scan cost at equal nail count.
- Benchmark harness exists: `scripts/benchmark.py` with `--label`/`--plot`.

## What to build

1. **Research script** `scripts/grid_scale_experiment.py`: both fixtures, rect
   step 4 (298 nails — nail count held fixed to isolate the grid variable),
   grids 300 / 450 / 600, thread budgets 500 / 2000 (budget in pulls, not
   time). Metrics: render MSE and SSIM vs the reference at a fixed 1200 px
   export, time for cache build and search. Targets preprocessed by the same
   box-filter path (`Image.resize`) at each grid size.
2. **Expected confound to control**: at 600 px a 1-px line darkens 4× fewer
   pixels relative to the canvas — the working strength 0.05 may need to
   scale. Sweep working strength {0.05, 0.1} per grid so the conclusion is
   about the grid, not a mistuned constant.
3. **Deliverable**: `docs/research/grid-scale-experiment.md` with the
   quality-vs-time curve and a one-line verdict:
   - gain < 3% MSE or > 3× time → keep 300, document, check off the roadmap
     item as answered;
   - otherwise → implement the flag (next point).
4. **Flag (only on a positive verdict)**: `-g/--grid <px>` CLI option
   replacing the hard-coded `LONG_SIDE`, default 300 (goldens and all
   published numbers stay at 300). `Config` gains `grid: int = 300`.
   Presets in README gain a "large board" row if it earns one.
5. **Tests**: default path unchanged (goldens); if the flag lands, one e2e at
   600 asserting the render is valid and the doc's expected MSE ordering
   (600 ≥ 300 quality) holds on the fixtures.

## Acceptance criteria

- [ ] Research doc exists with pre-registered thresholds and both fixtures.
- [ ] The roadmap question is answered either way with numbers.
- [ ] If adopted: `-g` works end to end, tuning guide row added, benchmark
      table gains a 600-row.
- [ ] If rejected: `docs/tuning.md` cites the doc as the reason 300 stands.

## Files touched

`scripts/grid_scale_experiment.py` (new),
`docs/research/grid-scale-experiment.md` (new), `docs/img/` artifacts;
conditionally `src/restring/cli.py`, `src/restring/generator.py`,
`tests/test_cli_e2e.py`, `README.md`, `docs/tuning.md`.

## Out of scope

- Changing nail counts with the grid (nail_step is a separate axis; the
  experiment freezes it).
- GPU or SIMD acceleration to make 600 cheap — closed territory, see the
  dead-end table in `tasks/README.md`.
