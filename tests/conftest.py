"""Pytest hooks — set DB URL before controller modules import (SQLite file for CI)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


def pytest_configure(config) -> None:
    if os.environ.get("FIXOPS_DATABASE_URL"):
        url = os.environ["FIXOPS_DATABASE_URL"]
        if url.startswith("sqlite"):
            # Ephemeral SQLite cannot host LangGraph Postgres checkpoints; keep CI on memory.
            os.environ.setdefault("FIXOPS_CHECKPOINT_BACKEND", "memory")
        return
    fd, path = tempfile.mkstemp(prefix="fixops_", suffix=".db")
    os.close(fd)
    os.environ["FIXOPS_DATABASE_URL"] = f"sqlite:///{path}"
    os.environ.setdefault("FIXOPS_CHECKPOINT_BACKEND", "memory")


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
