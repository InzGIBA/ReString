# ReString

ReString turns a photo into string art. Feed in a portrait. You get the picture a single thread would draw around nails, plus the nail order to wind the thread by hand or with a machine.

The greedy algorithm picks one thread at a time. Each step scores every possible pull from the current nail, takes the pull that moves the canvas closest to the reference photo, and repeats. Black and white output uses one thread. RGB uses three, one per channel.

Key facts:

- Zero runtime dependencies. The Python package is a thin API over a Rust core. Image codecs, nail layouts, the rasterizer, the greedy search and the renders all live in Rust.
- Python 3.14, numpy 2 and matplotlib sit in the dev group for tests and analysis scripts.
- Fast. A 7000-iteration search on 211 nails takes 0.8 s. A full CLI run with 300 threads takes 0.2 s.
- Verified. 46 tests run in 1.8 s. Golden tests pin the exact rasterizer output and greedy pull orders, so silent behavior drift fails the suite.

The project started as a 2020 university course assignment by Kaspar Valk, Kert Tali and Almas Baktubayev. The [project poster](https://raw.githubusercontent.com/InzGIBA/ReString/main/docs/Algoritmika%20poster%20puhtand.pdf) describes the original idea.

## Installation

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) and a Rust toolchain. uv fetches Python 3.14 and compiles the core on first sync.

```bash
uv sync
```

No system C compiler? Use zig as the cargo linker. The recipe lives in [docs/architecture.md](docs/architecture.md#build).

## Quickstart

```bash
# best quality preset, ~1.4 s
uv run restring -i portrait.png -o out.png --rect -n 2 -l 3000 -s 0.05

# balanced, ~0.6 s
uv run restring -i portrait.png -o out.png --rect -n 4 -l 2000 -s 0.05

# fast preview, ~0.3 s
uv run restring -i portrait.png -o out.png --rect -l 300 -s 0.2
```

The `-s 0.05` value matters. The render strength must scale down as the thread count goes up, or the picture overshoots and darkens. The tuning guide explains the rule and the degradation curves: [docs/tuning.md](docs/tuning.md).

## CLI reference

| Flag | Meaning | Default |
|---|---|---|
| `-i <path>` | input image (PNG or JPEG) | required |
| `-o <path>` | output PNG | `output.png` |
| `-d <int>` | output side length in pixels | 300 |
| `-n <int>` | nail step. Smaller values place more nails. Minimum 1 | 4 |
| `-l <int>` | iteration budget. Without the flag the search stops after 3 pulls with no improvement | run to exhaustion |
| `-s <float>` | thread strength at export, 0..1 | 0.1 |
| `-r <int>` | scan a fixed random subset of candidates each iteration. Trades quality for speed. Good values sit near 100 to 150 | all nails |
| `-r1 <float>` | vertical nail ellipse multiplier | 1 |
| `-r2 <float>` | horizontal nail ellipse multiplier | 1 |
| `--rect` | nails on the rectangle border instead of the circle. Better for square portraits, about 2x lower error | circle |
| `--rgb` | colored output with three interleaved threads | black and white |
| `--wb` | white thread on a black canvas | black on white |

Nails sit evenly on the perimeter. The circle starts at 9 o'clock and runs clockwise. The rectangle starts at the top left corner. The pull order is continuous by construction, so you wind one uncut thread.

## Use as a library

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

## Development

```bash
uv run pytest                   # 46 tests, 1.8 s
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

## Photo credits

Portrait fixtures in `tests/data/` are square face-centered crops of studio photos provided for this project. Earlier fixtures came from [Unsplash](https://unsplash.com/s/photos/people) under the [Unsplash License](https://unsplash.com/license).

## License

MIT. See [LICENSE](LICENSE).
