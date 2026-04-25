"""In-worker reasoning uses compact context only — no kubeconfig in prompts."""

from __future__ import annotations

from fixops_contract.ad006 import WorkerInvestigateRequest, WorkerResult

from fixops_worker_obs.adapters.prometheus import PrometheusPort


def _label_value(s: str) -> str:
    """Escape a string for use inside PromQL double-quoted label values."""
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def _instant_query_candidates(req: WorkerInvestigateRequest) -> list[str]:
    """Ordered PromQL attempts: tight selectors first, then looser fallbacks (local dev clusters)."""
    et = (req.entity_type or "pod").lower()
    if et == "service":
        return [f'up{{job="{_label_value(req.entity_name)}"}}']

    ns = (req.namespace or "").strip() or "default"
    ns_l = _label_value(ns)
    seen: set[str] = set()
    out: list[str] = []

    def add(expr: str) -> None:
        if expr not in seen:
            seen.add(expr)
            out.append(expr)

    add(f'up{{namespace="{ns_l}"}}')
    app = (req.labels or {}).get("app", "").strip()
    if app:
        add(f'up{{job="{_label_value(app)}"}}')
        add(f'up{{namespace="{ns_l}",job="{_label_value(app)}"}}')
    if ns != "default":
        add('up{namespace="default"}')
    add("count(up)")
    return out


def investigate(req: WorkerInvestigateRequest, prom: PrometheusPort) -> WorkerResult:
    checked: list[str] = []
    findings: list[str] = []
    evidence: list[str] = []
    ruled_out: list[str] = []

    candidates = _instant_query_candidates(req)

    for i, expr in enumerate(candidates):
        checked.append(f"prometheus instant query: {expr}")
        data = prom.query_instant(expr)
        evidence.append(f"prom:query:{expr}")

        status = data.get("status")
        if status != "success":
            findings.append(f"Prometheus returned status={status} for {expr!r}")
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
            ruled_out.append(f"No series for {expr!r}")
            continue

        if expr == "count(up)":
            findings.append(
                "Prometheus reports active `up` samples (count(up)) but tighter namespace/job "
                "selectors returned no series — targets may use different labels than the alert."
            )
            conf = 0.62
        elif i == 0:
            findings.append(f"Found {len(results)} series for selector")
            conf = 0.82
        else:
            findings.append(
                f"Found {len(results)} series for fallback selector {expr!r} "
                f"(earlier selectors in this probe returned no series)"
            )
            conf = 0.72

        return WorkerResult(
            checked=checked,
            findings=findings,
            evidence_refs=evidence,
            ruled_out=ruled_out,
            confidence=conf,
            next_suggested_check=None if conf >= 0.8 else "Align scrape labels (namespace/job/pod) with alert labels or inventory",
        )

    ruled_out.append("No series matched any candidate selector including count(up)")
    return WorkerResult(
        checked=checked,
        findings=["No matching series for any candidate selector"],
        evidence_refs=evidence,
        ruled_out=ruled_out,
        confidence=0.45,
        next_suggested_check="Verify Prometheus has scrape targets and label names match this cluster",
    )
