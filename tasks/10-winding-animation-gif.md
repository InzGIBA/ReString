# T-10 — Winding animation: GIF of the thread being wound

| | |
|---|---|
| Target | Q2 2027 · v1.3.0 |
| Depends on | T-08 (`.restring` project format as input) |
| Unlocks | shareable renders; winding tutorials; project marketing |
| Size | M (1–3 days) |
| Status | [x] done (505e1f6) |

## Why

The pull order is inherently temporal — the picture emerges pull by pull. An
animation of that emergence is the most shareable artifact a string-art
generator can produce, doubles as a winding tutorial for makers, and costs
little: the renderer already draws a pull order incrementally.

## Current state

- `render_bw` (`rust/src/lib.rs:938`) rasterizes the whole order in one pass
  onto a fresh canvas — there is no per-step snapshot, but the loop structure
  (`for pair in order.windows(2)`) is exactly the frame generator needed.
- The `image` crate is compiled with `features = ["png", "jpeg"]` only
  (`rust/Cargo.toml:13`); GIF encoding exists behind the `gif` feature.
- T-08 provides the `Project` input; this task never runs a search.
- The numpy AST guard applies: frame assembly belongs in Rust, not in a
  numpy/Pillow Python sidecar.

## What to build

1. **Rust: incremental frame renderer.** New pyfunction
   `animate_bw(order, nails, strength, in_w, in_h, out_w, out_h, white,
   frames: usize) -> Vec<Image>`: maintain the running canvas (same accumulate
   semantics as `render_bw` — a pull adds `val * strength`, clamped only at
   snapshot time so intermediate frames share the final image's math), and
   snapshot **after every pull** into a `Vec<Image>` when `frames == 0`
   (raw mode), or at `frames` evenly spaced pull indices (downsampled mode).
   Keep raw and downsampled as one function — the poster and future video
   export reuse both.
2. **Rust: GIF writer.** `save_gif(path, images: Vec<Image>, fps: u16)` using
   the `image` crate's GIF encoder (add the `gif` feature; frame delay from
   fps; full-replace disposal; the palette quantization the encoder provides
   is acceptable for grayscale threads). Full-white and near-white colors
   must survive quantization — verify on the wb mode too.
3. **Python + CLI.** `src/restring/animation.py`: `animate_project(project,
   out_path, *, export_strength, size, frames)`. CLI:
   `restring --project art.restring --anim wind.gif [--anim-frames 180]
   [-s auto-per-T-03 -d 600]`. Frame count default: 180 (≈6 s at 30 fps);
   every frame maps to a contiguous, monotonic range of pulls — no pull may
   appear twice and none may be skipped (assert in tests).
4. **RGB** (second step, still this task): interleave the three orders the
   same way `render_rgb` does (`rust/src/lib.rs:979`) and snapshot per
   interleaved step; the three fixed thread colors carry into frames.
5. **Size guard**: log the GIF size; if the downsampled 600-px result exceeds
   25 MB, halve fps in a warning and document `-d 450` as the dial. No
   silent quality loss.
6. **Tests**: frame count exact; monotonic coverage of pulls; first frame is
   the blank canvas, last frame is pixel-identical to `render_bw` of the full
   order at the same strength (the key correctness property); GIF file
   signature and non-trivial size; CLI e2e.

## Acceptance criteria

- [ ] `restring --project art.restring --anim wind.gif` plays in a browser
      and ends on the same image as the PNG render (asserted by test, checked
      by eye in the PR).
- [ ] BW and RGB both animate; wb (white-on-black) mode survives GIF palette
      quantization.
- [ ] A 2000-pull project animates in under 5 s of compute at 600 px.
- [ ] `cargo` gains only the `gif` feature of the existing `image` crate —
      no new crate dependencies.

## Files touched

`rust/Cargo.toml`, `rust/src/lib.rs`, `src/restring/animation.py` (new),
`src/restring/cli.py`, `tests/test_animation.py` (new),
`tests/test_cli_e2e.py`, `README.md`.

## Out of scope

- MP4/WebM (codec crates are heavy; GIF first, external ffmpeg for video).
- Partial-range animation ("show pulls 500–1000") — trivial later once there
  is demand; the raw-frame mode already makes it possible.
