"""Human verdict: what the evidence actually shows vs the alert text."""

from __future__ import annotations

import re

from fixops_contract.models import AlertPayload, WorkerResponse


def logs_were_pulled(worker: WorkerResponse) -> bool:
    return any(c.startswith("logs/") for c in worker.checked)


def build_conclusion(alert: AlertPayload, worker: WorkerResponse) -> str:
    """Short, honest paragraphs for the CLI (no LLM required)."""
    paragraphs: list[str] = []
    findings_blob = "\n".join(worker.findings)
    alert_blob = f"{alert.title or ''} {alert.message or ''}"

    if logs_were_pulled(worker):
        paragraphs.append(
            "Container logs **were** fetched from the Kubernetes API. The lines in the summary are "
            "**real output** from the cluster for this investigation slice — not invented by a model."
        )
        low_alert = alert_blob.lower()
        low_find = findings_blob.lower()
        if re.search(r"\b(s3|bucket|aws)\b", low_alert):
            storage_hit = bool(
                re.search(
                    r"\b(s3|amazonaws|access denied|accessdenied|nosuchbucket|forbidden|403|"
                    r"signature|credentials|invalidaccesskey)\b",
                    low_find,
                    re.IGNORECASE,
                )
            )
            if storage_hit:
                paragraphs.append(
                    "**Conclusion:** The captured log tail **includes** wording that can plausibly relate to "
                    "object storage / access (S3-style errors or HTTP codes). Treat that as **supporting** "
                    "the alert; still confirm bucket name, IAM/IRSA, and network from your cloud side."
                )
            else:
                paragraphs.append(
                    "**Conclusion:** In this **tail**, we **do not** see obvious S3 / bucket / AWS access errors "
                    "that match the alert text. That usually means one of: the error is **outside this time "
                    "window**, only on **stderr** elsewhere, **intermittent**, or the alert text is **stale / "
                    "mis-attributed**. This run **does not prove** the alert false — only that this slice "
                    "doesn't show it."
                )
        else:
            paragraphs.append(
                "**Conclusion:** Compare the alert description to the log excerpt. If they align, dig along "
                "that component; if not, widen the log window or query Loki before changing infra."
            )
    else:
        paragraphs.append(
            "**Conclusion:** This run relied on **pod status and events only** (no log tail in the report). "
            "Soft failures that do not change `Running` or restart counts will **not** appear here unless "
            "the alert wording triggers log collection or you set `extra.investigate_logs: true`."
        )

    paragraphs.append(
        f"Worker-reported **confidence** is **{worker.confidence:.2f}** — it reflects how strong the "
        "structured worker felt the **API-visible** evidence was, not a guarantee the alert text is true."
    )
    return "\n\n".join(paragraphs)
