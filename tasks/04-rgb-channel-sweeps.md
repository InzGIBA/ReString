# T-04 — RGB per-channel sweeps (research)

| | |
|---|---|
| Target | Q1 2027 · v1.2.0 |
| Depends on | none |
| Unlocks | evidence-based RGB defaults; input for T-12 palette work |
| Size | M (1–3 days) |
| Status | [ ] not started |

## Why

The README roadmap already carries this debt: "Re-run the RGB sweeps —
per-channel thresholds were never measured." Every B/W flag has a degradation
curve behind it (`docs/tuning.md`); RGB has folklore. The RGB pipeline also has
two structural unknowns nobody measured: channels stop at different pull
counts and get padded (`src/restring/generator.py:53-54`), and all three use
the same working strength.

## Current state

- `generate_rgb` (`src/restring/generator.py:41`): one greedy run per channel
  on a shared nail grid, working strength ±0.1 (vs ±0.05 for B/W), budgets
  padded to the max channel length, export via `pull_order_to_array_rgb`.
- `render_rgb` in Rust paints fixed pure RGB thread colors
  (`rust/src/lib.rs:972`).
- Existing RGB artifacts: `docs/img/rgb_mse_curves_portrait_woman_1.png`,
  `docs/img/metrics_rgb_portrait_woman_1.json` — one fixture, no parameter
  sweeps, produced by `scripts/quality_analysis.py`.

## What to build

A research deliverable, not a flag. Follow the house pattern of
`scripts/alternatives_experiment.py` (dev-only numpy/matplotlib, `_bridge.py`
for image conversion, JSON + PNG into `docs/img/`).

1. **Script** `scripts/rgb_channel_sweep.py`, both portrait fixtures,
   rect layout step 4, and the sweep grid:
   - working strength per channel: 0.03 / 0.05 / 0.1 / 0.15;
   - per-channel budgets: equal vs proportional to channel target contrast
     (e.g. budget split by the channel's grayscale variance);
   - export strength: fixed 0.1 vs 1/k auto (cross-reference T-03's fitted
     constant if it has landed; otherwise fit per-channel the same way);
   - stopping: budgeted vs exhaustion per channel (padding waste — a padded
     channel repeats its last nail, painting the same chord for nothing).
2. **Metrics**: global color MSE, per-channel MSE, grayscale SSIM of the
   render vs the target, share of padded pulls.
3. **Deliverables**: `docs/research/rgb-channels-experiment.md` (question,
   setup, tables, verdict — same voice as the alternatives doc),
   `docs/img/rgb_channel_sweep.json`, per-facet PNG curves.
4. **Verdict rules, written before running** (pre-registration, house style):
   - adopt a pipeline change only on ≥5% global color MSE improvement or a
     documented perceptual gain on both fixtures;
   - record negative results with the same care — they close questions.
5. **Follow-through**: if a change is adopted, a small code PR updates
   `generate_rgb` defaults and the tuning guide's RGB row; the doc records
   before/after numbers. If nothing is adopted, the tuning guide cites the doc
   as the reason the current defaults stand.

## Acceptance criteria

- [ ] Script runs end to end via `uv run python scripts/rgb_channel_sweep.py`
      and regenerates every artifact it cites.
- [ ] Research doc exists with the verdict table and pre-registered rules.
- [ ] `docs/tuning.md` RGB guidance references the doc.
- [ ] If defaults changed: goldens added for the new RGB path, README preset
      table updated; if not: README roadmap item checked off as "measured,
      current defaults stand".

## Files touched

`scripts/rgb_channel_sweep.py` (new), `docs/research/rgb-channels-experiment.md`
(new), `docs/img/rgb_channel_sweep*` (new), `docs/tuning.md`, `README.md`.
Conditionally: `src/restring/generator.py`, `tests/test_e2e_quality.py`.

## Out of scope

- Non-RGB palettes (CMYK, real floss colors) — that is T-12; this task's
  numbers are its input.
- Rust changes unless the adopted change requires them (e.g. per-channel
  working strength is a Python-side parameter already).
