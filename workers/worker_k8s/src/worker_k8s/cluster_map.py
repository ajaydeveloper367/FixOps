"""Map alert.cluster_id to kubeconfig + context (multi-cluster / multi-EKS)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass(frozen=True)
class ClusterKubeCredentials:
    """One EKS (or any) cluster connection."""

    kubeconfig: Path
    context: str | None


def load_cluster_credentials_map(path: Path) -> dict[str, ClusterKubeCredentials]:
    """
    YAML format::

        clusters:
          my-prod-eks:
            kubeconfig: /etc/fixops/kubeconfigs/prod.yaml
            context: arn:aws:eks:us-west-2:123456789012:cluster/prod
          my-dev-eks:
            kubeconfig: /etc/fixops/kubeconfigs/dev.yaml
            context: ""   # optional: use kubeconfig's current-context when empty / omitted
    """
    if not path.is_file():
        raise FileNotFoundError(f"Cluster map path is not a file: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        raise ValueError(f"Cluster map is empty: {path}")
    if not isinstance(raw, dict) or "clusters" not in raw:
        raise ValueError(f"Cluster map must be a YAML object with a top-level 'clusters' key: {path}")
    clusters_raw = raw["clusters"]
    if not isinstance(clusters_raw, dict) or not clusters_raw:
        raise ValueError(f"Cluster map 'clusters' must be a non-empty object: {path}")

    out: dict[str, ClusterKubeCredentials] = {}
    for cluster_id, spec in clusters_raw.items():
        cid = str(cluster_id).strip()
        if not cid:
            continue
        if not isinstance(spec, dict):
            raise ValueError(f"clusters[{cluster_id!r}] must be a mapping with kubeconfig/context")
        kc_val = spec.get("kubeconfig")
        if not kc_val or not isinstance(kc_val, str):
            raise ValueError(f"clusters[{cid!r}] must set string 'kubeconfig' (path to kubeconfig file)")
        kc_path = Path(kc_val).expanduser()
        if not kc_path.is_file():
            raise FileNotFoundError(f"clusters[{cid!r}] kubeconfig is not a file: {kc_path}")
        ctx_val = spec.get("context", None)
        ctx: str | None
        if ctx_val is None or ctx_val == "":
            ctx = None
        elif isinstance(ctx_val, str):
            ctx = ctx_val.strip() or None
        else:
            raise ValueError(f"clusters[{cid!r}].context must be a string or empty")
        out[cid] = ClusterKubeCredentials(kubeconfig=kc_path, context=ctx)
    return out


def format_known_cluster_ids(cluster_map: dict[str, ClusterKubeCredentials], *, limit: int = 24) -> str:
    keys = sorted(cluster_map.keys())
    if len(keys) <= limit:
        return ", ".join(keys)
    head = ", ".join(keys[:limit])
    return f"{head}, … ({len(keys) - limit} more)"
