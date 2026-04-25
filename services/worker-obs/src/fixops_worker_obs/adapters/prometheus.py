"""Typed Prometheus adapter (AD-007). MCP server mirrors this for MCP-first path."""

from typing import Any, Protocol


class PrometheusPort(Protocol):
    def query_instant(self, expr: str) -> dict[str, Any]: ...


class StubPrometheusAdapter:
    def query_instant(self, expr: str) -> dict[str, Any]:
        return {
            "status": "success",
            "data": {"resultType": "vector", "result": [{"metric": {"job": "stub"}, "value": [0, "1"]}]},
        }


class HttpPrometheusAdapter:
    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")

    def query_instant(self, expr: str) -> dict[str, Any]:
        import httpx

        url = f"{self._base}/api/v1/query"
        with httpx.Client(timeout=20.0) as c:
            r = c.get(url, params={"query": expr})
            r.raise_for_status()
            return r.json()


def get_prometheus_adapter() -> PrometheusPort:
    from fixops_worker_obs.settings import settings

    if settings.prometheus_url:
        return HttpPrometheusAdapter(settings.prometheus_url)
    return StubPrometheusAdapter()
