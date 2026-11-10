# T-06 — CI: test workflow on three operating systems

| | |
|---|---|
| Target | Q1 2027 · v1.2.0 |
| Depends on | none |
| Unlocks | T-07 release workflow; safe refactoring for everything else |
| Size | S (under a day) |
| Status | [x] done (0eeb200) |

## Why

The repository has no CI at all (no `.github/` directory). The correctness
model — golden rasterizer pixels, golden pull orders, the numpy AST guard —
is exactly the kind of invariant that only protects the project if it runs on
every push. Today a regression is caught only if the author remembered to run
pytest locally, and only on their OS.

## Current state

- Checks are documented as local commands: `uv run pytest` (46 tests, 1.8 s),
  `uv run ruff check .` (`README.md`, Development).
- Build requirements: uv fetches Python 3.14 (`requires-python = ">=3.14"`,
  `.python-version`) and compiles the Rust core via maturin; a C linker is
  needed for cargo. GitHub-hosted runners (ubuntu/macos/windows) all ship
  compilers — the zig recipe in `docs/architecture.md` is for minimal WSL and
  is **not** needed in CI.
- The compiled module `src/restring/_core.abi3.so` is gitignored; `uv sync`
  builds it, so the workflow needs a Rust toolchain before `uv sync`.
- pyo3 uses `abi3-py312` (`rust/Cargo.toml:12`) — one build covers CPython
  ≥3.12; a single Python version in the matrix is enough for now.

## What to build

1. **Workflow** `.github/workflows/ci.yml`:
   - Triggers: `push` to `main`, all `pull_request`.
   - Matrix: `os: [ubuntu-latest, macos-latest, windows-latest]`.
   - Steps, in order:
     1. `actions/checkout@v4`
     2. `dtolnay/rust-toolchain@stable`
     3. `Swatinem/rust-cache@v2` with `workspaces: rust -> target`
     4. `astral-sh/setup-uv@v5` (installs uv; honors `.python-version` on
        `uv sync`)
     5. `uv sync` (builds `_core.abi3.so` via maturin)
     6. `uv run ruff check .`
     7. `uv run pytest`
   - Concurrency group per ref with `cancel-in-progress: true`.
   - Timeout of 15 minutes per job.
2. **README badge**: status badge row at the top of `README.md`, next to the
   hero picture.
3. **Verify the golden tests hold on all three OSes.** The goldens pin pixel
   and order data, which is platform-neutral (pure integer/float algorithms,
   no threading nondeterminism — chunks reassemble in source order per
   `docs/architecture.md`). If any OS diverges, that is a real bug to fix in
   this task, not a flake to ignore.

## Acceptance criteria

- [ ] A PR that breaks a golden (test it by temporarily perturbing a constant
      in a scratch branch) goes red on all three OSes.
- [ ] Green run completes under 10 minutes per job with warm cache.
- [ ] Badge renders in README.
- [ ] Workflow file commented so a newcomer can extend it for T-07.

## Files touched

`.github/workflows/ci.yml` (new), `README.md`.

## Out of scope

- Wheel building and publishing — T-07 builds on this file.
- Nightly jobs, fuzzing, coverage — nothing in the backlog needs them yet.
