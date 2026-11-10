# T-11 — Physical thread model: thickness-aware rendering

| | |
|---|---|
| Target | Q2 2027 · v1.3.0 |
| Depends on | none (shares the `--canvas-size` flag name with T-09 if both land — merge is cosmetic) |
| Unlocks | realistic previews; physically grounded presets |
| Size | M (1–3 days) |
| Status | [ ] not started |

## Why

Today every thread is rasterized as a 1-px anti-aliased line regardless of
board size, and `docs/tuning.md` warns that exporting above the 300-px grid
"hurts" — because a hairline at high resolution covers a vanishing share of
pixels. Physical boards are not hairlines: Birsak used a 630 mm canvas with
0.15 mm thread, Demoussel found semi-transparent thread (α≈0.3) beats opaque.
A renderer that knows thread width in millimeters makes the digital preview
match the physical board and unlocks honest large exports.

## Current state

- `render_bw`/`render_rgb` (`rust/src/lib.rs:938`, `:966`) stamp Zingl 1-px
  coverage (`val * strength`, clamp at the end). Semi-transparency already
  exists as the `-s` semantics; **thickness is the missing half**.
- The Zingl rasterizer (`zingl_line`, `rust/src/lib.rs:272`) has no width
  parameter; thick-line rasterization is a distance-to-segment coverage
  problem, not a Bresenham one.

## What to build

1. **Rust: thick anti-aliased segments.** Function
   `thick_line(r0, c0, r1, c1, half_width_px) -> (rows, cols, coverage)`:
   bounding box of the segment inflated by `half_width`; for each pixel,
   coverage = clamped 1 − (distance_to_segment − half_width) (1-px linear
   falloff, same spirit as the AA in Zingl). Pure f64 math, no new crates.
   Expose it as `_core.thick_line` for golden tests, mirroring `line_aa`.
2. **Rust: physical renderer.** `render_bw_thick(order, nails, strength,
   in_w, in_h, out_w, out_h, white, thread_px: f64) -> Image` — drop-in
   parallel of `render_bw` stamping thick segments; `render_rgb_thick`
   likewise. Accumulation and clamping semantics unchanged.
3. **Pixel size from physics.** CLI gains `--canvas-size <mm>` (default 400)
   and `--thread-width <mm>` (default 0.2, typical polyester thread; Birsak
   used 0.15). `thread_px = thread_width_mm * out_side_px / canvas_size_mm`,
   floored at 1.0 (below that, the classic renderer is equivalent and
   cheaper — log which path was taken).
4. **CLI flag** `--realistic`: switches both renderers to the thick variants.
   Default rendering stays exactly as today — goldens untouched.
5. **Measurement** (`scripts/thread_model_experiment.py`, house style): both
   fixtures, canvas 400 mm, thread 0.15/0.2/0.3 mm, pulls 500/2000, export
   1200 px. Question pre-registered: at what thread width does the
   thick-render MSE at N pulls match hairline MSE at 2N pulls — i.e. how much
   thread does thickness buy? Deliverable:
   `docs/research/thread-model-experiment.md` + tuning-guide row.
6. **Tests**: `thick_line` goldens (horizontal, 45°, near-45° widths 1/2/3 px
   — exact coverage lists frozen like `line_aa`'s); thick render of a 2-pull
   order hand-checked; width < 1 px routes to the classic renderer; e2e CLI.

## Acceptance criteria

- [ ] `--realistic --canvas-size 400 --thread-width 0.2 -d 1200` produces a
      render whose lines are visibly and measurably ~0.6 px wide at 1200 px
      (assert mean covered-pixel width per segment within tolerance).
- [ ] Thick and classic renders agree within 1% MSE as `thread_px → 1.0`.
- [ ] Research doc answers the pre-registered question with numbers.
- [ ] No new crate dependencies; default path bit-identical (goldens).

## Files touched

`rust/src/lib.rs`, `src/restring/canvas.py`, `src/restring/cli.py`,
`scripts/thread_model_experiment.py` (new),
`docs/research/thread-model-experiment.md` (new), `tests/test_rust_core.py`,
`tests/test_cli_e2e.py`, `README.md`, `docs/tuning.md`.

## Out of scope

- Thread cross-section, gloss, or shadow — over-modeling.
- Making physical mode the default — only after T-05 (grid scale) and this
  task's numbers settle the interaction between export size and width.
