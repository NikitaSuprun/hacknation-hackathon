# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Pre-commit hook: every .py file starts with the proprietary copyright header."""

import sys
from pathlib import Path
from typing import Final

HEADER_LINES: Final[tuple[str, str]] = (
    "# Copyright (c) 2026 Venture Hunt. All rights reserved.",
    "# Proprietary and confidential. See LICENSE.",
)


def _has_header(lines: list[str]) -> bool:
    start = 1 if lines and lines[0].startswith("#!") else 0
    candidate = lines[start : start + len(HEADER_LINES)]
    return [line.rstrip("\n") for line in candidate] == list(HEADER_LINES)


def _add_header(path: Path) -> bool:
    """Insert the header if missing.

    Args:
        path: File to check and, when needed, rewrite in place.

    Returns:
        True when the file was modified.
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if _has_header(lines):
        return False
    start = 1 if lines and lines[0].startswith("#!") else 0
    header = [line + "\n" for line in HEADER_LINES]
    path.write_text("".join(lines[:start] + header + lines[start:]), encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    """Run the hook over the files pre-commit passes in.

    Args:
        argv: File paths staged for commit.

    Returns:
        1 when any file was rewritten (pre-commit shows it as failed-then-fixed).
    """
    modified = [name for name in argv if _add_header(Path(name))]
    for name in modified:
        sys.stderr.write(f"added license header: {name}\n")
    return 1 if modified else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
