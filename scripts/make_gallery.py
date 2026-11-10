"""Gallery builder: a fixed grid of configurations over the portrait fixtures.

Deterministic by construction (the greedy has no randomness). Writes the
montage to docs/img/gallery.png and the configuration manifest to
docs/img/gallery.json; examples/gallery/README.md embeds both with the
commands to reproduce every tile.

    uv run python scripts/make_gallery.py
"""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from restring import GenerateOptions, generate

OUT = Path(__file__).parent.parent / "docs" / "img"
PHOTOS = {
    "male": "tests/data/portrait_male.png",
    "female": "tests/data/portrait_female.png",
}

CONFIGS = [
    ("circle, 300 pulls", GenerateOptions(layout="circle", pulls=300, strength=0.2)),
    ("rect, 300 pulls", GenerateOptions(layout="rect", pulls=300, strength=0.2)),
    ("circle, 2000 pulls", GenerateOptions(layout="circle", pulls=2000, strength=0.05)),
    ("rect, 2000 pulls", GenerateOptions(layout="rect", pulls=2000, strength=0.05)),
    ("rect, 2000, weight 3", GenerateOptions(layout="rect", pulls=2000, strength=0.05, weight=3.0)),
    ("star:5:0.55, exhaustion", GenerateOptions(layout="star:5:0.55:1500", strength=0.05)),
]


def main():
    rendered = {}
    manifest = []

    for tag, path in PHOTOS.items():
        row = []
        for label, options in CONFIGS:
            result = generate(path, options)
            arr = np.asarray(result.image.tolist())
            if arr.ndim == 2:
                arr = np.stack([arr] * 3, axis=-1)
            row.append(arr)
            manifest.append({
                "fixture": tag,
                "config": label,
                "pulls_per_thread": result.stats.pulls_per_thread,
                "nails": result.stats.nails,
            })
            print(f"{tag} {label}: {result.stats.pulls_per_thread} "
                  f"({result.stats.elapsed_s}s)")
        rendered[tag] = row

    rows = len(PHOTOS)
    cols = len(CONFIGS)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.2, rows * 2.2))
    for i, (tag, row) in enumerate(rendered.items()):
        for j, arr in enumerate(row):
            axes[i][j].imshow(arr)
            axes[i][j].axis("off")
            if i == 0:
                axes[i][j].set_title(CONFIGS[j][0], fontsize=8)
            if j == 0:
                axes[i][j].set_ylabel(tag, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "gallery.png", dpi=130)
    (OUT / "gallery.json").write_text(json.dumps(manifest, indent=1))
    print(f"montage: docs/img/gallery.png ({rows} x {cols} tiles)")


if __name__ == "__main__":
    import json
    main()
