#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest>=8", "pyyaml"]
# ///
"""Tests for build.py packaging.

Runs build.py with this interpreter, so pyyaml has to be importable here too.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKILL = "concise"


def package(out: Path, *extra: str) -> None:
    result = subprocess.run(
        [sys.executable, str(REPO / "build.py"), "package", SKILL, "--out", str(out), *extra],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def names(archive: Path) -> list[str]:
    with zipfile.ZipFile(archive) as zf:
        return zf.namelist()


def test_skill_format_has_the_skill_directory_at_the_root(tmp_path: Path) -> None:
    package(tmp_path)
    entries = names(tmp_path / f"{SKILL}.skill")
    assert f"{SKILL}/SKILL.md" in entries
    assert all(e.startswith(f"{SKILL}/") for e in entries)


def test_flat_format_puts_skill_md_at_the_zip_root(tmp_path: Path) -> None:
    package(tmp_path, "--format", "flat")
    entries = names(tmp_path / f"{SKILL}.zip")
    assert "SKILL.md" in entries
    assert "test-corpus.md" in entries
    assert not any(e.startswith(f"{SKILL}/") for e in entries)


def test_flat_format_is_byte_reproducible(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    package(first, "--format", "flat")
    package(second, "--format", "flat")
    assert (first / f"{SKILL}.zip").read_bytes() == (second / f"{SKILL}.zip").read_bytes()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
