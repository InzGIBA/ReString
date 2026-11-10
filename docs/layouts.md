# Nail layouts

The core searches and renders any nail list. Built-in generators cover the two classic boards (circle, rectangle border) and four custom layouts: polygon, star, multi-ring and SVG outlines. Everything lives in `src/restring/layouts.py`; all builders return `[(row, col)]` pairs in working-grid pixels.

## Ordering convention

Every layout is ordered clockwise starting at 9 o'clock, relative to the layout's centroid — the same rule as the circle. Nail index N on a poster or in a `.restring` project always means the same nail across tools. Rings are the exception: they concatenate ring by ring, each ring clockwise, so ring 1 keeps its own indices.

## The layouts

```
circle          rect            polygon:5        star:5:0.55      rings:1.0:60,0.6:40
   __              __              ____             ___               ________
  /  \            |  |            /\    /\         /\  /\           ( o o o )
 |    |           |  |           /  \  /  \        \/  \/           (  o o  )
  \__/            |__|           \    \/    /       /\  /\           ( o o o )
                                  \________/        \/  \/           ---------
```

- `polygon:sides[:count]` — regular n-gon perimeter fitted to the working shape, nails at equal arc length. `polygon:5:120` = pentagon with 120 nails (count defaults to 300).
- `star:points:inner[:count]` — star outline with `points` spikes; `inner` is the inner radius as a fraction of the outer (0.55 is the classic 5-point star). `star:5:0.55:150`.
- `rings:r:count,r:count,...` — concentric rings; pulls between rings are ordinary long chords, no special casing in the core. `rings:1.0:200,0.6:120`.
- `svg:file.svg[:count]` — sample nails along the combined outline of an SVG. Supported elements: `polygon`, `polyline`, `rect`, `circle`, and `path` restricted to `M`/`L`/`Z` (absolute or relative). Curves (`C`, `S`, `Q`, `A`, `T`) are unsupported by design; the importer fails with the offending command instead of guessing.
- `@aspect` suffix on any spec: `polygon:5@1.5` crops the input to a centered 1.5 width/height rectangle before the search, for non-square boards.

`circle` and `rect` keep the `-n` density dial and the `-r1`/`-r2` ellipse multipliers (multipliers apply to the circle only, as before). The custom layouts take explicit counts instead of a step — pick the count, not a spacing.

## Nail-count guidance

The tuning guide's rule transfers: going from the default nail step to twice the density buys roughly 6 percent MSE at four times the cost, and every layout saturates in the same 2500 to 2900 thread band at the 300 px working grid. Start at 300 nails for a 300 px grid (`-n 4` on a circle, `--layout polygon:5:300`, `rings:1.0:150,0.7:100,0.45:50`) and add nails only when the render looks under-inked.
