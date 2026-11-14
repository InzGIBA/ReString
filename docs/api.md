# Public API

One import, one call, a typed result:

```python
from restring import GenerateOptions, generate

result = generate("portrait.png")
result.image.save_png("out.png")
```

`generate` accepts a path, PNG/JPEG bytes, or a `_core.Image`. It runs the full pipeline the CLI runs: load, crop/resample, nails, greedy search, render.

## GenerateOptions

Every field has the documented default; pass only what you change.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `layout` | str | `"rect"` | layout spec: `circle`, `rect`, `polygon:sides[:count]`, `star:points:inner[:count]`, `rings:r:count,r:count`, `svg:file.svg[:count]`, optional `@aspect` suffix ([layouts](layouts.md)) |
| `nail_step` | int | 4 | density dial for circle and rect |
| `pulls` | int \| None | None | thread budget; None runs to exhaustion |
| `strength` | float \| None | None | export strength; None = fitted from the pull count ([tuning](tuning.md)) |
| `palette` | str \| Path | `"bw"` | `bw`, `wb`, `rgb`, `cmy`, `cmyk`, `auto:K[:chart]` suggested from the photo (chart: `dmc` or a palette JSON path), or a JSON palette file ([palettes](research/palette-experiment.md)) |
| `max_threads` | int | 8 | palette thread cap |
| `grid` | int | 300 | working grid side |
| `export_size` | int | 300 | render side in pixels |
| `weight` | float \| None | None | importance weighting peak (portraits) |
| `weight_map` | str \| Path \| None | None | grayscale PNG of per-pixel search weights, overrides `weight` (bw runs) |
| `min_chord` | float \| None | None | minimum chord distance in grid pixels |
| `rollback` | bool | False | truncate a stagnating run to its best prefix |
| `realistic` | bool | False | physical thread width render |
| `canvas_size` | float | 400 | board size in mm behind `realistic` |
| `thread_width` | float | 0.2 | thread diameter in mm |
| `radius1_multiplier` | float | 1 | export height multiplier |
| `radius2_multiplier` | float | 1 | export width multiplier |
| `random_nails` | int \| None | None | scan a fixed seeded subset of k candidates per iteration |
| `seed` | int \| None | None | subset seed, core default 42 |
| `crop` | tuple \| None | None | source crop as (x0, y0, x1, y1) fractions in 0..1 |
| `contrast` | float | 1.0 | contrast around mid-gray, > 1 hardens |
| `gamma` | float | 1.0 | gamma power on 0..1, < 1 brightens |
| `invert` | bool | False | negative of the photo |

## Result

| Field | Type | Meaning |
|---|---|---|
| `image` | `_core.Image` | the render; `save_png(path)` writes it |
| `pull_orders` | list[list[int]] | one wound sequence (bw) or per-thread sequences (color), interleaved and padded |
| `nails` | list[tuple[int, int]] | the layout in working-grid pixels |
| `options` | GenerateOptions | the options the run used |
| `stats` | Stats | `pulls_per_thread`, `nails`, `elapsed_s` |
| `palette` | list \| None | resolved thread colors for color runs (including `auto:` suggestions), None for bw/wb |

## Continuing a winding

`continue_project(source, project, extra_pulls)` resumes a saved project on
the same uncut thread: every thread replays its stored order and appends up
to `extra_pulls` new pulls from its last nail. The source photo is required
(the project stores only its digest); preprocessing stored in the project
config is reapplied. The returned orders keep the stored prefix unchanged.

```python
from restring import continue_project, generate
from restring.project import load, save

result = generate("portrait.png")
save("art.restring", mode="bw", config={"grid": 300, "wb": False},
     nails=result.nails, pull_orders=result.pull_orders, input_digest="sha256:...")
more = continue_project("portrait.png", load("art.restring"), 1000)
```

The CLI equivalent is `--project art.restring -i portrait.png --extra-pulls 1000`.

## Examples

Minimal: defaults render a rect-board black-and-white piece:

```python
from restring import generate

result = generate("portrait.png")
result.image.save_png("out.png")
```

Portrait preset: more threads, fitted strength, center weighting:

```python
from restring import GenerateOptions, generate

result = generate("portrait.png", GenerateOptions(
    layout="rect", pulls=2000, strength=0.05, weight=3.0))
result.image.save_png("out.png")
print(result.stats)
```

Project round-trip: save the winding instructions, re-render later:

```python
from restring import GenerateOptions, Result, generate
from restring.project import save, load

result = generate("portrait.png", GenerateOptions(pulls=2000))
save("art.restring", mode="bw", config={"grid": 300, "wb": False},
     nails=result.nails, pull_orders=result.pull_orders, input_digest="sha256:...")
again = load("art.restring")
```

## Deprecated names

`generate_bw`, `generate_rgb` and `Config` (the 1.x API) still work and emit a `DeprecationWarning`; they delegate to the same pipeline and disappear in 3.0.

## numpy bridge

Analysis scripts that want numpy matrices import the dev bridge by path, and the runtime package stays numpy-free:

```python
import sys
sys.path.insert(0, "scripts")
from _bridge import image_from_numpy, image_to_numpy
```
