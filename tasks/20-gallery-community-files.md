# T-20 — Community surface: issue templates, PR template, example gallery

| | |
|---|---|
| Target | Q4 2027 · v2.0.0 |
| Depends on | none |
| Unlocks | lower-friction contributions and issues that can be acted on |
| Size | S (under a day) |
| Status | [ ] not started |

## Why

By Q4 the project should have wheels, a browser demo and a wide feature set —
traffic follows, and first contact becomes the repo's README issues section
and example gallery. Today a bug report arrives without a command line or
image, and the only showcased output is one demo JPEG. The contributing
section asks for focused changes but gives no templates to structure them.

## Current state

- No `.github/` directory (CI arrives in T-06; nothing else is templated).
- Contributing prose lives in `README.md` (Contributing section, 4 steps).
- Visual assets: `assets/demo.jpg`, feature cards, hero/social previews —
  one demo, no parameter variety, no layout variety.
- Examples directory holds the original 2020 course images
  (`examples/*.png`) — historical, not a gallery.

## What to build

1. **Issue templates** (`.github/ISSUE_TEMPLATE/`):
   - `bug_report.yml` (form): restring version (`pip show restring` output
     or git rev), OS, exact command line, expected vs actual, input image
     attach (optional), reproducibility (always/sometimes).
   - `feature_request.md`: problem statement first, proposed solution
     second, and a checkbox "I checked `docs/research/` — this is not a
     closed dead end" (the dead-end table from `tasks/README.md` linked and
     mirrored into the template — protects the project's measurement
     culture from relitigating beam search).
   - `research_idea.md`: the house specialty — question, hypothesis,
     pre-registered success bar, fixture(s) to measure on.
2. **PR template** (`.github/pull_request_template.md`): what/why, the
   measurement or test evidence, docs touched (README/tuning/research),
   goldens re-pinned yes/no (and why if yes).
3. **Gallery** (`examples/gallery/`):
   - `scripts/make_gallery.py` (dev group): renders a fixed grid of
     configurations over the two portrait fixtures — circle vs rect, 300 vs
     2000 pulls, bw/wb/rgb, one star layout and one weighted run (from
     T-13/T-01 if landed; skip gracefully if not) — montages into
     `docs/img/gallery.png` and writes a small JSON manifest of
     configurations;
   - `examples/gallery/README.md` embedding the montage with per-tile
     captions and the exact commands to reproduce each tile;
   - gallery regeneration documented in the Development checks.
4. **README**: Contributing links the templates; a one-line "Show and tell"
   issue label documented for users posting their boards (the physical
   outputs are the project's best advertisement).

## Acceptance criteria

- [ ] All three issue templates render correctly on GitHub (checked in the
      PR by inspection — no YAML schema warnings).
- [ ] `uv run python scripts/make_gallery.py` regenerates the montage and
      manifest deterministically (seeded).
- [ ] Every gallery tile is reproducible by a copy-pasted command in the
      gallery README (tested by pasting three of them).
- [ ] The feature template carries the dead-end checklist with links.

## Files touched

`.github/ISSUE_TEMPLATE/bug_report.yml` (new),
`.github/ISSUE_TEMPLATE/feature_request.md` (new),
`.github/ISSUE_TEMPLATE/research_idea.md` (new),
`.github/pull_request_template.md` (new), `scripts/make_gallery.py` (new),
`examples/gallery/README.md` (new), `docs/img/gallery.png` (generated),
`README.md`.

## Out of scope

- Code of conduct file — adopt one verbatim from Contributor Covenant when
  the first outside contributor arrives, not before.
- Discord/forum channels — GitHub only until overflow.
- Localized (ru/et) templates — English only, matching the docs.
