"""Typed Loki adapter."""

from typing import Any, Protocol


class LokiPort(Protocol):
    def query_instant(self, expr: str) -> dict[str, Any]: ...

    def query_range(self, expr: str, *, start_ns: int, end_ns: int, limit: int = 50) -> dict[str, Any]: ...


class HttpLokiAdapter:
    def __init__(self, base_url: str, query_path: str = "/loki/api/v1/query") -> None:
        self._base = base_url.rstrip("/")
        self._path = query_path if query_path.startswith("/") else f"/{query_path}"

    def query_instant(self, expr: str) -> dict[str, Any]:
        import httpx

        url = f"{self._base}{self._path}"
        with httpx.Client(timeout=20.0) as c:
            r = c.get(url, params={"query": expr})
            r.raise_for_status()
            return r.json()

    def query_range(self, expr: str, *, start_ns: int, end_ns: int, limit: int = 50) -> dict[str, Any]:
        import httpx

        path = self._path.replace("/query", "/query_range")
        url = f"{self._base}{path}"
        with httpx.Client(timeout=20.0) as c:
            r = c.get(
                url,
                params={
                    "query": expr,
                    "start": str(start_ns),
                    "end": str(end_ns),
                    "limit": str(limit),
                },
            )
            r.raise_for_status()
            return r.json()


def get_loki_adapter() -> LokiPort | None:
    from fixops_worker_obs.settings import settings

    if settings.loki_base_url:
        return HttpLokiAdapter(settings.loki_base_url, query_path=settings.loki_query_path)
    return None
