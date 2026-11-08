"""Static guard: the runtime package must not reference numpy.

`dependencies = []` means a runtime install has no numpy; any import or use
of it in src/restring would crash there. This test parses the package sources
with the AST and flags numpy imports and `np`-qualified usages (docstrings
and comments are naturally ignored).
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).parent.parent / "src" / "restring"


def _numpy_offenders(source):
    tree = ast.parse(source.read_text())
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "numpy":
                    offenders.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "numpy":
            offenders.append((node.lineno, f"from {node.module} import ..."))
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id == "np":
            offenders.append((node.lineno, f"np.{node.attr}"))
    return offenders


def test_runtime_package_never_references_numpy():
    findings = []
    for source in sorted(PACKAGE.glob("*.py")):
        for line_no, what in _numpy_offenders(source):
            findings.append(f"{source.name}:{line_no}: {what}")
    assert not findings, "numpy leaked into the runtime package:\n" + "\n".join(findings)
