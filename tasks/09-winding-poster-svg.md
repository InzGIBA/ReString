# T-09 — Winding poster: SVG instructions + thread length

| | |
|---|---|
| Target | Q2 2027 · v1.3.0 |
| Depends on | T-08 (`.restring` project format as input) |
| Unlocks | the maker workflow: print, hammer nails, wind |
| Size | M (1–3 days) |
| Status | [ ] not started |

## Why

Birsak et al. wound robots from computer instructions; Vrellis spent 1–2 km of
thread per board. A maker with a printed ReString render still cannot wind
anything: they need numbered nails, the winding sequence, and — before they
start — how many meters of thread to buy. This task turns the pull order into
a printable A-series SVG poster with the statistics on it.

## Current state

- T-08 delivers `Project` objects: `nails` (working-grid pixel coordinates),
  `pull_orders`, mode and config. This task consumes projects — it does not
  re-run searches.
- Physical mapping does not exist anywhere yet: all coordinates are grid
  pixels; there is no canvas size in millimeters.
- SVG is plain XML — generatable with stdlib string templating, keeping the
  zero-dependency runtime intact.

## What to build

1. **Geometry module** `src/restring/poster.py`:
   - `thread_length_mm(project, canvas_size_mm) -> float`: scale factor
     `canvas_size_mm / grid_side` maps grid pixels to millimeters; sum the
     Euclidean distances of consecutive nail pairs across the pull order
     (for RGB: all three orders), multiply by a 1.05 handling-slack factor,
     add 2 × 150 mm lead-in per thread. B/W: one thread; RGB: three.
   - `poster_svg(project, *, canvas_size_mm, number_every, show_preview)
     -> str`.
2. **Poster layout** (SVG 1.1, viewBox in mm, sized for A2/A3 printing —
   parameter, default A3 420×297 landscape):
   - the board area centered at the given canvas size, drawn to scale;
   - nails as 2 mm circles; the starting nail marked distinctly;
   - numbering every Nth nail clockwise (default 10; `0` = none, `1` = all)
     matching the nail list order — the same order the pull indices refer to;
   - optional faint preview of the pattern (the pulls as 0.1-opacity lines)
     toggled off by default — it duplicates the PNG render;
   - a footer block: nail count, pull count(s), total thread length in
     meters, thread count, `restring` version, date.
3. **CLI**: `restring --project art.restring --poster poster.svg
   [--canvas-size 400] [--number-every 10] [--poster-preview]`. Also usable
   in the same invocation as a normal generate run (`--project-out` +
   `--poster` together). Thread length additionally logged at INFO on every
   project write: `Thread length: 512 m`.
4. **Tests**:
   - Thread length: unit test against an independent recomputation on a tiny
     hand-built project (5 nails, known distances) — agreement within 0.1%.
   - SVG: parses as XML (stdlib `xml.etree`), contains the right nail count,
     numbering count, and the footer numbers match the project.
   - CLI e2e: project → poster end to end.
5. **Docs**: README "Wind it for real" section; `docs/winding.md` with a
   printing checklist (100% scale / no "fit to page", nail spacing by canvas
   size, thread buying guidance from the length + 20% margin).

## Acceptance criteria

- [ ] `--poster` produces a valid SVG that renders in a browser and prints at
      true scale (manual check recorded in the PR).
- [ ] Thread length matches an independent recomputation within 0.1%.
- [ ] Nail numbering order equals the nail list order (asserted), so pull
      index N on the poster is unambiguous.
- [ ] RGB projects produce a poster with three thread lengths and one shared
      nail numbering.
- [ ] No new runtime dependencies (AST guard green).

## Files touched

`src/restring/poster.py` (new), `src/restring/cli.py`,
`tests/test_poster.py` (new), `tests/test_cli_e2e.py`, `docs/winding.md`
(new), `README.md`.

## Out of scope

- PDF output — browsers and Inkscape print SVG; revisit on user demand.
- Per-step winding cards / split posters (a "next 200 pulls" pager) — natural
  follow-up if the single poster proves unwieldy in practice.
