# T-16 — Blurred SSIM and a `--metrics` quality report

| | |
|---|---|
| Target | Q3 2027 · v1.4.0 |
| Depends on | none |
| Unlocks | honest acceptance metrics; user-facing quality numbers |
| Size | S (under a day) |
| Status | [ ] not started |

## Why

`docs/research/pull-count-quality.md` documents that plain SSIM misbehaves on
thread renders (thin dark lines on white defeat the local statistics), and
improvement candidate #5 in the survey points at isandrocks' fix: blur before
SSIM. Meanwhile the CLI computes no quality numbers at all — users eyeball
the PNG, and the e2e quality tests lean on MSE alone. One new metric fixes
both: a blurred SSIM in the core, wired into tests and a `--metrics` report.

## Current state

- `_core.ssim` (`rust/src/lib.rs:1026`): 7×7 uniform window, integral
  images, grayscale only.
- `src/restring/metrics.py` wraps ssim/mse/corr.
- No blur exists in the core (`Image` has resize — box filter — but no
  small-radius blur primitive; `resize` downscale is a coarse substitute, not
  a blur).
- Quality e2e tests (`tests/test_e2e_quality.py`) read metrics via the numpy
  bridge in scripts; the CLI prints nothing about quality.

## What to build

1. **Rust: blur.** `Image.box_blur(radius: usize) -> Image` — separable box
  blur (two passes via running sums; O(w·h) regardless of radius), grayscale
  and RGB (per channel). Edge handling: clamp (replicate). Exposed on the
  Image class.
2. **Rust: blurred SSIM.** `ssim_blur(a, b, radius: usize) -> f64` —
   `ssim(a.box_blur(radius), b.box_blur(radius))`; recommended radius 2 on
   the 300 grid. Wrapper `blurred_ssim(a, b, radius=2)` in
   `src/restring/metrics.py`.
3. **Validation** (the point of the metric): extend the saturation study
   data — along a pull-budget series (100…3000) on both fixtures, blurred
   SSIM must be **monotone non-decreasing within tolerance** where plain SSIM
   is not (cite the specific non-monotone segment from
   `pull-count-quality.md`). This becomes the property test.
4. **CLI `--metrics <path.json>`**: after rendering, compute MSE, corr,
   plain SSIM, blurred SSIM of render vs the preprocessed working target
   (upscaled to the export size), plus pull count, nails, elapsed time;
   write JSON and log a one-line summary at INFO. Works in generate mode
   (target known) — in `--project` mode (T-08) the target is absent: the
   flag requires `-i` and errors clearly otherwise.
5. **Wire the tests**: `tests/test_e2e_quality.py` acceptance asserts gain a
   blurred-SSIM condition alongside MSE (do not remove the MSE asserts —
   additive change).
6. **Docs**: metrics section in `docs/architecture.md` (one paragraph: why
   blurred, the misbehavior it fixes, pointer to the research doc); README
   flag row.

## Acceptance criteria

- [ ] `box_blur` matches a hand-computed 7×7 case exactly (golden).
- [ ] Monotonicity property test passes on both fixtures; the doc records
      the plain-SSIM segment it now catches.
- [ ] `--metrics out.json` produces the full report on a generate run and a
      clear error on project-only runs.
- [ ] Quality e2e asserts on blurred SSIM; suite stays fast (the metric is
      O(w·h), integral-image based).

## Files touched

`rust/src/lib.rs`, `src/restring/metrics.py`, `src/restring/cli.py`,
`tests/test_rust_core.py`, `tests/test_e2e_quality.py`,
`tests/test_cli_e2e.py`, `docs/architecture.md`, `README.md`.

## Out of scope

- Gaussian blur (box×3 approximates it; not needed until something demands
  it).
- Making blurred SSIM a **stopping criterion** inside the search — this task
  only measures and reports; isandrocks-style stopping is a separate
  experiment if the metric proves stable.
