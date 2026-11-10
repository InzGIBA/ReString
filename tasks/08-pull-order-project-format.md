# T-08 — `.restring` project format and pull-order export

| | |
|---|---|
| Target | Q2 2027 · v1.3.0 |
| Depends on | none |
| Unlocks | T-09 (poster), T-10 (animation), batch rendering, API 2.0 |
| Size | M (1–3 days) |
| Status | [x] done (e7aad1b) |

## Why

The pull order — the nail-by-nail winding sequence — is the product's most
valuable output (Vrellis wound his boards from exactly such instructions), yet
the CLI throws it away: `result, _ = generate_bw(...)` at
`src/restring/cli.py:65`. There is also no way to re-render a result without
re-running the search. A serialization format fixes both and is the
foundation for the poster (T-09) and animation (T-10) tasks.

## Current state

- `generate_bw` / `generate_rgb` already return `(render, pull_order(s))`
  (`src/restring/generator.py:90`, `:68`) — the data exists at the call site.
- A pull order is `list[int]` of nail indices (starting and including the
  initial nail 0; see `create_art`, `rust/src/lib.rs:553`); RGB returns three
  per-channel orders, padded to equal length (`generator.py:53-54`).
- Nails are `list[(row, col)]` in working-grid pixels (`src/restring/nails.py`).
- Rendering from an order already exists and needs no search:
  `pull_order_to_array_bw/rgb` (`src/restring/canvas.py:23`, `:35`).

## What to build

1. **Schema** (JSON, extension `.restring` — plain JSON so any tool can read
   it; document it in `docs/project-format.md`):
   ```json
   {
     "format": "restring-project",
     "version": 1,
     "created": "2027-04-01T12:00:00Z",
     "mode": "bw | rgb",
     "config": { "grid": 300, "wb": false, "nail_step": 4, "layout": "rect",
                 "pull_budget": 2000, "weight": null },
     "nails": [[r, c], ...],
     "pull_orders": [[...], ...],
     "input_digest": "sha256:...",
     "restring_version": "1.3.0"
   }
   ```
   `pull_orders` has one list for B/W, three for RGB (padding kept — it is
   part of the interleaving contract with `render_rgb`).
2. **Serialization module** `src/restring/project.py` (stdlib `json` only —
   the AST guard bans numpy, not stdlib): `save(path, *, mode, config, nails,
   pull_orders, input_digest)` and `load(path)` returning a typed structure
   (dataclass `Project`) with validation: mode/order-count consistency, nail
   indices in range, format version check with a clear error on mismatch.
3. **CLI**:
   - `--project-out <path>` on a normal run: writes the project file next to
     the PNG; the input digest is computed from the loaded file bytes.
   - `--project <path>` as an **input**: replaces `-i`; skips loading,
     preprocessing and search, re-renders with the current `-s`, `-d`
     (overriding the stored render-only fields) and exits. `-i` and
     `--project` together is a CLI error.
4. **Tests**:
   - Round trip: generate → save → load → render is **pixel-identical** to
     the direct render at identical export parameters (both B/W and RGB).
   - Validation errors: truncated order (index out of range), wrong mode
     arity, unknown format version.
   - CLI e2e: both new flags, including that `--project` skips the search
     (assert via runtime or log line).
5. **Docs**: README "Save and re-render" subsection; `docs/project-format.md`
   with the schema and a promise of backward compatibility for version 1.

## Acceptance criteria

- [ ] `uv run restring -i p.png -o out.png --rect -l 2000 --project-out a.restring`
      writes a valid project; `uv run restring --project a.restring -o out2.png`
      reproduces `out.png` byte for byte at default export flags.
- [ ] Round-trip property test in the suite (small grid, seeded).
- [ ] RGB mode round-trips including channel padding.
- [ ] Schema documented and versioned.

## Files touched

`src/restring/project.py` (new), `src/restring/cli.py`,
`tests/test_project.py` (new), `tests/test_cli_e2e.py`,
`docs/project-format.md` (new), `README.md`.

## Out of scope

- Editing/merging project files — read and write only.
- Storing the input image itself in the project (digest only, for provenance).
- A resume-able interrupted search — the format supports it later, nothing in
  this task implements it.
