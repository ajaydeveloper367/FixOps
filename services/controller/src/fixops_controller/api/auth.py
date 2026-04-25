"""Optional shared-secret auth for controller mutation / sensitive routes."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, HTTPException

from fixops_controller.settings import settings


def require_controller_api_key(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """When ``controller_api_key`` is set, require ``Authorization: Bearer <key>`` or ``X-API-Key`` on run routes."""
    expected = (settings.controller_api_key or "").strip()
    if not expected:
        return
    token: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_api_key:
        token = x_api_key.strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing API key")
    try:
        ok = secrets.compare_digest(token, expected)
    except (TypeError, ValueError):
        ok = False
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid API key")
