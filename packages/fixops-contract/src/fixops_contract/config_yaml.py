"""Per-service YAML config files under `config/` (independent deployables)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

CONTROLLER_FILE = "controller.yaml"
WORKER_OBS_FILE = "worker-obs.yaml"


def _find_named_config(file_name: str, explicit_path: str | None) -> Path | None:
    if explicit_path:
        p = Path(explicit_path).expanduser()
        if p.is_file():
            return p
    cwd = Path.cwd() / "config" / file_name
    if cwd.is_file():
        return cwd
    here = Path(__file__).resolve()
    for par in here.parents:
        cand = par / "config" / file_name
        if cand.is_file():
            return cand
    return None


def _load(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_controller_yaml() -> dict[str, Any]:
    """Flat dict from ``config/controller.yaml`` (controller service only)."""
    p = _find_named_config(CONTROLLER_FILE, os.environ.get("FIXOPS_CONTROLLER_CONFIG"))
    return _load(p)


def load_worker_obs_yaml() -> dict[str, Any]:
    """Flat dict from ``config/worker-obs.yaml`` (worker-obs service only)."""
    p = _find_named_config(WORKER_OBS_FILE, os.environ.get("FIXOPS_WORKER_OBS_CONFIG"))
    return _load(p)


# Backwards-compatible names (same files).
def controller_section() -> dict[str, Any]:
    return load_controller_yaml()


def worker_obs_section() -> dict[str, Any]:
    return load_worker_obs_yaml()
