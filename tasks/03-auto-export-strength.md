# T-03 — Auto export strength: `-s` derived from the pull count

| | |
|---|---|
| Target | Q1 2027 · v1.2.0 |
| Depends on | none |
| Unlocks | removes the project's main foot-gun |
| Size | M (1–3 days) |
| Status | [ ] not started |

## Why

`docs/tuning.md` opens with: "The `-s` value matters more than any other
flag... When `-s` is too high for the thread count, the render reaches its
target halfway, then overshoots and darkens. The optimum scales as 1 over the
thread count." Improvement candidate #2 in `docs/research/related-work.md`:
"Auto-scale `-s` against `-l`. Removes the main foot-gun." Today every new
user must read a tuning guide before their first good render.

## Current state

- `-s` defaults to a fixed `0.1` (`src/restring/cli.py:19`), which is wrong at
  both ends: previews want 0.15–0.2, 2000+ thread runs want 0.05.
- The fitted curve data already exists in the repository:
  `docs/img/params/pulls.json` (sweep of `-s` against pull count) plus the
  measured rule "0.05 above 1000 threads, 0.15 to 0.2 for previews".
- Export happens **after** the search (`src/restring/generator.py:82-89`), so
  the **actual** pull count is known by then — the auto value can use the real
  number, not the `-l` budget.

## What to build

1. **Fit the model.** Small script `scripts/fit_export_strength.py` (dev
   dependencies only, numpy allowed there): load
   `docs/img/params/pulls.json`, fit `s*(L) = k / L` (one parameter, least
   squares in log space), print `k` and the residual band. Cross-check against
   the two anchor points (≈0.2 near 300 pulls, 0.05 near 1200–2000).
2. **Resolution logic in Python.** `Config.export_strength: float | None`
   (default `None` = auto). New helper in `generator.py`:
   `resolve_export_strength(pull_count) -> float` = `clamp(k / pull_count,
   0.03, 0.3)` with the fitted `k` embedded as a named constant with a comment
   pointing at the fit script. Called in `generate_bw` and per channel in
   `generate_rgb` (RGB uses each channel's own actual count before padding —
   see the padding at `src/restring/generator.py:54`).
3. **CLI.** `-s` stays accepted; document `default: auto (fitted from the
   actual pull count)`. Log the resolved value at INFO:
   `Export strength: 0.052 (auto, 1927 pulls)`.
4. **Tests.**
   - Unit: resolver returns the fitted value at anchor points, respects
     clamps for extreme counts (e.g. 50 pulls → 0.3).
   - E2E quality: on both fixtures at 500 and 2000 pulls, auto `-s` render MSE
     is within 2% of the best hand-tuned `-s` from the existing sweep data.
   - Explicit `-s 0.1` still honored exactly (golden render unchanged).
5. **Docs.** README flag row and tuning guide: demote the manual `-s` table to
   "advanced"; the quick-start presets drop the `-s` flag entirely — this is
   the user-visible win: `uv run restring -i p.png -o out.png --rect -l 2000`.

## Acceptance criteria

- [ ] A bare `uv run restring -i p.png -o out.png --rect -l 2000` (no `-s`)
      produces a non-overshooted render on both fixtures.
- [ ] Auto is within 2% of hand-tuned quality at measured budgets.
- [ ] Explicit `-s` unchanged; default-off behavior for library users who pass
      `Config(export_strength=...)` explicitly is unchanged.
- [ ] Fit script committed; constant in code cites it.

## Files touched

`src/restring/generator.py`, `src/restring/cli.py`,
`scripts/fit_export_strength.py` (new), `tests/test_e2e_quality.py`,
`tests/test_cli_e2e.py`, `README.md`, `docs/tuning.md`.

## Out of scope

- Retuning the working-canvas strength (fixed 0.05 in `generate_bw`) — it is
  an internal constant, not a foot-gun.
- RGB-specific re-fitting — T-04 sweeps the channels; if channels need
  different `k`, the resolver grows a mode argument later.
