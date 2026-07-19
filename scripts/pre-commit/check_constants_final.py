# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Pre-commit hook: module-level UPPER_CASE constants must be annotated Final[...]."""

import ast
import sys
from pathlib import Path


def _is_constant_name(name: str) -> bool:
    return name.isupper() and not (name.startswith("__") and name.endswith("__"))


def _is_final_annotation(annotation: ast.expr) -> bool:
    target = annotation.value if isinstance(annotation, ast.Subscript) else annotation
    match target:
        case ast.Name(id="Final"):
            return True
        case ast.Attribute(attr="Final"):
            return True
        case _:
            return False


def _violations(tree: ast.Module) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            found.extend((node.lineno, n) for n in names if _is_constant_name(n))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            is_constant = _is_constant_name(node.target.id)
            if is_constant and not _is_final_annotation(node.annotation):
                found.append((node.lineno, node.target.id))
    return found


def main(argv: list[str]) -> int:
    """Check each staged file for un-Final module constants.

    Args:
        argv: File paths staged for commit.

    Returns:
        1 when any violation was reported.
    """
    failed = False
    for name in argv:
        tree = ast.parse(Path(name).read_text(encoding="utf-8"), filename=name)
        for lineno, const in _violations(tree):
            sys.stderr.write(f"{name}:{lineno}: constant {const} must be annotated Final[...]\n")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
