"""ReString — recreate images by connecting nails with strings (greedy algorithm)."""

from restring import _core  # noqa: F401  (compiled module, typed via _core.pyi)
from restring.api import GenerateOptions, Result, Stats, continue_project, generate
from restring.generator import Config, generate_bw, generate_rgb

__version__ = "2.1.0"

__all__ = [
    "Config",
    "GenerateOptions",
    "Result",
    "Stats",
    "continue_project",
    "generate",
    "generate_bw",
    "generate_rgb",
]
