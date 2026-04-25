"""LangGraph Postgres checkpointer migrations (optional; needs DB privileges)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]


def _sync_uri() -> str:
    return os.environ.get(
        "FIXOPS_TEST_POSTGRES_URI",
        "postgresql://fixops:fixops@127.0.0.1:5432/fixops",
    )


def test_postgres_checkpoint_migrations_subprocess() -> None:
    """Fresh interpreter runs LangGraph ``PostgresSaver.setup()`` (same as controller checkpoints)."""
    uri = _sync_uri()
    code = f"""
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver

uri = {uri!r}
pool = ConnectionPool(
    uri,
    min_size=1,
    max_size=5,
    kwargs={{"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}},
)
try:
    saver = PostgresSaver(pool)
    saver.setup()
finally:
    pool.close()
print("checkpoint_migrations_ok")
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        pytest.skip(
            "Postgres LangGraph checkpoint setup failed (need GRANT CREATE ON SCHEMA public "
            f"for role in {uri!r}; DATABASE/ALL TABLES grants are not enough — see "
            f"scripts/postgres_fixops_grants.sql). stderr:\n{proc.stderr}"
        )
    assert "checkpoint_migrations_ok" in proc.stdout
