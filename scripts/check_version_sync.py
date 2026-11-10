"""Fail when the package version drifts between the three files that carry it.

pyproject.toml, src/restring/__init__.py and rust/Cargo.toml must agree. CI
runs this before the test suite; the release workflow runs it before wheels
are built.

    uv run python scripts/check_version_sync.py
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent


def main():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    init_match = re.search(r'__version__\s*=\s*"([^"]+)"',
                           (ROOT / "src" / "restring" / "__init__.py").read_text())
    if init_match is None:
        print("version drift: no __version__ in src/restring/__init__.py")
        sys.exit(1)
    init = init_match.group(1)
    cargo = tomllib.loads((ROOT / "rust" / "Cargo.toml").read_text())["package"]["version"]

    versions = {
        "pyproject.toml": pyproject,
        "src/restring/__init__.py": init,
        "rust/Cargo.toml": cargo,
    }
    if len(set(versions.values())) != 1:
        print("version drift:")
        for path, version in versions.items():
            print(f"  {path}: {version}")
        sys.exit(1)
    print(f"version {pyproject}: in sync")


if __name__ == "__main__":
    main()
