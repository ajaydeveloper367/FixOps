"""MCP observability package loads (stdio server is run manually or via Docker)."""

import pytest


def test_mcp_obs_package_importable():
    try:
        import mcp_fixops_obs.server as srv  # noqa: PLC0415
    except ImportError as e:
        pytest.skip(f"mcp-fixops-obs not installed: {e}")
    assert getattr(srv, "mcp", None) is not None
