# T-19 — Public API 2.0: one-call facade

| | |
|---|---|
| Target | Q4 2027 · v2.0.0 |
| Depends on | none (synergy: T-08's Project and this task's Result serialize into each other, but neither requires the other) |
| Unlocks | library adoption; a stable contract to document |
| Size | M (1–3 days) |
| Status | [x] done (05fe851) |

## Why

The README's "As a library" example needs **six imports across four modules**
and manual pipeline assembly (`_core.Image.load` → `largest_square` →
`resize` → `create_*_nail_positions` → `generate_bw` → `save_png`). The
package's real export list is three functions (`src/restring/__init__.py`),
and the docs tell users to copy numpy bridge helpers from scripts. For v2 the
library needs one obvious call, typed and documented, that does what the CLI
does — and internal modules should stop being quasi-public.

## Current state

- Public: `Config`, `generate_bw`, `generate_rgb` (`__init__.py:3-7`).
- The pipeline lives implicitly in `cli.py:main` (`src/restring/cli.py:31`):
  load → square/resize (only when `-r1 == -r2 == 1`, an inconsistency worth
  fixing in passing) → nails → generate → save.
- Q1–Q3 tasks add flags (weight, min-chord, rollback, palettes, layouts) —
  by Q4 the Config surface is wide and uneven; the facade is the chance to
  make one coherent shape for it.
- No type checker discipline: no `py.typed`, annotations are partial.

## What to build

1. **Facade** (`src/restring/api.py`, re-exported from `__init__`):
   ```python
   @dataclass(slots=True)
   class GenerateOptions:
       layout: Layout = "rect"            # str spec or Layout object
       nail_step: int = 4
       pulls: int | None = None           # None = run to exhaustion
       strength: float | None = None      # None = auto (T-03 rule)
       palette: str | Path = "bw"         # "bw" | "wb" | "rgb" | palette file (T-12)
       grid: int = 300
       export_size: int = 300
       weight: float | None = None        # T-01
       min_chord: float | None = None     # T-02
       rollback: bool = False             # T-15

   @dataclass(slots=True)
   class Result:
       image: Image                       # _core.Image, save_png available
       pull_orders: list[list[int]]
       nails: list[tuple[int, int]]
       options: GenerateOptions           # resolved, post-defaults
       stats: Stats                       # pulls per thread, elapsed, nails

   def generate(source: str | Path | bytes | Image, options=...) -> Result
   ```
   The old three functions stay as thin deprecated wrappers (`
   DeprecationWarning`, removed in 3.0) delegating to the facade —
   zero breakage for existing users within 2.x.
2. **CLI rewrite on the facade**: `cli.py:main` collapses to argument parsing
   + `generate()` + save (+ project/metrics/poster hooks from other tasks if
   they landed). Behavior and flags unchanged — the README's documented
   commands keep working; this is an internal refactor with a public-API
   payoff. The `-r1/-r2` inconsistency (square-crop skipping, `cli.py:50`)
   becomes an explicit documented behavior of the layout, not a silent
   special case.
3. **Typing and packaging**: `py.typed` marker; full annotations on the
   facade; the numpy-bridge helpers that scripts copy move from
   `scripts/_bridge.py` into the dev group as a documented import path
   (runtime stays numpy-free — the AST guard keeps enforcing it).
4. **Docs**: `docs/api.md` — the facade, the options table, three examples
   (minimal, portrait preset, project round-trip); README "As a library"
   collapses to 3 lines; a public-contract test file
   (`tests/test_public_api.py`) that fails on any breaking signature or
   name change to the facade.
5. **Version**: this ships as 2.0.0 together with Q4 items; `__all__` grows
   to the facade names; deprecation notes in the release notes.

## Acceptance criteria

- [ ] The README library example is ≤3 lines and needs one import.
- [ ] `tests/test_public_api.py` pins every facade signature, default and
      Result field — the contract is executable.
- [ ] Old API (`generate_bw`/`generate_rgb`/`Config`) still works with a
      deprecation warning; all existing tests pass unmodified.
- [ ] CLI behavior identical (the CLI e2e suite is the proof).
- [ ] `py.typed` shipped; mypy or pyright in clean mode on `src/restring`
      reports no facade errors (add as a CI advisory step, non-blocking on
      the rest of the codebase).

## Files touched

`src/restring/api.py` (new), `src/restring/__init__.py`,
`src/restring/cli.py`, `pyproject.toml` (py.typed packaging),
`tests/test_public_api.py` (new), `docs/api.md` (new), `README.md`,
`scripts/_bridge.py`.

## Out of scope

- Plugin interfaces for third-party layouts/metrics — the facade makes them
  possible later; designing them now, without a second consumer, is
  speculation.
- Async API, progress callbacks — nothing needs them until a GUI exists.
- Removing the deprecated wrappers (3.0 decision).
