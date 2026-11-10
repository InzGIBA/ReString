# T-13 — Custom nail layouts: polygon, star, multi-ring, SVG, explicit list

| | |
|---|---|
| Target | Q3 2027 · v1.4.0 |
| Depends on | none |
| Unlocks | T-14 (adaptive placement composes with these); non-square art |
| Size | M (1–3 days) |
| Status | [x] done (d10f7e2) |

## Why

Two shapes only — ellipse and rectangle border — is the most visible
limitation for a new user (`docs/tuning.md`, `README.md` Features). String
art on stars, hearts, multi-ring boards and custom outlines is common in the
maker community, and the core accepts **any** nail list: layouts are pure
Python-side data. No Rust changes needed.

## Current state

- Nails enter the pipeline as `list[(r, c)]` in working-grid pixels;
  `create_art` and the renderers treat them as opaque points
  (`rust/src/lib.rs:512`, `:938`). The line cache is built from the nail list
  itself — any geometry works, including rings (pulls between rings are just
  long chords).
- `src/restring/nails.py` wraps the only two generators:
  `create_circle_nail_positions` (ellipse perimeter, sorted clockwise from
  9 o'clock, `rust/src/lib.rs:390`) and `create_rectangle_nail_positions`
  (border, clockwise from top-left, `rust/src/lib.rs:409`).
- CLI picks between them with `--rect` (`src/restring/cli.py:27`).

## What to build

1. **Builders in `src/restring/layouts.py`** (pure Python; output sorted
   clockwise from the centroid's 9 o'clock, matching the circle convention —
   a stable, documented ordering rule for all layouts):
   - `polygon(shape, sides: int, count: int)` — regular n-gon perimeter;
   - `star(shape, points: int, inner_radius: float, count: int)` —
     alternating outer/inner radius;
   - `rings(shape, specs: list[(radius_fraction, count)])` — concentric
     rings, concatenated ring by ring, each ring clockwise; pulls between
     rings allowed by construction;
   - `from_svg(path, shape, count)` — sample `count` points along the
     combined path data of `<polygon>`, `<polyline>`, `<rect>`, `<circle>`
     and `<path>` restricted to `M`/`L`/`Z` commands (documented limitation:
     curves unsupported; stdlib `xml.etree` only);
   - `explicit(nails: list[(r, c)])` — pass-through with bounds validation,
     the escape hatch for generated layouts.
   Each builder validates: count ≥ 3, coordinates inside the grid, no exact
   duplicates (dedupe with a warning — duplicate nails create zero-length
   lines).
2. **CLI.** `--layout <spec>` with a mini-grammar:
   `circle | rect | polygon:5 | star:5:0.55 | rings:1.0:200,0.6:120 |
   svg:outline.svg`. `--rect` and the ellipse multipliers `-r1/-r2` keep
   working (`rect` → `--layout rect`, multipliers apply to circle only, as
   today). `--nail-step` stays the circle/rect density dial; the new layouts
   take explicit counts instead — document the difference in the flag table.
3. **Non-square boards**: `polygon`/`star`/`rings` accept the working shape;
   the CLI currently forces a square via `largest_square` (`cli.py:50-51`) —
   layouts may specify `aspect` so the input crop becomes
   `largest_rect(aspect)` (small pure-Python helper over existing
   `Image.resize`; no core changes).
4. **Tests**: builder invariants (count, bounds, clockwise order, no
   duplicates) for every layout; `from_svg` on a committed fixture file;
   end-to-end `create_art` run on each layout (small grid, seeded) returning
   a valid non-empty order; CLI e2e for the spec grammar including errors
   (`star:2` → argparse error, not a stack trace).
5. **Docs**: `docs/layouts.md` with ASCII diagrams of each layout, the
   ordering convention, and nail-count guidance (the tuning guide's
   "844 nails buy 6%" logic transfers); README feature bullet.

## Acceptance criteria

- [ ] All five builders produce valid nail sets the unmodified core searches
      and renders end to end.
- [ ] `--layout star:5:0.55` on the demo portrait yields a star-board render
      in the PR (eyeball) plus an automated small-grid equivalent.
- [ ] `--rect` behavior unchanged; existing goldens untouched.
- [ ] SVG import handles the documented element subset and fails with a
      clear message on curves.

## Files touched

`src/restring/layouts.py` (new), `src/restring/cli.py`,
`src/restring/image_transformations.py` (aspect helper), `tests/layouts/`
(new), `tests/data/star_outline.svg` (new fixture), `docs/layouts.md` (new),
`README.md`, `docs/tuning.md`.

## Out of scope

- Interior nails (nails not on a outline — different search geometry and
  winding ergonomics; needs its own experiment).
- Bezier/arc SVG paths.
- Layout auto-selection from the photo ("pick the best shape") — far-future
  idea, no evidence base yet.
