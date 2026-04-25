"""In-worker reasoning uses compact context only — no kubeconfig in prompts."""

from fixops_contract.ad006 import WorkerInvestigateRequest, WorkerResult

from fixops_worker_obs.adapters.prometheus import PrometheusPort


def investigate(req: WorkerInvestigateRequest, prom: PrometheusPort) -> WorkerResult:
    checked: list[str] = []
    findings: list[str] = []
    evidence: list[str] = []
    ruled_out: list[str] = []

    expr = f'up{{namespace="{req.namespace or "default"}"}}'
    if req.entity_type == "service":
        expr = f'up{{job="{req.entity_name}"}}'

    checked.append(f"prometheus instant query: {expr}")
    data = prom.query_instant(expr)
    evidence.append(f"prom:query:{expr}")

    status = data.get("status")
    if status != "success":
        findings.append(f"Prometheus returned status={status}")
        return WorkerResult(
            checked=checked,
            findings=findings,
            evidence_refs=evidence,
            ruled_out=ruled_out,
            confidence=0.35,
            next_suggested_check="Verify Prometheus reachability and scrape targets",
        )

    results = (data.get("data") or {}).get("result") or []
    if not results:
        ruled_out.append("No series matched the selector (service may be down or un-scraped)")
        return WorkerResult(
            checked=checked,
            findings=["No matching series for selector"],
            evidence_refs=evidence,
            ruled_out=ruled_out,
            confidence=0.55,
            next_suggested_check="Expand label selectors using inventory labels",
        )

    findings.append(f"Found {len(results)} series for selector")
    return WorkerResult(
        checked=checked,
        findings=findings,
        evidence_refs=evidence,
        ruled_out=ruled_out,
        confidence=0.82,
        next_suggested_check=None,
    )
