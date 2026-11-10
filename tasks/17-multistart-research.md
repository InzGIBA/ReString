# T-17 — Multi-start greedy (research; expected negative, closing the family)

| | |
|---|---|
| Target | Q3 2027 · v1.4.0 |
| Depends on | none |
| Unlocks | closure of the search-strategy question for good |
| Size | M (1–3 days) |
| Status | [ ] not started |

## Why

Multi-start (run the greedy from several starting states, keep the best run)
is the **only untested member** of the search-strategy family. The family's
record so far: beam search, receding horizon, multi-scale, asymmetric
penalties, add/remove local search — all measured, all no-gain
(`docs/research/lookahead-experiment.md`,
`docs/research/alternatives-experiment.md`). The known killer control is
"the same compute in more threads beats it". A clean multi-start measurement
either finds the first exception or closes the whole family with evidence —
both are worth publishing in the project's voice.

## Current state

- The greedy starts from nail 0 (`pull_order: vec![0]`,
  `rust/src/lib.rs:553`) on a blank canvas; the `-r` subset mode uses a fixed
  seed (42, `seeded_subset`, `rust/src/lib.rs:455`) — two natural start
  axes: starting nail and subset seed.
- `create_art_from` (`rust/src/lib.rs:1278`) already supports resuming a
  search from a given canvas — sufficient machinery for start variations
  without new Rust.
- Negative-result precedent to imitate: the lookahead doc's tone —
  pre-registered controls, the "threads not brains" comparison table, a clear
  mechanism paragraph.

## What to build

1. **Variations under test** (Python orchestration, sequential runs — seconds
   each, parallelism unnecessary for the experiment):
   - S starting nails: S ∈ {2, 4, 8, 16} evenly spread across the nail ring,
     same budget B per run, keep the run with the lowest final working-canvas
     error;
   - S subset seeds: `-r 100` with seeds 42, 43, 44, … (needs a `seed`
     parameter added to `create_art`'s subset call — small Rust addition,
     default 42, goldens untouched);
   - controls at **matched total compute**: greedy with budget B×S threads,
     and greedy with B threads (time-matched too, reported in the table).
2. **Experiment** (`scripts/multistart_experiment.py`): both fixtures, rect
   step 4, B ∈ {500, 1000, 2000}, S as above. Metrics: render MSE (global,
   center), total time. One figure: MSE vs total compute, multistart points
   against the greedy thread-scaling curve from the lookahead doc.
3. **Pre-registered verdict** (written into the doc before running): adopt
   nothing unless multi-start at total budget B×S beats greedy at B×S by
   ≥3% MSE on both fixtures — the lookahead result predicts it will not;
   the doc then states the family closure: "no known search modification
   beats spending the same compute on more threads", listing all six
   negative results in one table.
4. **Deliverable**: `docs/research/multistart-experiment.md`, JSON + figure
   in `docs/img/`. No CLI flag ships from a negative; if the improbable
   positive happens, the doc proposes the flag design and a follow-up task
   is written instead of smuggling a feature into this one.

## Acceptance criteria

- [ ] Script runs end to end and regenerates every artifact it cites.
- [ ] The doc contains the pre-registered bar, the matched-compute control
      table, and a mechanism paragraph (why start diversity does or does not
      matter given the line cache's dense candidate coverage).
- [ ] The family-closure table (six strategies, one verdict) exists and links
      each member's doc.
- [ ] If `seed` was added to the core: default behavior bit-identical,
      goldens pass.

## Files touched

`rust/src/lib.rs` (optional `seed` parameter only),
`scripts/multistart_experiment.py` (new),
`docs/research/multistart-experiment.md` (new), `docs/img/` artifacts.

## Out of scope

- Parallel multi-start in one process (thread pool over runs) — performance
  engineering of a feature that is expected not to ship.
- Hybrid strategies (best-prefix + restart chains) — T-15 keeps its purity;
  combinations reopen only if this task surprises.
