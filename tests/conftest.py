"""Pytest hooks — set DB URL before controller modules import (SQLite file for CI)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


def pytest_configure(config) -> None:
    if os.environ.get("FIXOPS_DATABASE_URL"):
        return
    fd, path = tempfile.mkstemp(prefix="fixops_", suffix=".db")
    os.close(fd)
    os.environ["FIXOPS_DATABASE_URL"] = f"sqlite:///{path}"


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
