"""
Live checks against Prometheus using ``config/worker-obs.yaml`` (same URL shape as ``worker-obs``).

Skips if the endpoint is unreachable. Fails with a clear hint if the configured path returns HTML
(Prometheus UI lives at ``/query``; the JSON instant API is ``/api/v1/query``).
"""

from __future__ import annotations

import json

import httpx
import pytest

from fixops_contract.config_yaml import load_worker_obs_yaml
from fixops_worker_obs.adapters.prometheus import HttpPrometheusAdapter


pytestmark = pytest.mark.integration


def _build_query_url() -> tuple[str, str]:
    cfg = load_worker_obs_yaml()
    base = (cfg.get("prometheus_base_url") or "").rstrip("/")
    path = cfg.get("prometheus_query_path") or "/api/v1/query"
    if not path.startswith("/"):
        path = "/" + path
    if not base:
        pytest.skip("prometheus_base_url missing in config/worker-obs.yaml")
    return base, path


def _assert_json_not_ui(r: httpx.Response, url: str) -> dict:
    assert r.status_code == 200, f"GET {url} -> HTTP {r.status_code}: {r.text[:500]}"
    body = r.text.lstrip()
    if body.startswith("<!") or "text/html" in (r.headers.get("content-type") or "").lower():
        pytest.fail(
            f"Received HTML from {url} — this is usually the Prometheus **UI** path `/query`. "
            f"Set prometheus_query_path to `/api/v1/query` in config/worker-obs.yaml for the JSON API."
        )
    try:
        return r.json()
    except Exception as e:
        pytest.fail(f"Expected JSON from {url}, got: {r.text[:300]!r} ({e})")


def test_prometheus_instant_api_vector1():
    """``vector(1)`` should return one series on any Prometheus-compatible instant API."""
    base, path = _build_query_url()
    url = f"{base}{path}"
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url, params={"query": "vector(1)"})
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        pytest.skip(f"Prometheus not reachable at {url}: {e}")

    data = _assert_json_not_ui(r, url)
    assert data.get("status") == "success", data
    res = (data.get("data") or {}).get("result") or []
    assert len(res) >= 1, f"expected at least one vector result, got: {data!r}"


def test_prometheus_instant_api_up_has_targets():
    """``up`` should list at least one scrape target when metrics are actually available."""
    base, path = _build_query_url()
    url = f"{base}{path}"
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url, params={"query": "up"})
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        pytest.skip(f"Prometheus not reachable at {url}: {e}")

    data = _assert_json_not_ui(r, url)
    assert data.get("status") == "success", data
    res = (data.get("data") or {}).get("result") or []
    assert len(res) >= 1, (
        "`up` returned no series: nothing is being scraped yet, or the endpoint is not "
        "Prometheus-compatible for `up`. Fix scrape configs or query path."
    )


def test_prometheus_up_namespace_monitoring_has_series_when_present():
    """
    Local / kind stacks often scrape node-exporter in ``monitoring``; worker-obs tries
    ``up{namespace="<ns>"}`` first for pod-shaped alerts.
    """
    base, path = _build_query_url()
    url = f"{base}{path}"
    q = 'up{namespace="monitoring"}'
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url, params={"query": q})
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        pytest.skip(f"Prometheus not reachable at {url}: {e}")

    data = _assert_json_not_ui(r, url)
    assert data.get("status") == "success", data
    res = (data.get("data") or {}).get("result") or []
    if not res:
        pytest.skip(
            "No series for up{namespace=\"monitoring\"} — skip when this namespace is not scraped "
            "(e.g. empty dev Prometheus). Deploy node-exporter under monitoring to exercise this path."
        )
    assert len(res) >= 1


def test_worker_http_prometheus_adapter_matches_config():
    """Same code path as ``worker-obs`` for instant queries."""
    cfg = load_worker_obs_yaml()
    base = cfg.get("prometheus_base_url")
    if not base:
        pytest.skip("prometheus_base_url missing")
    qpath = cfg.get("prometheus_query_path") or "/api/v1/query"
    try:
        adapter = HttpPrometheusAdapter(base, query_path=qpath)
        data = adapter.query_instant("vector(1)")
    except httpx.HTTPError as e:
        pytest.skip(f"Prometheus HTTP error: {e}")
    except json.JSONDecodeError:
        pytest.fail(
            "Worker adapter got non-JSON (often HTML from `/query` UI). "
            "Use prometheus_query_path: /api/v1/query in config/worker-obs.yaml."
        )

    assert data.get("status") == "success"
    assert len((data.get("data") or {}).get("result") or []) >= 1
