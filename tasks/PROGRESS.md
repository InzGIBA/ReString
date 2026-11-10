# Progress log

One line per finished or blocked task, newest at the bottom.

01. done. f53d04d. `--weight` flag ships importance weighting in the production greedy scan, center MSE falls 24 to 28 percent on portraits. tests 52 passed.
02. done. bdaab2b. `--min-chord` flag with dead-end recovery ships default off: the greedy never picks short chords on portraits, thresholds bite past 230 px and cost up to 24 percent MSE (docs/research/min-chord-experiment.md). tests 56 passed.
03. done. a7b1e30. Auto export strength: unset `-s` resolves k/L from the actual pull count, k=104.0 fitted from the sweep data, within 2 percent of hand-tuned at 500 and 2000 pulls; ceiling 0.2 (0.3 measured worse than blank on synthetic). tests 61 passed.
04. done. c23debf. RGB research: working strength 0.05 adopted (13 to 17 percent better MSE on both fixtures), variance budgets and exhaustion rejected, RGB order golden added. tests 62 passed.
05. done. 970c295. Working grid research: keep 300, gains under 3 percent at up to 2.4x time; large-grid wins at strength 0.1 reproduce saturation from mistuned strength. tests 62 passed.
