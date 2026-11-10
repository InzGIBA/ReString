# The `.restring` project format

A `.restring` file stores everything needed to re-render a finished result without re-running the search: the nail layout and the nail-by-nail pull orders. The format is plain JSON, so any tool reads it. This document describes schema version 1.

## Example

```json
{
  "format": "restring-project",
  "version": 1,
  "created": "2027-04-01T12:00:00Z",
  "mode": "bw",
  "config": {
    "grid": 300, "wb": false, "nail_step": 4, "layout": "rect",
    "pull_budget": 2000, "weight": null, "min_chord": null, "random_nails": null
  },
  "nails": [[0, 0], [0, 4]],
  "pull_orders": [[0, 222, 226]],
  "input_digest": "sha256:2ab477ed...",
  "restring_version": "1.3.0"
}
```

## Fields

| Field | Meaning |
|---|---|
| `format` | always `"restring-project"` |
| `version` | schema version, currently 1 |
| `created` | write time, UTC, ISO 8601 |
| `mode` | `"bw"` (one pull order) or `"rgb"` (three per-channel orders) |
| `config.grid` | working grid the nails live on, pixels. An int when square, `[height, width]` otherwise |
| `config.wb` | white thread on black canvas (a render-time choice, kept for faithful re-renders) |
| `config.nail_step` | `-n` value used to build the layout |
| `config.layout` | `"rect"` or `"circle"` |
| `config.pull_budget` | `-l` budget of the search, `null` for run-to-exhaustion |
| `config.weight`, `config.min_chord`, `config.random_nails` | search-time flags, `null` when off |
| `nails` | the layout, `[row, col]` pairs in working-grid pixels, clockwise from the circle's 9 o'clock or the rectangle's top-left corner |
| `pull_orders` | one list of nail indices for B/W, three for RGB. Each list starts at nail 0. RGB lists are padded to equal length: the padding is part of the interleaving contract with `render_rgb` |
| `input_digest` | SHA-256 of the input image bytes, provenance only. The image itself is not stored |
| `restring_version` | the ReString version that wrote the file |

## Re-rendering

The CLI re-renders without a search: `restring --project result.restring -o out.png`. The current `-s` and `-d` apply (unset `-s` resolves from the stored pull count, exactly like a fresh run). `--rgb` must match the stored mode. The render is byte-identical to the original run at the same export flags.

## Compatibility

Version 1 is a promise: files written today keep loading. Future writers add fields; readers ignore unknown fields. A future schema bump raises `version` and this document gains a section for the new version; the loader rejects versions beyond its knowledge with a clear error instead of guessing.
