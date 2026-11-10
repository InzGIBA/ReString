# T-12 — Thread palette system: CMYK, real floss colors, K threads

| | |
|---|---|
| Target | Q2 2027 · v1.3.0 |
| Depends on | none (T-04's numbers refine the defaults later; not required) |
| Unlocks | colored string art with buyable thread |
| Size | L (a week or more) |
| Status | [ ] not started |

## Why

RGB mode paints three threads in pure red, green and blue
(`rust/src/lib.rs:972`) — colors no shop sells as thread. Real color string
art (precedent: roy-hachnochi's 360-nail CMY-log-blend, Demoussel's color
runs) uses cyan/magenta/yellow or actual embroidery floss (DMC/Anchor sell
~500 shades). A palette abstraction replaces the hard-coded triple with any
set of K thread colors, separating "which threads do I own" from the search.

## Current state

- `generate_rgb` (`src/restring/generator.py:41`): three greedy runs — one
  per RGB channel of the target — orders padded and interleaved.
- `render_rgb` (`rust/src/lib.rs:966`): fixed `colors: [[1,0,0],[0,1,0],[0,0,1]]`,
  additive-on-white accumulation per thread, clamp at the end.
- `--rgb` / `--wb` CLI flags (`src/restring/cli.py:26-27`).
- The image crate handles color; targets decompose via `Image.channel`
  (`rust/src/lib.rs`, Image methods). No subtractive separation exists.

## What to build

1. **Palette representation.** `Palette = list[ThreadColor]`,
   `ThreadColor = {name, rgb: (float, float, float)}`. Built-ins
   (`src/restring/palettes.py`): `rgb` (today's triple — compatibility),
   `cmy` (3), `cmyk` (4). Loader `load_palette(path)` for JSON palette files
   (`[{"name": "DMC 310", "rgb": [0.0, 0.0, 0.0]}, ...]`, sRGB 0–1, stdlib
   json). Ship `examples/palettes/dmc-starter.json` with ~20 curated grays/
   skin/earth tones and a comment header crediting community DMC charts.
2. **Color separation (Python, in `generator.py`).** For K threads, decompose
   the target into K single-thread gray targets: project each target pixel's
   RGB onto each thread color (dot product / rgb normalization — the classic
   CMYK separation generalized). For `cmy`/`cmyk` built-ins this reproduces
   channel separation; for arbitrary palettes it yields per-thread intensity
   maps. Run the existing greedy once per thread target on the shared nails,
   pad and interleave — the proven `generate_rgb` structure, K instead of 3.
3. **Rust: generalized renderer.** `render_palette(orders, nails,
   colors: Vec<(f64, f64, f64)>, strength, in_w, in_h, out_w, out_h, white)
   -> Image` — `render_rgb` with the colors array as a parameter. Keep
   `render_rgb` as a thin wrapper (compatibility + goldens).
4. **CLI.** `--palette <name|path.json>`; `--rgb` becomes sugar for
   `--palette rgb` (both accepted, `--rgb` wins if both given, logged).
   `--wb` stays orthogonal (canvas polarity). Cap K at 8 with a clear error —
   line cache cost is per-run K × today's RGB cost, and 8 × 3000 pulls is
   already a long run.
5. **Measurement** (`scripts/palette_experiment.py`): both fixtures, equal
   **total** pull budgets (e.g. 3000 split across threads), rgb vs cmy vs
   cmyk vs dmc-starter. Metrics: color MSE, per-thread pull counts, time.
   Pre-registered bar: a palette ships as recommended only on ≥5% color MSE
   improvement over `rgb` at equal budget. Doc:
   `docs/research/palette-experiment.md`.
6. **Tests**: palette loading + validation (bad JSON, out-of-range rgb);
   separation unit test (pure red target → R thread target is red, others
   near zero); cmyk e2e; `render_palette` goldens for a seeded tiny case;
   K > 8 rejected; `--rgb` unchanged (existing goldens).

## Acceptance criteria

- [ ] `--palette cmyk` runs end to end and measurably beats `--rgb` at equal
      total budget on fixtures, or the doc records why it does not and cmyk
      stays non-recommended.
- [ ] Custom palette JSON loads; dmc-starter produces a distinct, valid art
      render (e2e + eyeball check in PR).
- [ ] `--rgb` path is behavior- and pixel-identical to v1.2 (goldens).
- [ ] Zero runtime pip dependencies; palettes are data, not code.

## Files touched

`rust/src/lib.rs`, `src/restring/palettes.py` (new),
`src/restring/generator.py`, `src/restring/canvas.py`, `src/restring/cli.py`,
`examples/palettes/dmc-starter.json` (new), `scripts/palette_experiment.py`
(new), `docs/research/palette-experiment.md` (new), tests, `README.md`,
`docs/tuning.md`.

## Out of scope

- Optimal least-squares palette subset selection ("choose the best 4 of 500
  DMC colors for this photo") — a good follow-up task once palettes exist.
- Gamut mapping or ICC color management — sRGB in, approximation out.
- Multi-thread blending physics on the board (overlapping threads) — additive
  model only, consistent with today's RGB.
