"""Typed Grafana adapter (health check only for v1)."""

from typing import Any, Protocol


class GrafanaPort(Protocol):
    def health(self) -> dict[str, Any]: ...


class HttpGrafanaAdapter:
    def __init__(self, base_url: str, username: str | None = None, password: str | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password

    def health(self) -> dict[str, Any]:
        import httpx

        url = f"{self._base}/api/health"
        auth = None
        if self._username is not None and self._password is not None:
            auth = (self._username, self._password)
        with httpx.Client(timeout=20.0) as c:
            r = c.get(url, auth=auth)
            r.raise_for_status()
            return r.json()


def get_grafana_adapter() -> GrafanaPort | None:
    from fixops_worker_obs.settings import settings

    if settings.grafana_base_url:
        return HttpGrafanaAdapter(
            settings.grafana_base_url,
            username=settings.grafana_username,
            password=settings.grafana_password,
        )
    return None
