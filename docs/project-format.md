# The `.restring` project format

A `.restring` file stores everything needed to re-render a finished result without re-running the search: the nail layout and the nail-by-nail pull orders. The format is plain JSON, so any tool reads it. This document describes schema versions 1 and 2.

## Example

```json
{
  "format": "restring-project",
  "version": 2,
  "created": "2026-11-11T12:00:00Z",
  "mode": "bw",
  "config": {
    "grid": 300, "wb": false, "nail_step": 4, "layout": "rect",
    "pull_budget": 2000, "weight": null, "min_chord": null, "random_nails": null,
    "seed": null
  },
  "nails": [[0, 0], [0, 4]],
  "pull_orders": [[0, 222, 226]],
  "input_digest": "sha256:2ab477ed...",
  "restring_version": "2.0.1"
}
```

## Fields

| Field | Meaning |
|---|---|
| `format` | always `"restring-project"` |
| `version` | schema version, 1 or 2. Writers emit 2 |
| `created` | write time, UTC, ISO 8601 |
| `mode` | `"bw"` (one pull order), `"rgb"` (three per-channel orders) or `"palette"` (K orders with stored colors, version 2) |
| `palette` | version 2, mode `"palette"` only: one `{"name", "rgb": [r, g, b]}` entry per pull order, floats 0..1, same convention as palette files |
| `config.grid` | working grid the nails live on, pixels. An int when square, `[height, width]` otherwise |
| `config.wb` | white thread on black canvas (a render-time choice, kept for faithful re-renders) |
| `config.nail_step` | `-n` value used to build the layout |
| `config.layout` | the layout spec used to build the nails |
| `config.pull_budget` | `-l` budget of the search, `null` for run-to-exhaustion |
| `config.weight`, `config.min_chord`, `config.random_nails`, `config.seed` | search-time flags, `null` when off |
| `nails` | the layout, `[row, col]` pairs in working-grid pixels, clockwise from the circle's 9 o'clock or the rectangle's top-left corner |
| `pull_orders` | one list of nail indices for B/W, three for RGB, K for palette. Each list starts at nail 0. Multi-thread lists are padded to equal length: the padding is part of the interleaving contract with `render_rgb` / `render_palette` |
| `input_digest` | SHA-256 of the input image bytes, provenance only. The image itself is not stored |
| `restring_version` | the ReString version that wrote the file |

## Re-rendering

The CLI re-renders without a search: `restring --project result.restring -o out.png`. The current `-s` and `-d` apply (unset `-s` resolves from the stored pull count, exactly like a fresh run). `--rgb` must match the stored `"rgb"` mode; `"palette"` projects carry their colors in the file and re-render without extra flags. The render is byte-identical to the original run at the same export flags.

## Version 2

Version 2 adds the `"palette"` mode: any thread palette (cmy, cmyk, a custom floss JSON) saves with its colors, so the poster, the animation and the re-render all reproduce the original run. The `"bw"` and `"rgb"` modes are unchanged; a version 2 file without a `palette` field carries the same information as version 1.

## Compatibility

Version 1 is a promise: files written today keep loading. Future writers add fields; readers ignore unknown fields. A future schema bump raises `version` and this document gains a section for the new version; the loader rejects versions beyond its knowledge with a clear error instead of guessing.
