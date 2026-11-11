# ReString playground

A static browser playground: drop a photo, run the greedy search in the
page, download the render. No server, no framework, no bundler — one HTML
file plus the wasm module the build produces.

## Architecture

- `rust/core/` — the platform-neutral core crate (rasterizer, greedy search,
  renderers). The browser uses the same algorithms as the Python package.
- `rust/wasm/` — the wasm-bindgen binding: `load_image` (decode + square
  crop + resample to the 300 px working grid), `generate` (greedy search,
  pulls capped at 1000 for responsiveness, optional center-weight map) and
  `render_png` (PNG bytes for the canvas and the download link).
- `index.html` — vanilla JS: drag-drop file input, sliders, canvas preview,
  PNG download. State lives in memory; photos never leave the machine.
  Styled after the smui Nord theme: Source Code Pro monospace, zero
  radius, surface-0..3 hierarchy, dark and light modes plus five runtime
  accent colors, all persisted in localStorage.

Serial everywhere: the core's thread-parallel line cache has a serial
fallback on wasm (`std::thread::scope` is unavailable on
wasm32-unknown-unknown). A 1000-pull search on the 300 px grid is a few
seconds on a mid-range laptop.

## Build

```bash
rustup target add wasm32-unknown-unknown
cargo install wasm-pack
wasm-pack build rust/wasm --target web --out-dir ../../web/pkg
```

Then serve the directory (browsers refuse module imports from file://):

```bash
python3 -m http.server -d web 8000
```

Offline after first load: the page, the wasm binary and its glue are
same-origin static files, so the browser cache covers a reload without
network.

## Deploy

`.github/workflows/pages.yml` builds the wasm module and publishes `web/`
to GitHub Pages on every push to main.
