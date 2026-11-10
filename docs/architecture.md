# Architecture

This document describes how ReString works today. For the migration story and rejected experiments read [history.md](history.md).

## Pipeline

```
Image.load          largest_square       resize              nails
PNG or JPEG  --->   central square  ---> 300 x 300     --->  circle or rectangle
(Rust codecs)       crop                 box/bilinear       border positions
                                                                |
    save_png  <---  render_bw / rgb  <---  create_art  <--------+
    8-bit PNG       accumulate AA         greedy search
                    lines, clip           (working canvas
                                           in Vec<f64>)
```

Everything below the Python surface runs in the Rust core `restring._core`.

## The Rust core

The `Image` class holds pixels in a `Vec<f64>` with width, height and channel count. Data never crosses the boundary as arrays. Python passes references and receives new `Image` objects, so a 2048 x 2048 photo costs one allocation per stage instead of millions of boxed floats.

| Responsibility | Where | Notes |
|---|---|---|
| PNG/JPEG codecs | `Image.load`, `Image.save_png` | `image` crate, RGB float 0..1 |
| Crops and resample | `Image.largest_square`, `Image.resize` | box filter when downscaling, bilinear when upscaling |
| Grayscale, channels | `Image.gray`, `Image.channel` | standard luminance weights |
| Nail layouts | `circle_nails`, `rect_nails` | midpoint ellipse rasterization |
| Line rasterizer | `line_aa` | Zingl algorithm, identical pixels to the original skimage implementation |
| Greedy search | `create_art` | line cache, working canvas and the scan loop all in Rust |
| Renders | `render_bw`, `render_rgb` | nail scaling included |
| Metrics | `ssim`, `mse`, `corr` | integral-image SSIM, no dependencies |

The Python modules are thin wrappers. `generator.py` orchestrates the pipeline. `canvas.py`, `nails.py`, `image_transformations.py` and `metrics.py` delegate to the core. `cli.py` wires the flow end to end without numpy or pillow.

## Greedy search

`create_art` rasterizes every nail pair once per run and stores the lines in CSR blocks per source nail. One iteration scans all candidate lines from the current nail, sums the squared-error improvement each pull would bring, takes the best, and applies the pull to the working canvas. Tie-breaking picks the last maximum, which matches the original Python loop.

The line cache is rasterized across cores with `std::thread::scope`. Chunks reassemble in source order, so output stays bit-identical regardless of thread count.

Iteration stops after a fixed budget or after 3 pulls with no improvement, whichever comes first. The `-r` flag restricts the scan to a fixed subset drawn once by a seeded splitmix64 sampler with Floyd's algorithm, seed 42.

## Correctness model

Three guarantees, all enforced by the test suite on every run:

1. Golden rasterizer outputs. Exact pixel lists and coverage values for axis-aligned and diagonal segments, plus measured checksums for long lines. [tests/test_rust_core.py](../tests/test_rust_core.py)
2. Golden greedy pull orders. Full scan and `-r` subset mode, frozen for a seeded target. Any change in rasterization, tie-breaking or subset seeding fails the suite.
3. No numpy in the runtime package. An AST guard test fails on any `import numpy` or `np.*` inside `src/restring`, because a runtime install ships without numpy.

The equivalence chain behind the goldens: the Rust rasterizer matched the Python port pixel for pixel, and the Python port matched skimage byte for byte. The pull orders matched the former numpy implementation 2862 out of 2862 on a 7000-iteration run. Those reference implementations are gone now. The goldens carry the guarantee forward.

## Metrics

Quality reports use two windowed statistics plus MSE and correlation. Plain SSIM misbehaves on thread renders: thin anti-aliased lines on white defeat the local statistics, so it peaks at 50 threads and falls while the picture improves (`docs/research/pull-count-quality.md`). The fix is a box blur before the comparison — `Image.box_blur(radius)` (separable, running sums, O(w*h)) followed by the windowed SSIM, exposed as `_core.ssim_blur`. Measured on both portrait fixtures at export strength 0.05: blurred SSIM rises monotonically along the pull series (0.60 to 0.67 on the male fixture) exactly where plain SSIM falls (0.56 to 0.30). `--metrics out.json` writes the four numbers plus pull count, nails and elapsed time after any generate run; the monotonicity property lives in `tests/test_e2e_quality.py`.

## Performance

Measured on an AMD 24-core Linux box, 300 x 300 working grid, 211 nails, portrait fixture. Reproduce with `uv run python scripts/benchmark.py`.

| Scenario | Time |
|---|---|
| Line cache build | 18 ms |
| 300 iterations | 59 ms |
| 2000 iterations | 267 ms |
| 7000 iterations | 797 ms |
| 2000 iterations, 422 nails | 578 ms |
| CLI run, 300 threads end to end | 0.20 s |
| Test suite, 46 tests | 1.8 s |

For comparison, the original Python stack needed 74.8 s for the 7000-iteration search. The full comparison lives in [history.md](history.md).

Two optimizations were measured and declined:

- SIMD and FMA. The scan loop reads pixels through a gather pattern, which blocks auto-vectorization. FMA instructions change float rounding, which would drift the frozen golden orders.
- Incremental improvement cache. Cache candidate improvements and invalidate the lines crossing each applied pull. The idea preserved results exactly, but the benchmark showed 0.4x to 0.6x throughput. Canvas-crossing chords give each changed pixel a fan-out of roughly 73 lines, so invalidation cost rivalled the full rescan. Reverted.

## Targets

One core crate, two bindings. `rust/core/` holds the platform-neutral algorithms as plain Rust: image container, Zingl rasterizer, line cache, greedy search, renderers, animation frames, metrics. Two thin bindings wrap it:

- CPython via pyo3 (`rust/`, the maturin crate): exposes `restring._core`, the module every Python test and script imports. The line cache builds with `std::thread::scope` here.
- Web via wasm-bindgen (`rust/wasm/`, target `web`): `load_image`, `generate`, `render_png` for the browser playground (`web/`). Threads are unavailable on wasm32-unknown-unknown, so the cache builder has a serial fallback behind `cfg`.

Behavior is shared by construction: both bindings call the same functions, and the golden tests plus `scripts/benchmark.py --label split` pin the split as behavior-preserving. The playground builds with `wasm-pack build rust/wasm --target web` and deploys `web/` to GitHub Pages (`.github/workflows/pages.yml`).

## Build

Requirements: uv, a Rust toolchain, and a C linker for cargo. Standard setups work out of the box:

```bash
uv sync
```

Minimal containers and WSL images often lack a system compiler. The zig compiler works as a drop-in cargo linker:

```bash
curl -sL https://ziglang.org/download/0.17.1/zig-x86_64-linux-0.17.1.tar.xz | tar -xJ -C ~/.local/zig --strip-components=1
printf '#!/bin/sh\nexec ~/.local/zig/zig cc "$@"\n' > ~/.local/bin/zigcc && chmod +x ~/.local/bin/zigcc
export CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER=~/.local/bin/zigcc
uv sync
```

There is no pure-Python fallback. Building from source requires Rust.
