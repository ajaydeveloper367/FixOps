"""Call the standalone worker-k8s HTTP service (controller has no worker package import)."""

from __future__ import annotations

import httpx

from fixops_contract.models import WorkerInvestigationRequest, WorkerResponse


class WorkerK8sNotConfigured(RuntimeError):
    """CONTROLLER_WORKER_K8S_BASE_URL is unset — controller cannot reach K8s."""


class WorkerK8sTransportError(RuntimeError):
    """Network, timeout, or non-success HTTP from the worker."""


def call_worker_k8s(
    *,
    base_url: str,
    request: WorkerInvestigationRequest,
    timeout_seconds: float,
) -> WorkerResponse:
    url = base_url.rstrip("/") + "/v1/investigate"
    timeout = httpx.Timeout(timeout_seconds, connect=15.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=request.model_dump(mode="json"))
    except httpx.ConnectError as e:
        raise WorkerK8sTransportError(
            f"Could not connect to K8s worker at {base_url!r}. "
            "Start the worker (fixops-worker-k8s-serve) or fix the URL / network."
        ) from e
    except httpx.TimeoutException as e:
        raise WorkerK8sTransportError(
            f"K8s worker at {base_url!r} did not respond within {timeout_seconds}s."
        ) from e
    except httpx.RequestError as e:
        raise WorkerK8sTransportError(f"Request to K8s worker failed: {e}") from e

    if resp.status_code >= 400:
        body = (resp.text or "")[:1500]
        raise WorkerK8sTransportError(
            f"K8s worker returned HTTP {resp.status_code}. Body (truncated): {body}"
        )

    try:
        return WorkerResponse.model_validate(resp.json())
    except Exception as e:
        raise WorkerK8sTransportError(
            f"K8s worker response was not valid WorkerResponse JSON: {e}"
        ) from e
