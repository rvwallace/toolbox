"""Tests for the cross-platform Teams URL launcher."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

module_path = Path(__file__).parents[1] / "scripts/productivity/join-call.py"
spec = importlib.util.spec_from_file_location("join_call", module_path)
assert spec is not None and spec.loader is not None
join_call = importlib.util.module_from_spec(spec)
pytest.importorskip("textual")
sys.modules[spec.name] = join_call
spec.loader.exec_module(join_call)


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("darwin", "open"), ("linux", "xdg-open"), ("linux-gnu", "xdg-open")],
)
def test_launcher_for_supported_platforms(platform: str, expected: str) -> None:
    assert join_call.launcher_for_platform(platform) == expected


def test_launcher_for_unsupported_platform() -> None:
    assert join_call.launcher_for_platform("win32") is None
