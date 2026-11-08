# Related work survey

> Status: verified survey from the pre-Rust era. All facts were checked against primary sources, README files, source code and paper PDFs. The improvement candidates at the end remain open.

Why this survey exists: compare ReString with other generators, extract the empirical rules others follow, and decide what to adopt.

## Where the field comes from

- Petros Vrellis, "A new way to knit", 2016. The artist who started the wave: a 28 inch rim, 200 pegs, one continuous thread pulled 3000 to 4000 times, 1 to 2 km of thread, wound by hand from computer instructions. He never published the algorithm.
- The kaspermeerts gist, 2016. The canonical code most GitHub projects descend from: greedy chord choice, `MAX_LINES=4000`, `N_PINS=288`, `MIN_DISTANCE=20`, `MIN_LOOP=20`, `LINE_WEIGHT=15`.
- Birsak, Rist, Wonka, Musialski, Eurographics 2018. The main academic work: 256 pins on a 630 mm canvas, 0.15 mm thread, a 4096 x 4096 grid, binary least squares with a greedy add and remove solver, an Eulerian path for one uncut thread, robot winding at roughly 5000 loops per 2500 m in 2 hours.
- Demoussel et al., Bridges 2022. A greedy generator with a key finding: a semi-transparent thread at alpha 0.3 beats opaque thread. RMS improves 25 to 30 percent for about 2.4 times the line count.
- The open source projects dissected below: callummcdougall, Hirnmoder, roy-hachnochi, halfmonty, isandrocks, damione1, piellardj, prabinpebam, danielvarga.

## Parameter landscape

| Project | Nails | Threads | Darkness model | Stopping rule |
|---|---|---|---|---|
| Vrellis 2016 | 200 | 3000 to 4000 | thread density, unpublished | none published |
| kaspermeerts gist | 288 | up to 4000 | additive, minus 15 of 255 | fixed budget |
| Birsak EG 2018 | 256 | about 5000, up to 14850 | additive with clamp, z = min(1, sum) | no improving add or remove |
| Demoussel 2022 | 1000 | 2500 to 5000 opaque, 8000 to 10000 at alpha 0.3 | semi-transparent alpha 0.3 | stagnation or RMS threshold |
| danielvarga | 180 | about 12000 | least squares then quantize | fixed budget |
| halfmonty | 300 | up to 4000 | minus 8 of 255 | fixed budget |
| isandrocks | 288 | until SSIM 0.65 | per-pixel error cap plus Sobel edge boost | SSIM above 0.65 or stalled under 0.005 per 500 lines |
| Hirnmoder | 200 | until dead end | multiplicative, opacity 0.2 to 0.5 | no improving chord, optional rim-walk recovery |
| roy-hachnochi | 360 | 3000 mono, 10000 color | anti-aliased, CMY log blend | error threshold |
| damione1 | 280 | up to 4500 | length-normalized Vrellis or L2 with Xiaolin-Wu lines | 1000 failed steps, rollback to best prefix |
| ReString | 211 | 2500 to 2900 useful | accumulate and clip, working 0.05, export `-s` | budget or 3 pulls with no improvement |

Consensus for physical black and white portraits: 180 to 360 nails, 3000 to 5000 threads, 1 to 3 km of thread, black on white, a 600 to 710 mm canvas.

## Rules others impose on themselves

1. Minimum nail distance and cooldown. Most projects forbid short chords and immediate returns. kaspermeerts uses distance 20, halfmonty 30 plus a 20 nail exclusion list, damione1 a circular minimum of 22 with an 8 step cooldown.
2. Eulerian paths for physical winding. Optimizers pick arbitrary chords, then add rim-routed edges and run Hierholzer so one thread covers everything. ReString gets continuity for free: the greedy always pulls from the current nail.
3. Weaker or darker threads. Demoussel's alpha 0.3 finding and Birsak's darker input factor both point the same way as this code base's `-s 0.05` rule for long thread counts.
4. Clamped darkness. Birsak formalizes layers as z = min(1, sum). ReString clips the accumulated canvas the same way.
5. Quality-based stopping. Birsak stops when nothing improves, possibly-wrong stops when the best improvement goes negative, isandrocks stops on blurred SSIM above 0.65. ReString's 3-pull rule sits in the same family and needs no threshold.
6. Importance maps. Birsak, Demoussel and McDougall weight eyes and mouth above background. Open idea for ReString.
7. Asymmetric penalties. McDougall separates over and under darkening to preserve small bright details. Open idea.
8. Edge boost. isandrocks multiplies error by a Sobel factor so threads hug contours. Open idea.
9. Random candidate subsets. roy-hachnochi scans 150 nails per step, Demoussel batches 5000 lines, the original ReString README suggested `-r 50`. All report small quality loss for a large speed gain.
10. Physical divergence. McDougall caps physical pieces at 3500 lines because real thread renders denser than simulation. ReString keeps the same caution.

## What ReString already matches

Greedy squared-error scoring, anti-aliased lines identical to the damione1 Xiaolin-Wu approach, the clamped accumulation model, random subsets, stagnation stopping, 211 nails and a 2500 to 2900 thread saturation inside the published 3000 to 5000 band. The `-s 0.05` rule for long runs independently reproduces Demoussel's semi-transparency conclusion.

## Open improvement candidates

Ranked by payoff over effort:

1. Minimum chord distance. Cheap, removes wasteful short pulls.
2. Auto-scale `-s` against `-l`. Removes the main foot-gun, the export strength mismatch.
3. Importance mask for faces. The portrait fixtures would measure the gain directly.
4. Best-prefix rollback on stagnation, as in damione1. The prefix-deterministic search makes the rollback trivial.
5. Blurred SSIM for acceptance tests, as in isandrocks. The plain SSIM misbehavior on thread renders is documented in [pull-count-quality.md](pull-count-quality.md).

## Sources

- Vrellis: http://artof01.com/vrellis/works/knit.html
- Birsak et al.: http://www.peterwonka.net/Publications/pdfs/2018.EG.Birsak.StringArt.pdf
- Demoussel et al.: https://archive.bridgesmathart.org/2022/bridges2022-63.pdf
- kaspermeerts gist: https://gist.github.com/kaspermeerts/781f0137b361b51224dcab722ae387b4
- danielvarga: https://github.com/danielvarga/string-art
- possiblywrong: https://possiblywrong.wordpress.com/2022/01/22/string-art/
- callummcdougall: https://github.com/callummcdougall/computational-thread-art
- Hirnmoder: https://github.com/Hirnmoder/thread-art
- roy-hachnochi: https://github.com/roy-hachnochi/string-art
- halfmonty: https://github.com/halfmonty/StringArtGenerator
- isandrocks: https://github.com/isandrocks/ThreadArt
- damione1: https://github.com/damione1/thread-art-generator
- piellardj: https://github.com/piellardj/image-stylization-threading
- prabinpebam: https://github.com/prabinpebam/string-art
- Demaine and Vrellis, string art font: https://erikdemaine.org/fonts/stringart/
