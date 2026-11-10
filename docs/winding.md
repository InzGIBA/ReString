# Winding guide

The poster turns a finished result into physical work: numbered nails on a printed sheet, the winding sequence in your hand, and the thread length before you buy anything.

## From render to poster

```bash
restring -i portrait.png -o out.png --rect -l 2000 --project-out result.restring --poster poster.svg
```

`--poster` works in the same invocation as a normal run, or later from the project alone:

```bash
restring --project result.restring --poster poster.svg
```

Flags: `--canvas-size` sets the board size in millimeters (default 260, must fit the A3 landscape page), `--number-every` sets nail numbering density (default: every 10th nail, `1` = all, `0` = none), `--poster-preview` draws the pattern at 10 percent opacity.

## Printing checklist

- Print at 100 percent scale, no "fit to page", no shrink. The SVG carries its dimensions in millimeters; a scaled print moves every nail.
- Check the print with a ruler: the board edge must measure exactly `--canvas-size` millimeters.
- The board rectangle on the poster equals the physical board. Nail positions sit inside the outline; the starting nail is the red-ringed circle at the top-left corner (rectangle layout) or at 9 o'clock (circle layout).
- Numbers appear every Nth nail in nail-list order. Pull index N in the project file points at nail N on the poster, so the two references never disagree.

## Thread buying

The footer prints the thread length per thread at the chosen board size, including 2 x 150 mm lead-in tails and a 5 percent handling slack. Buy 20 percent more than the footer says: knots, tension mistakes and re-winds eat margin. Real boards historically needed 1 to 2 km of thread; the number scales linearly with `--canvas-size`.

RGB projects use three threads, one per channel. The footer lists the three lengths separately; the nail numbering is shared. The three channels wind interleaved: pull N of the combined sequence uses channel `N mod 3`, in R, G, B order.
