# T-18 — Core crate split and WASM browser demo

| | |
|---|---|
| Target | Q4 2027 · v2.0.0 |
| Depends on | none |
| Unlocks | zero-install playground; the demo that sells the project |
| Size | L (a week or more) |
| Status | [ ] not started |

## Why

`pip install` (T-07) still asks for a terminal. The demo that converts
bystanders into users is a browser page: drop a photo, get string art, watch
it wind. The Rust core is dependency-light (`pyo3`, `image` with png/jpeg) —
the algorithms are platform-neutral; only the pyo3 binding is not. This task
splits the algorithmic core into a plain crate, binds it to wasm, and ships a
static playground.

## Current state

- Everything lives in `rust/src/lib.rs` (1453 lines): algorithms
  (`zingl_line`, `ellipse_perimeter`, `build_sources`, `create_art` and
  friends, renders, metrics, `Image`) **interleaved with pyo3 macros**
  (`#[pyfunction]`, the `#[pymodule]` at `rust/src/lib.rs:1434`).
- The build is maturin-shaped: `[tool.maturin] python-source = "src",
  module-name = "restring._core"` (`pyproject.toml:41-43`); `Cargo.toml`
  declares `crate-type = ["cdylib"]`.
- `create_art` parallelizes the cache build with `std::thread::scope`
  (`rust/src/lib.rs:537`) — **not available on wasm32-unknown-unknown**;
  a single-threaded path is needed there (300-grid cache build serializes in
  well under a second of native-equivalent work).
- `image` crate PNG decode/encode works on wasm; JPEG too.

## What to build

1. **Crate split** (behavior-preserving, goldens prove it):
   - new `rust/core/` crate `restring-core`: everything except pyo3 —
     `Image`, codecs wrappers, layouts, `zingl_line`, line cache, searches,
     renders, metrics, as plain `pub fn`s; the parallel cache build behind
     `#[cfg(not(target_family = "wasm"))]` with a serial fallback for wasm;
   - `rust/` (the maturin crate) becomes a thin pyo3 shim re-exporting the
     core to Python; `[tool.maturin]` gains `manifest-path = "rust/Cargo.toml"`
     if the layout requires it — the Python-visible module name
     `restring._core` must not change;
   - a workspace `rust/Cargo.toml` tying the crates together.
   **This refactor must leave every golden green and benchmarks within
   noise** — it is a move, not a rewrite. Run the full suite and
   `scripts/benchmark.py --label split` to prove it.
2. **WASM binding** (`rust/wasm/` crate `restring-wasm`, `wasm-bindgen`,
   target `web`): an API shaped for JS:
   - `load_image(bytes: &[u8]) -> WasmImage` (png/jpeg decode),
   - `generate(image, opts) -> WasmArt` where opts = layout, nail_step,
     pulls (cap 1000 for interactivity), strength, weight; runs the serial
     `create_art`;
   - `render_png(art, size_px) -> Vec<u8>` — the rendered PNG bytes.
   Deterministic, no threads, no panic across the boundary (errors as
   `Result<_, JsError>`).
3. **Playground** (`web/`, vanilla JS + one HTML file, no framework, no
   bundler — `wasm-pack build --target web` output committed or fetched):
   file input (drag-drop), sliders for pulls/nail_step/strength, layout
   select, live preview canvas (~600 px), render button with progress
   indication, PNG download. Budget guard: pulls ≤ 1000, grid 300 — the page
   must stay responsive on a mid-range laptop.
4. **Publishing**: `.github/workflows/pages.yml` — build wasm + deploy
   `web/` to GitHub Pages on push to main. README gets a demo link and a
   screenshot.
5. **Docs**: `web/README.md` (architecture, build, why no framework);
   `docs/architecture.md` gains a "Targets" section (CPython via pyo3, wasm
   via wasm-bindgen, shared core).

## Acceptance criteria

- [ ] After the split: `uv run pytest` green, all goldens untouched,
      benchmark within noise of the pre-split label.
- [ ] `wasm-pack build rust/wasm --target web` succeeds in CI.
- [ ] The deployed page loads a user photo and produces a 1000-pull render
      in under 10 s on a mid-range laptop (checked manually, noted in PR).
- [ ] The Python package still builds via maturin and imports as
      `restring._core` with the same API.
- [ ] Playground works offline after first load (cache headers / inlined
      assets as practical).

## Files touched

`rust/core/` (new crate), `rust/wasm/` (new crate), `rust/Cargo.toml`
(workspace + shim), `pyproject.toml` (manifest path if moved), `web/` (new),
`.github/workflows/pages.yml` (new), `docs/architecture.md`, `README.md`.

## Out of scope

- Web workers / SharedArrayBuffer parallelism in the browser — serial
  preview first.
- Server-side rendering API, Docker images — the playground is static.
- Video/GIF export in the browser (T-10's Rust code compiles to wasm later
  if demand appears).
