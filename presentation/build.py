# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Render the architecture slide from SVG to a vector PDF (and a PNG proof).

The slide is hand-authored SVG so the layout is exact; this only converts it.
`rsvg-convert` keeps the PDF genuinely vector (cairo embeds font subsets), which
a screenshot-based path would not.

The source lives in `docs/` because the README embeds the same file — one
diagram serves both the repo and the deck, so the two cannot drift apart.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

HERE: Final[Path] = Path(__file__).resolve().parent
SOURCE: Final[Path] = HERE.parent / "docs" / "architecture.svg"
OUT_DIR: Final[Path] = HERE / "out"
PDF: Final[Path] = OUT_DIR / "architecture.pdf"
PNG: Final[Path] = OUT_DIR / "preview.png"

CONVERTER: Final[str] = "rsvg-convert"
PREVIEW_WIDTH: Final[int] = 1600


class ConverterMissingError(RuntimeError):
    """Raised when rsvg-convert is not on PATH."""

    def __init__(self) -> None:
        """Name the binary and how to install it."""
        super().__init__(f"{CONVERTER} not found on PATH; install it with `brew install librsvg`")


class ConversionError(RuntimeError):
    """Raised when rsvg-convert exits non-zero."""

    def __init__(self, target: Path, stderr: str) -> None:
        """Record which output failed and why.

        Args:
            target: The output file that could not be produced.
            stderr: Converter diagnostics.
        """
        super().__init__(f"failed to render {target.name}: {stderr.strip()}")


def _convert(fmt: str, target: Path, width: int | None = None) -> None:
    """Run rsvg-convert for one output format.

    Args:
        fmt: An rsvg-convert format name, `pdf` or `png`.
        target: Destination path.
        width: Optional pixel width; raster formats only.

    Raises:
        ConversionError: The converter exited non-zero.
    """
    command = [CONVERTER, "-f", fmt]
    if width is not None:
        command += ["-w", str(width)]
    command += [str(SOURCE), "-o", str(target)]

    completed = subprocess.run(  # noqa: S603 - argv is module constants, never user input
        command, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise ConversionError(target, completed.stderr)


def build(*, preview_only: bool) -> tuple[Path, ...]:
    """Render the slide.

    Args:
        preview_only: Render just the PNG proof, skipping the PDF.

    Returns:
        The paths written, in the order they were produced.

    Raises:
        ConverterMissingError: rsvg-convert is not installed.
        FileNotFoundError: The SVG source is missing.
    """
    if shutil.which(CONVERTER) is None:
        raise ConverterMissingError
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)
    OUT_DIR.mkdir(exist_ok=True)
    _convert("png", PNG, PREVIEW_WIDTH)
    if preview_only:
        return (PNG,)
    _convert("pdf", PDF)
    return (PNG, PDF)


def main() -> int:
    """Parse arguments and render.

    Returns:
        A process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument(
        "--preview", action="store_true", help="render only the PNG proof, skipping the PDF"
    )
    args = parser.parse_args()
    preview_only: bool = bool(args.preview)
    try:
        written = build(preview_only=preview_only)
    except (ConverterMissingError, ConversionError, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for path in written:
        print(f"wrote {path.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
