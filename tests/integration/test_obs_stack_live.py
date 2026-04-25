"""Live checks for Loki/Grafana endpoints configured in worker-obs.yaml."""

from __future__ import annotations

import httpx
import pytest

from fixops_contract.config_yaml import load_worker_obs_yaml

pytestmark = pytest.mark.integration


def test_loki_query_api_responds_when_configured():
    cfg = load_worker_obs_yaml()
    base = (cfg.get("loki_base_url") or "").rstrip("/")
    path = cfg.get("loki_query_path") or "/loki/api/v1/query"
    if not base:
        pytest.skip("loki_base_url missing in config/worker-obs.yaml")
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base}{path}"
    expr = 'count_over_time({namespace=~".+"}[5m])'
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, params={"query": expr})
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        pytest.skip(f"Loki not reachable at {url}: {e}")
    assert r.status_code == 200, f"GET {url} -> HTTP {r.status_code}: {r.text[:400]}"
    data = r.json()
    assert data.get("status") == "success", data


def test_grafana_health_api_responds_when_configured():
    cfg = load_worker_obs_yaml()
    base = (cfg.get("grafana_base_url") or "").rstrip("/")
    if not base:
        pytest.skip("grafana_base_url missing in config/worker-obs.yaml")
    auth = None
    if cfg.get("grafana_username") and cfg.get("grafana_password"):
        auth = (str(cfg["grafana_username"]), str(cfg["grafana_password"]))
    url = f"{base}/api/health"
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, auth=auth)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        pytest.skip(f"Grafana not reachable at {url}: {e}")
    assert r.status_code == 200, f"GET {url} -> HTTP {r.status_code}: {r.text[:400]}"
    data = r.json()
    assert "database" in data
