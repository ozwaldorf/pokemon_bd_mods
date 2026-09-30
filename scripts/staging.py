"""Publish generated directories without leaving partial or stale output."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def replace_directory(staged: Path, output: Path) -> None:
    """Rename staged to output, restoring the previous output on failure.

    staged must share a filesystem with output. The previous output is moved
    beside staged, so staging inside a temporary directory also removes it.
    """
    previous = staged.with_name(f"{staged.name}.previous")
    if output.exists():
        output.rename(previous)
    try:
        staged.rename(output)
    except OSError:
        if previous.exists():
            previous.rename(output)
        raise


@contextmanager
def staged_directory(output: Path) -> Iterator[Path]:
    """Yield an empty directory that replaces output when the block succeeds."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        staged = Path(temporary) / "output"
        staged.mkdir()
        yield staged
        replace_directory(staged, output)
