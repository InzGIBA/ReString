# History

The project began in 2020 as a Python course assignment. Through 2026 it went through a restructure, a toolchain change, a Rust migration and two optimization rounds. This page records the path, the numbers and the ideas measured and rejected. Current state lives in [architecture.md](architecture.md).

## Timeline

| Commit | Change | Effect |
|---|---|---|
| `a735f2b` | restructure to src-layout, tests, PEP 621 | installable package, first test suite |
| `758d2f0` | Poetry to uv, Python 3.12 | lock shrinks from 25 packages |
| `d5ffd55` | rename StringArt to ReString | package `restring`, CLI `restring` |
| `461f334` | e2e quality acceptance tests | thresholds calibrated on synthetic fixtures |
| `ba75c35` | real portrait fixtures and tests | Unsplash photos, recalibrated thresholds |
| `0b639af` | face-centered 2048px fixtures | better metrics across the board |
| `d96f149` | own rasterizers, Python 3.14, numpy 2 | runtime drops to numpy + pillow |
| `795174d` | Rust core with PyO3 | 82x on the greedy search |
| `1f958de` | zero runtime dependencies | the venv ships one package, `restring` |
| `9c7d93b` | Python reference code removed | golden tests replace executable references |
| `002b92f` | parallel line-cache rasterization | 8.4x cache build, up to 3.6x short runs |

## v2.0.0

Twenty measured work orders turned the generator into a full pipeline: importance weighting (`--weight`, center MSE down 24 to 28 percent on portraits), auto export strength (fitted 104/L, within 2 percent of hand-tuned), thread palettes with CMYK (42 to 45 percent better color MSE than the RGB triple), custom layouts (polygon, star, rings, SVG outlines), `.restring` project files with byte-identical re-render, a numbered-nail winding poster with thread length, a GIF animation, a physical thread model (0.3 mm beats the hairline by 35 percent at large exports), a blurred SSIM metric with monotonicity proof, wheels on PyPI, CI on three operating systems, a wasm playground and a typed 2.0 API.

The research tasks closed questions with numbers instead of shipping flags: adaptive nail placement loses on all 24 measured facets, multi-start never beats spending the same compute on more threads, and min-chord plus rollback measured as no-ops. The search-strategy family now carries six negative results: beam, receding horizon, multi-scale, asymmetric penalties, add/remove local search and multi-start. Every verdict lives in [research/](research/).

## Where the time went

Profiling the original Python on a 300-thread run: 46 percent in `skimage.draw.line_aa` called 63,900 times, 14 percent in the Python candidate loop. The code re-rasterized every candidate line on every iteration, though each nail pair repeats dozens of times per run.

The fix went in three steps. Cache all nail pairs once per run, rasterize that cache across cores, move the whole scan loop to Rust. Per-iteration cost fell from 10.7 ms to 0.11 ms.

## The rasterizer detour

The first numpy replacement for `line_aa` used the classic Xiaolin-Wu algorithm. The output looked close but rendered about 1.3 to 1.5 times darker per line: the same ink spread over fewer pixels. The e2e quality thresholds caught the overshoot on synthetic fixtures, where a flat disk rendered worse than a blank canvas.

The fix was a line-by-line port of the Zingl algorithm from the skimage sources. Pixel sets matched the original exactly, values to 1 ulp. The lesson stuck: port the exact algorithm, then validate against the original before removing the original.

## Equivalence, then goldens

During the migration the numpy implementation stayed as a live reference. Tests compared the Rust core against it on every run: 300 of 300 rasterizer matches, 2862 of 2862 identical pull orders on a 7000-iteration search, working canvas equal to 1e-9.

Once nothing in the runtime needed numpy, the reference code became dead weight. Instead of keeping it, the suite froze its outputs: exact rasterizer pixels, measured line checksums, and full pull orders for the full scan and the `-r` subset mode. The goldens pin the same guarantee at a fraction of the code.

## The incremental cache that lost

The idea looked solid. An improvement value depends only on the canvas pixels under its line. Each applied pull changes about 200 pixels, so cache the improvements and invalidate only the lines crossing them through an inverted pixel index.

Implementation preserved results bit for bit, and the golden tests proved the point. The benchmark then showed 0.4x to 0.6x throughput, a regression. Chords cross the whole canvas, so each changed pixel fans out to about 73 candidate lines. Invalidation cost rivalled the plain rescan, and the inverted index added a 6.6 million pair sort.

The code was reverted the same day. Parallel rasterization shipped instead and delivered the real win.

Two more measured rejections on record:

- SIMD and FMA in the scan loop. Gathers block auto-vectorization, and FMA rounding drifts the golden orders.
- The Birsak input-darkening rule from the literature. The accumulate-and-clip model in this code base prefers the current 0.9 factor. Numbers in [tuning.md](tuning.md).

## Dependency count over time

| Stage | Runtime packages |
|---|---|
| original | 25 |
| after rasterizer ports | 2, numpy and pillow |
| after the Rust core | 0, one compiled package |

A bare venv check confirms the final state: `uv sync --no-dev`, then `distributions: ['restring']`, then a full CLI run without numpy anywhere.
