<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/hero-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/hero-light.svg">
  <img alt="ReString — turn any photo into string art you can wind by hand" src="assets/hero-light.svg" width="100%">
</picture>

Feed in a portrait. The greedy search picks one thread at a time — each pull is the one that moves the canvas measurably closer to the reference photo — and out comes the picture a single thread would draw around the nails, plus the nail order to wind it. Black and white output uses one thread. RGB uses three, one per channel.

[Quick start](#quick-start) · [Usage](#usage) · [Tuning](#tuning) · [Development](#development) · [Contributing](#contributing) · [License](#license)

## Overview

- **For:** makers winding physical boards, machine and plotter owners, and anyone who wants a digital string-art render.
- **Input:** a PNG or JPEG photo; face-centered portraits work best.
- **Output:** a PNG render of the thread pattern; the Python API also returns the continuous nail-by-nail pull order.
- **Scope:** greedy search, B/W or RGB, circle or rectangle nail layouts, a 300 px working grid. Building from source requires a Rust toolchain — there is no pure-Python fallback.

![A photo becomes a thread drawing](assets/demo.jpg)

One run of the CLI: the same portrait at 1000 threads around 300 nails and 3000 threads around 598 nails (`--rect -s 0.05`).

The project started as a 2020 university course assignment by Kaspar Valk, Kert Tali and Almas Baktubayev. The [project poster](https://raw.githubusercontent.com/InzGIBA/ReString/main/docs/Algoritmika%20poster%20puhtand.pdf) describes the original idea.

## Features

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/feature-01-dark.svg">
  <img alt="Fast by design — a Rust greedy search, 7000 pulls in 0.8 s" src="assets/feature-01-light.svg" width="32%">
</picture>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/feature-02-dark.svg">
  <img alt="Zero dependencies — a thin Python API over a Rust core" src="assets/feature-02-light.svg" width="32%">
</picture>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/feature-03-dark.svg">
  <img alt="Verified output — golden tests pin pixels and pull order" src="assets/feature-03-light.svg" width="32%">
</picture>

- **One uncut thread** — the pull order is continuous by construction, so you wind a single thread by hand or machine.
- **Two layouts, three palettes** — nails on a circle or a rectangle border; black-on-white, white-on-black, or RGB with three interleaved threads.
- **Measured, not guessed** — every flag has a degradation curve behind it in the [tuning guide](docs/tuning.md).

## Quick start

### Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) and a Rust toolchain with a C linker for cargo. uv fetches Python 3.14 and compiles the core on first sync.
- No system C compiler (minimal WSL or container)? Use zig as the cargo linker — the recipe lives in [docs/architecture.md](docs/architecture.md#build).

### Install

```bash
uv sync
```

### Run your first example

```bash
uv run restring -i portrait.png -o out.png --rect -n 2 -l 3000   # best quality, ~1.4 s
```

Expected result:

```text
[...] [restring.cli] [INFO]: Nails amount: 598
```

`out.png` now holds the rendered thread pattern.

## Usage

### Basic example

Three presets cover most jobs (timed on a 24-core Linux box):

```bash
# fast preview, ~0.3 s
uv run restring -i portrait.png -o out.png --rect -l 300

# balanced, ~0.6 s
uv run restring -i portrait.png -o out.png --rect -n 4 -l 2000

# maximum measured quality, ~1.4 s
uv run restring -i portrait.png -o out.png --rect -n 2 -l 3000
```

### CLI reference

| Flag | Meaning | Default |
|---|---|---|
| `-i <path>` | input image (PNG or JPEG) | required |
| `-o <path>` | output PNG | `output.png` |
| `-d <int>` | output side length in pixels | 300 |
| `-n <int>` | nail step. Smaller values place more nails. Minimum 1 | 4 |
| `-l <int>` | iteration budget. Without the flag the search stops after 3 pulls with no improvement | run to exhaustion |
| `-s <float>` | thread strength at export, 0..1. Leave unset and the run derives the value from the actual pull count: k/L with k=104, clamped to 0.03..0.2, within 2 percent of the hand-tuned optimum at the measured budgets | auto |
| `-r <int>` | scan a fixed random subset of candidates each iteration. Trades quality for speed. Good values sit near 100 to 150 | all nails |
| `-r1 <float>` | vertical nail ellipse multiplier | 1 |
| `-r2 <float>` | horizontal nail ellipse multiplier | 1 |
| `--rect` | nails on the rectangle border instead of the circle. Better for square portraits, about 2x lower error | circle |
| `--rgb` | colored output with three interleaved threads | black and white |
| `--wb` | white thread on a black canvas | black on white |
| `--weight <float>` | importance weighting. A Gaussian weight map steers threads toward the image center, where the viewer looks. Suggested range 1.5 to 5.0. Portrait subjects only, about 25 percent more scan time | off |
| `--min-chord <px>` | candidate filter: chords shorter than the distance in working-grid pixels are banned. Portrait measurement: the greedy never picks short chords, the filter only degrades MSE past 250 px. Intended for sparse custom layouts | off |

Nails sit evenly on the perimeter. The circle starts at 9 o'clock and runs clockwise. The rectangle starts at the top left corner. The pull order is continuous by construction, so you wind one uncut thread.

### As a library

```python
from restring import _core
from restring.canvas import init_canvas, pull_order_to_array_bw
from restring.generator import Config, create_art, generate_bw
from restring.image_transformations import largest_square, resize
from restring.nails import create_circle_nail_positions

img = resize(largest_square(_core.Image.load("portrait.png")), (300, 300))
nails = create_circle_nail_positions((300, 300), nail_step=4)
result, pull_order = generate_bw(img, (300, 300), nails, Config(side_len=300, pull_amount=2000))
result.save_png("out.png")
```

Images travel as `_core.Image` objects. The pixel data stays in Rust memory, so calls pass references instead of copying arrays. The test suite and the analysis scripts show numpy bridging helpers you copy for your own asserts and plots.

## Tuning

`-s` is fitted for you: the run derives the export strength from the actual pull count (104/L clamped to 0.03..0.2) and lands within 2 percent of the hand-tuned optimum at the measured budgets. The working simulation darkens each pull with strength 0.05; the export accumulates with strength `-s`. When `-s` is too high for the thread count, the render reaches its target halfway, then overshoots and darkens. Manual `-s` values stay for special cases, see the tuning guide.

| Flag | Recommended | Rule |
|---|---|---|
| `--rect` | always on for square portraits | 1.8 to 2.7x lower error than the circle |
| `-s` | leave unset, auto fits the pull count | measured optimum scales as 1 over thread count, k=104 clamped 0.03 to 0.2 |
| `-l` | up to saturation, about 2500 to 2900 threads | beyond saturation the search finds no improvements |
| `-n` | 4 for the knee, 2 for maximum quality | 844 circle nails buy 6 percent error reduction at 4x the cost |
| `-r` | 100 to 150 while exploring, drop for the final run | k=100 saves 40 percent of the time for 15 percent error |
| `-d` | 300 | exporting above the working grid hurts |
| `--weight` | 3.0 for portraits, off for other subjects | center MSE falls 24 to 28 percent, global MSE rises 3 percent |
| `--min-chord` | off | the greedy never picks short chords, thresholds bite past 230 px at up to 24 percent MSE cost |

Every flag, the numbers behind the rules and the degradation curves: [docs/tuning.md](docs/tuning.md).

## Development

```bash
git clone git@github.com:InzGIBA/ReString.git
cd ReString
uv sync
```

### Checks

```bash
uv run pytest                   # 61 tests, ~6 s
uv run ruff check .
uv run python scripts/benchmark.py --label before   # or after, then --plot
```

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | how the pipeline works, the Rust core, correctness model, performance, build |
| [docs/tuning.md](docs/tuning.md) | every flag, degradation curves, recommended values, presets |
| [docs/history.md](docs/history.md) | the migration story: stages, numbers, rejected hypotheses |
| [docs/research/pull-count-quality.md](docs/research/pull-count-quality.md) | when thread count helps and when quality degrades |
| [docs/research/related-work.md](docs/research/related-work.md) | survey of string art projects, papers and their rules |

## Roadmap

- [x] Re-run the RGB sweeps — working strength 0.05 adopted, 13 to 17 percent better MSE ([measurement](docs/research/rgb-channels-experiment.md)).
- [ ] Test the working grid above 300 px.

## Contributing

Issues and pull requests are welcome. For larger changes, open an issue first to discuss the approach. For bug reports, include the input image, the exact command line, and the actual versus expected result.

1. Describe the problem or the proposed improvement.
2. Make a focused change.
3. Add or update relevant tests and documentation.
4. Run the checks above and open a pull request.

## License

MIT. See [LICENSE](LICENSE).

## Photo credits

Portrait fixtures in `tests/data/` are square face-centered crops of studio photos provided for this project. The demo image above uses the `portrait_female.png` fixture. Earlier fixtures came from [Unsplash](https://unsplash.com/s/photos/people) under the [Unsplash License](https://unsplash.com/license).
