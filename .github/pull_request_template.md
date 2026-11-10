<!--
Delete the sections that do not apply. Keep the change focused: one idea per PR.
-->

## What and why

What does this PR change, and what problem does it solve? Link the issue or task file (`tasks/NN-*.md`) if one exists.

## Evidence

Pick the section that fits:

- **Bug fix:** the command line before/after, and what the fixed output shows.
- **Feature:** how you know it works (test names, manual steps).
- **Quality claim:** the measurement. Fixtures, metric, before/after numbers, and the doc added under `docs/research/`. Claims without numbers do not merge.
- **Refactor:** proof of behavior preservation (goldens green, benchmark within noise).

## Docs

- [ ] README updated
- [ ] `docs/tuning.md` or a research doc updated
- [ ] Flag/reference table rows match the new behavior

## Tests

- [ ] `uv run pytest` green
- [ ] `uv run ruff check .` clean
- [ ] New behavior covered by new tests (never by weakening existing ones)

## Goldens

- [ ] Existing goldens untouched
- [ ] Goldens re-pinned on purpose — explain why the change is behavior-visible and intended, and paste the old vs new values:
