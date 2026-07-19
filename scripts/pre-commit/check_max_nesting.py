# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Pre-commit hook: control-flow nesting inside a function is capped at 3 levels.

An `elif` continues its chain at the same depth (Python's AST nests it inside
`orelse`, which must not count as an extra level).
"""

import ast
import sys
from pathlib import Path
from typing import Final

MAX_DEPTH: Final[int] = 3

_CONTROL: Final[tuple[type[ast.stmt], ...]] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.TryStar,
    ast.Match,
)
_SCOPES: Final[tuple[type[ast.stmt], ...]] = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
)


def _child_blocks(node: ast.stmt) -> list[list[ast.stmt]]:
    if isinstance(node, ast.If):
        blocks = [node.body]
        orelse = node.orelse
        while len(orelse) == 1 and isinstance(orelse[0], ast.If):
            blocks.append(orelse[0].body)
            orelse = orelse[0].orelse
        blocks.append(orelse)
        return blocks
    if isinstance(node, ast.Try | ast.TryStar):
        handler_bodies = [h.body for h in node.handlers]
        return [node.body, *handler_bodies, node.orelse, node.finalbody]
    if isinstance(node, ast.Match):
        return [case.body for case in node.cases]
    body = getattr(node, "body", [])
    orelse = getattr(node, "orelse", [])
    return [body, orelse]


def _scan(stmts: list[ast.stmt], depth: int, out: list[int]) -> None:
    for stmt in stmts:
        if isinstance(stmt, _SCOPES):
            continue
        if isinstance(stmt, _CONTROL):
            if depth + 1 > MAX_DEPTH:
                out.append(stmt.lineno)
            for block in _child_blocks(stmt):
                _scan(block, depth + 1, out)


def _function_violations(tree: ast.Module) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            deep: list[int] = []
            _scan(node.body, 0, deep)
            found.extend((lineno, node.name) for lineno in deep)
    return found


def main(argv: list[str]) -> int:
    """Check each staged file for over-nested functions.

    Args:
        argv: File paths staged for commit.

    Returns:
        1 when any violation was reported.
    """
    failed = False
    for name in argv:
        tree = ast.parse(Path(name).read_text(encoding="utf-8"), filename=name)
        for lineno, fn in _function_violations(tree):
            sys.stderr.write(
                f"{name}:{lineno}: nesting deeper than {MAX_DEPTH} in {fn}(); extract a helper\n"
            )
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
