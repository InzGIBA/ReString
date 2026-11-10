# T-07 — PyPI release: wheels for three platforms, published on tag

| | |
|---|---|
| Target | Q1 2027 · v1.2.0 |
| Depends on | T-06 (CI workflow exists; release job reuses its steps) |
| Unlocks | `pip install restring` — removes the Rust-toolchain barrier |
| Size | M (1–3 days) |
| Status | [ ] not started |

## Why

Today installing ReString requires uv, a Rust toolchain and a C linker
(`README.md`, Requirements). That excludes nearly every casual user. The
project is one `maturin` build away from ordinary `pip install` — pyo3 already
builds abi3 (`abi3-py312`, `rust/Cargo.toml:12`), so one wheel per platform
covers all CPython ≥3.12.

## Current state

- Packaging is maturin-based: `[build-system] requires = ["maturin>=1.5"]`,
  `[tool.maturin] python-source = "src", module-name = "restring._core"`
  (`pyproject.toml:37-43`).
- Runtime has zero pip dependencies (`dependencies = []`) — wheels stay small.
- `requires-python = ">=3.14"` (`pyproject.toml:12`) while abi3 targets 3.12.
  Decide in this task: either relax to `>=3.12` (wheels serve more users) or
  keep 3.14 as the support policy. Recommendation: relax to `>=3.12`; CI (T-06)
  still tests 3.14, and the Python code uses no 3.14-only syntax.
- No release workflow, no PyPI presence, versions bumped by hand
  (`1.1.0` in `pyproject.toml:3` and `src/restring/__init__.py:5`).

## What to build

1. **Release workflow** `.github/workflows/release.yml`:
   - Trigger: push of a tag matching `v*`.
   - Job 1 `test`: the T-06 steps (lint + pytest on ubuntu) — never publish an
     untested tag.
   - Job 2 `build` (needs `test`): `PyO3/maturin-action@v1` in matrix —
     - `linux` targets `x86_64` and `aarch64` (manylinux container, maturin
       handles it),
     - `macos` targets `x86_64` and `aarch64`,
     - `windows` target `x86_64`,
     - plus one `sdist` job (linux).
   - Job 3 `publish`: **PyPI trusted publishing** (configure the publisher for
     the repo on pypi.org — no upload tokens in secrets), then create a
     GitHub Release with `softprops/action-gh-release` attaching the wheels,
     sdist and release notes.
2. **Version hygiene**: single source of truth for the version. Add
   `[tool.maturin]`-compatible or scripted sync so `pyproject.toml`,
   `src/restring/__init__.py` and `rust/Cargo.toml:2` cannot drift — a
   10-line `scripts/check_version_sync.py` called from CI is enough.
3. **README**: rewrite Requirements/Install for two audiences —
   `pip install restring` (no Rust needed) and build-from-source (current
   text moves under a "Development" heading).
4. **Dry run**: publish to TestPyPI first (a second trusted publisher pointed
   at test.pypi.org, one trial tag), verify `pip install --index-url
   https://test.pypi.org/simple restring` in a clean 3.12 and 3.13 venv (3.14
   if available), then the real release.

## Acceptance criteria

- [ ] Tagged release produces wheels: `restring-<v>-cp312-abi3-{manylinux,
      musllinux?}-{x86_64,aarch64}`, `macosx_{x86_64,arm64}`, `win_amd64`,
      plus sdist.
- [ ] `pip install restring` + `restring -i p.png -o out.png --rect` works in
      a clean venv with no Rust toolchain present (verify in a container).
- [ ] Version sync check runs in CI.
- [ ] Release notes and GitHub Release created automatically by the tag.

## Files touched

`.github/workflows/release.yml` (new), `scripts/check_version_sync.py` (new),
`.github/workflows/ci.yml` (version-check step), `pyproject.toml`,
`README.md`.

## Out of scope

- conda-forge, Homebrew — revisit after PyPI proves demand.
- Nightly/RC channels; tags are the only release trigger.
