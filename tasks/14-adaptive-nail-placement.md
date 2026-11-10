# T-14 — Adaptive nail placement (research, flag only if proven)

| | |
|---|---|
| Target | Q3 2027 · v1.4.0 |
| Depends on | none (composes nicely with T-13's layouts, but runs on circle/rect alone) |
| Unlocks | better quality at equal nail hardware |
| Size | M (1–3 days) |
| Status | [ ] not started |

## Why

Nails today sit perfectly uniformly (`circle_nails`/`rect_nails`), yet a
portrait's detail lives in the eyes and mouth while forehead and background
are flat. If nail positions concentrate where chords can express detail, the
same 200 nails could buy measurably more picture. Nobody in the survey
(`docs/research/related-work.md`) ships adaptive placement — positive or
negative, this is a publishable measurement in the project's voice.

## Current state

- Placement is rasterized perimeters: ellipse midpoint (`rust/src/lib.rs:343`)
  subsampled by `nail_step`; rect border stepped (`rust/src/lib.rs:409`).
- The survey lists per-pixel error caps and Sobel edge boost (isandrocks) as
  the closest precedents — scoring tricks, not placement tricks.
- The core accepts arbitrary nail lists, so a placement experiment needs
  **no Rust changes** — Python builds the lists.

## What to build

1. **Gradient signal.** Small Rust helper `Image.gradient_magnitude() ->
   Image` (Sobel, grayscale) — pure f64 convolution, exposed for reuse by
   future tasks; Python wrapper in `metrics.py` or a new `analysis.py`.
2. **Placement algorithm** (`src/restring/adaptive.py`, prototype quality):
   - candidate pool: M = 4 × n uniformly spaced perimeter positions;
   - score(s) = sum of gradient magnitude within radius R = 40 px of
     candidate s (disc sum via the core's integral-image trick or a simple
     loop — prototype speed suffices);
   - select n positions greedily by score with a minimum angular gap of
     2π/M (guarantees spread, prevents clustering on one hot region).
3. **Experiment** (`scripts/adaptive_nails_experiment.py`, house style): both
   fixtures, circle and rect, nail counts 211/298/422, budgets 500/2000.
   Compare adaptive vs uniform at equal count: global MSE, center MSE, time.
   Pre-registered verdict rules:
   - adopt (`--adaptive` flag, default off) only on ≥3% global or ≥8% center
     MSE improvement at equal nail count on **both** fixtures;
   - otherwise document the negative and close the question.
4. **Flag (conditional on adoption)**: `--adaptive` in the CLI; adaptive
   lists feed the pipeline unchanged. New goldens for the adaptive path;
   uniform path untouched.
5. **Doc**: `docs/research/adaptive-nails-experiment.md` — question, setup,
   tables, verdict, and the algorithm description (reproducible from the doc
   alone).

## Acceptance criteria

- [ ] Gradient helper tested against a hand-computed 5×5 case.
- [ ] Experiment runs from one command and regenerates all cited artifacts.
- [ ] Research doc exists with pre-registered thresholds and a clear verdict.
- [ ] If adopted: `--adaptive` e2e test + tuning-guide row; if rejected: the
      doc says so with numbers and names the mechanism that failed.

## Files touched

`rust/src/lib.rs` (gradient helper), `src/restring/adaptive.py` (new),
`scripts/adaptive_nails_experiment.py` (new),
`docs/research/adaptive-nails-experiment.md` (new), tests; conditionally
`src/restring/cli.py`, `README.md`, `docs/tuning.md`.

## Out of scope

- Interior (non-perimeter) nails — separate geometry question.
- Placement guided by the error **during** the search (co-evolution) —
  interesting but a different, larger task; this one is placement-before-
  search.
- Making adaptive the default, regardless of results, until reproducibility
  across more photo classes is shown.
