"""Search options that used to be dead flags: random_nails, seed, radius
multipliers. Behavior tests on the public API, small grids for speed."""

from pathlib import Path

from restring.api import GenerateOptions, generate

FIXTURE = Path(__file__).parent / "data" / "portrait_female.png"


def run(**overrides):
    options = GenerateOptions(layout="rect", nail_step=2, pulls=150, grid=64,
                              export_size=64, strength=0.1)
    for key, value in overrides.items():
        setattr(options, key, value)
    return generate(FIXTURE, options)


def test_random_nails_changes_the_pull_order():
    full = run()
    subset = run(random_nails=10)
    assert full.pull_orders[0] != subset.pull_orders[0]


def test_seed_makes_the_subset_reproducible():
    a = run(random_nails=10, seed=7)
    b = run(random_nails=10, seed=7)
    c = run(random_nails=10, seed=8)
    assert a.pull_orders[0] == b.pull_orders[0]
    assert a.pull_orders[0] != c.pull_orders[0]


def test_default_seed_matches_the_core_default():
    explicit = run(random_nails=10, seed=42)
    implicit = run(random_nails=10)
    assert explicit.pull_orders[0] == implicit.pull_orders[0]


def test_radius_multipliers_shape_the_export():
    result = run(radius1_multiplier=2, radius2_multiplier=1)
    assert result.image.shape() == (128, 64, 1)


def test_random_nails_palette_run():
    result = run(palette="cmyk", random_nails=12, seed=3)
    assert len(result.pull_orders) == 4
    assert result.image.shape() == (64, 64, 3)