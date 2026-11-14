# ReString playground

A static browser playground: drop a photo, watch the greedy search wind the
thread live, pick a palette, save the project, print the poster, download
the GIF, then wind it for real in the step-by-step assistant. No server, no
framework, no bundler — static HTML plus the wasm module the build produces.

## Architecture

- `rust/core/` — the platform-neutral core crate (rasterizer, greedy search,
  renderers). The browser uses the same algorithms as the Python package.
  `Search` is the chunked search state: build once, step many times, render
  previews in between; multi-thread runs share one line cache (`SearchSetup`).
- `rust/wasm/` — the wasm-bindgen binding:
  - `load_image` — decode + square crop + resample to the 300 px working grid;
  - `WasmSearch` — chunked search, one core search per thread color.
    `step(n)` advances, `render_png` draws the current state, `quality_json`
    reports MSE/SSIM against the photo, `orders_json` exports the winding,
    `animation_gif` encodes the winding GIF in memory. Palettes: built-in
    rgb/cmy/cmyk or a JSON color list; black-on-white and white-on-black;
  - `generate` / `render_png` — the one-shot compatibility surface;
  - `render_project` — re-render a `.restring` project JSON without a search.
- `worker.js` — the search runs in a Web Worker. It streams preview frames
  and progress between chunks, honors cancel, and keeps the finished search
  alive for on-demand GIF encoding. The main thread never blocks.
- `index.html` — vanilla JS: drag-drop input, layout and palette controls
  (including a custom JSON palette), sliders, live canvas preview with a
  before/after compare slider, progress and cancel, stats (pulls, nails,
  seconds, MSE, SSIM). Downloads: PNG, `.restring` project (schema v2),
  winding CSV/TXT, numbered-nail poster SVG, winding GIF. Saved projects
  load back for re-render and export. Styled after the smui Nord theme:
  Source Code Pro monospace, zero radius, surface-0..3 hierarchy, dark and
  light modes plus five runtime accent colors, persisted in localStorage.
- `poster.js` — the browser twin of `restring.poster`: A3 poster SVG with
  numbered nails and thread lengths, plus the CSV/TXT winding exports.
- `wind.html` — the winding assistant: load a `.restring` project (or take
  the handoff from the playground), step through the pulls with buttons or
  arrow keys, the board highlights the current chord, threads wind one after
  another, and the session survives a reload via localStorage.

Serial everywhere: the core's thread-parallel line cache has a serial
fallback on wasm (`std::thread::scope` is unavailable on
wasm32-unknown-unknown). A 3000-pull search on the 300 px grid is a few
seconds on a mid-range laptop, streamed as live progress.

## Build

```bash
rustup target add wasm32-unknown-unknown
cargo install wasm-pack
wasm-pack build rust/wasm --target web --out-dir ../../web/pkg
```

Without wasm-pack, the same output comes from cargo plus wasm-bindgen
(version-matched to the crate in `rust/wasm/Cargo.lock`):

```bash
cd rust/wasm
cargo build --release --target wasm32-unknown-unknown
wasm-bindgen --target web --out-dir ../../web/pkg \
    target/wasm32-unknown-unknown/release/restring_wasm.wasm
```

Then serve the directory (browsers refuse module imports from file://):

```bash
python3 -m http.server -d web 8000
```

Smoke the binding in Node before shipping (the pages workflow runs this):

```bash
cp web/pkg/restring_wasm.js web/pkg/restring_wasm.mjs
node scripts/wasm_smoke.mjs
```

Offline after first load: the page, the wasm binary and its glue are
same-origin static files, so the browser cache covers a reload without
network.

## Deploy

`.github/workflows/pages.yml` builds the wasm module and publishes `web/`
to GitHub Pages on every push to main.