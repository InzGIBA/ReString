# Progress log

One line per finished or blocked task, newest at the bottom.

01. done. f53d04d. `--weight` flag ships importance weighting in the production greedy scan, center MSE falls 24 to 28 percent on portraits. tests 52 passed.
02. done. bdaab2b. `--min-chord` flag with dead-end recovery ships default off: the greedy never picks short chords on portraits, thresholds bite past 230 px and cost up to 24 percent MSE (docs/research/min-chord-experiment.md). tests 56 passed.
03. done. a7b1e30. Auto export strength: unset `-s` resolves k/L from the actual pull count, k=104.0 fitted from the sweep data, within 2 percent of hand-tuned at 500 and 2000 pulls; ceiling 0.2 (0.3 measured worse than blank on synthetic). tests 61 passed.
04. done. c23debf. RGB research: working strength 0.05 adopted (13 to 17 percent better MSE on both fixtures), variance budgets and exhaustion rejected, RGB order golden added. tests 62 passed.
05. done. 970c295. Working grid research: keep 300, gains under 3 percent at up to 2.4x time; large-grid wins at strength 0.1 reproduce saturation from mistuned strength. tests 62 passed.
06. done. 0eeb200. CI workflow: three-OS matrix (linux, macos, windows), ruff plus pytest, 15 minute timeout. YAML validated locally, the live run is untested until the next push. tests 62 passed.
07. done. 5600c85. Release workflow builds abi3 wheels for five targets plus sdist on a v* tag, publishes via trusted publishing, opens the GitHub Release; requires-python relaxes to 3.12, version sync check in CI. The publish step is untested (no PyPI trusted publisher from this environment). tests 62 passed.
08. done. e7aad1b. `.restring` project format v1: `--project-out` saves layout plus pull orders as JSON, `--project` re-renders byte-identically with no search, loader validates format, version, mode arity and ranges. tests 73 passed.
09. done. 33fa256. Winding poster: A3 landscape SVG with numbered nails, per-thread length (scaled chords, lead-in, 5 percent slack) and stats footer; `--poster` works from a run or from `--project`. Browser visual check stays manual. tests 81 passed.
10. done. 505e1f6. Winding animation: `--anim` writes an animated GIF from a project (raw or downsampled frames, last frame pixel-identical to the full render); gif feature added to the image crate, no new crates. 600 px 2000-pull GIF is 45 MB and 3 s of compute; browser playback check stays manual. tests 86 passed.
