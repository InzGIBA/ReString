# Task backlog 2027

Self-contained technical tasks derived from the 2027 roadmap. Each file is a
complete work order: context, current state with code anchors, a build spec,
acceptance criteria and explicit out-of-scope notes. A contributor (human or
agent) needs only the task file and the repository to start.

## How to work with the backlog

- Tasks are **independent by design**. Pick any task whose `Depends on` row is
  empty, in any order. Do not chain tasks by hidden assumptions — if a task
  needs something that does not exist, that is a dependency and it is listed.
- Where a real dependency exists, the prerequisite task is numbered first
  (07 needs 06; 09 and 10 need 08).
- Every task follows the project's measurement culture: research questions get
  a `docs/research/*.md` document with numbers before any flag ships.
- Definition of done for every task (not repeated in each file):
  1. `uv run pytest` green (46+ tests, no golden drift unless the task says
     otherwise).
  2. `uv run ruff check .` clean.
  3. Documentation updated (README table row, `docs/tuning.md` or a research
     doc) — a feature without a measurement is not done.
  4. Runtime package stays dependency-free (`tests/test_no_runtime_numpy.py`
     is the guard; stdlib is allowed, pip packages are not).

## Dead ends — closed by measurement, do not reopen

These were implemented, measured and rejected with numbers. A new attempt
needs a new hypothesis, not persistence.

| Idea | Verdict | Evidence |
|---|---|---|
| Beam search / receding horizon | Same MSE as greedy at 5–500x the time | docs/research/lookahead-experiment.md |
| Multi-scale coarse-to-fine | MSE up to 5x worse | docs/research/alternatives-experiment.md |
| Asymmetric over-darkening penalty | No measurable effect | docs/research/alternatives-experiment.md |
| SIMD/FMA in the scan loop | Breaks float rounding, freezes goldens | docs/architecture.md, Performance |
| Incremental improvement cache | 0.4–0.6x throughput, invalidation fan-out | docs/architecture.md, Performance |
| Add/remove local search | No gain | docs/research/alternatives-experiment.md |

## Index

| # | Task | Target | Depends on | Size | Done |
|---|---|---|---|---|---|
| [01](01-importance-weight-flag.md) | `--weight` importance-weighting flag | Q1 · v1.2.0 | — | M | ✅ |
| [02](02-min-chord-distance.md) | `--min-chord` minimum chord distance | Q1 · v1.2.0 | — | M | ✅ |
| [03](03-auto-export-strength.md) | Auto export strength (`-s` from pull count) | Q1 · v1.2.0 | — | M | ✅ |
| [04](04-rgb-channel-sweeps.md) | RGB per-channel sweeps (research) | Q1 · v1.2.0 | — | M | ✅ |
| [05](05-working-grid-scale.md) | Working grid above 300 px (research + flag) | Q1 · v1.2.0 | — | M | ✅ |
| [06](06-ci-test-workflow.md) | CI: test workflow, three OSes | Q1 · v1.2.0 | — | S | ✅ |
| [07](07-pypi-release-wheels.md) | PyPI wheels + tag release workflow | Q1 · v1.2.0 | 06 | M | ✅ |
| [08](08-pull-order-project-format.md) | `.restring` project format + order export | Q2 · v1.3.0 | — | M | ✅ |
| [09](09-winding-poster-svg.md) | Winding poster SVG + thread length | Q2 · v1.3.0 | 08 | M | ✅ |
| [10](10-winding-animation-gif.md) | Winding animation GIF | Q2 · v1.3.0 | 08 | M | ✅ |
| [11](11-thread-thickness-render.md) | Physical thread-thickness render | Q2 · v1.3.0 | — | M | ✅ |
| [12](12-thread-palette-system.md) | Thread palette system (CMYK, real floss) | Q2 · v1.3.0 | — | L | ✅ |
| [13](13-custom-nail-layouts.md) | Custom nail layouts (polygon, star, rings, SVG) | Q3 · v1.4.0 | — | M | ✅ |
| [14](14-adaptive-nail-placement.md) | Adaptive nail placement (research) | Q3 · v1.4.0 | — (synergy with 13) | M |
| [15](15-best-prefix-rollback.md) | Best-prefix rollback on stagnation | Q3 · v1.4.0 | — | S |
| [16](16-blurred-ssim-metric.md) | Blurred SSIM + `--metrics` report | Q3 · v1.4.0 | — | S |
| [17](17-multistart-research.md) | Multi-start greedy (research, likely negative) | Q3 · v1.4.0 | — | M |
| [18](18-wasm-browser-demo.md) | Core crate split + WASM browser demo | Q4 · v2.0.0 | — | L |
| [19](19-public-api-v2.md) | Public API 2.0 facade | Q4 · v2.0.0 | — (synergy with 08) | M |
| [20](20-gallery-community-files.md) | Issue templates, PR template, gallery | Q4 · v2.0.0 | — | S |

Size legend: S = under a day, M = 1–3 days, L = a week or more.
