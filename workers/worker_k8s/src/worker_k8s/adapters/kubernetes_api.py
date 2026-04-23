from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException


@dataclass(frozen=True)
class ContainerStateBrief:
    """Per-container status (CrashLoop / OOM / exit code live here)."""

    name: str
    restart_count: int
    waiting_reason: str | None
    terminated_reason: str | None
    exit_code: int | None
    signal: int | None
    terminated_message: str | None


@dataclass(frozen=True)
class PodSnapshot:
    exists: bool
    name: str
    namespace: str
    phase: str | None
    reason: str | None
    message: str | None
    # Aggregate / worst-case hints (first non-null among containers)
    container_waiting_reason: str | None
    last_state_terminated_reason: str | None
    restart_count: int
    container_states: tuple[ContainerStateBrief, ...]
    raw_status: dict[str, Any] | None


@dataclass(frozen=True)
class EventSummary:
    """One row for evidence_refs."""

    ref: str
    type: str
    reason: str
    message: str
    involved_kind: str | None
    involved_name: str | None


class KubernetesApiAdapter:
    """All cluster reads go through here (testability + audit boundary)."""

    def __init__(self, *, kubeconfig: str | None, context: str | None) -> None:
        # Isolated Configuration + ApiClient so concurrent requests (multi-cluster)
        # do not mutate the process-wide default kube config.
        configuration = client.Configuration()
        if kubeconfig:
            config.load_kube_config(
                config_file=kubeconfig,
                context=context,
                client_configuration=configuration,
            )
        else:
            try:
                config.load_incluster_config(client_configuration=configuration)
            except config.ConfigException:
                config.load_kube_config(
                    context=context,
                    client_configuration=configuration,
                )
        self._api_client = client.ApiClient(configuration)
        self._v1 = client.CoreV1Api(self._api_client)
        self._apps = client.AppsV1Api(self._api_client)

    def close(self) -> None:
        self._api_client.close()

    def read_pod(self, namespace: str, name: str) -> PodSnapshot:
        try:
            pod = self._v1.read_namespaced_pod(name=name, namespace=namespace)
        except ApiException as e:
            if e.status == 404:
                return PodSnapshot(
                    exists=False,
                    name=name,
                    namespace=namespace,
                    phase=None,
                    reason=None,
                    message=None,
                    container_waiting_reason=None,
                    last_state_terminated_reason=None,
                    restart_count=0,
                    container_states=(),
                    raw_status=None,
                )
            raise
        status = pod.status
        phase = status.phase
        reason = status.reason
        message = status.message
        cwr: str | None = None
        lstr: str | None = None
        restarts = 0
        briefs: list[ContainerStateBrief] = []
        if status.container_statuses:
            for cs in status.container_statuses:
                cname = cs.name or "unknown"
                rc = int(cs.restart_count or 0)
                restarts += rc
                wr: str | None = None
                if cs.state and cs.state.waiting and cs.state.waiting.reason:
                    wr = cs.state.waiting.reason
                    if cwr is None:
                        cwr = wr
                tr: str | None = None
                ec: int | None = None
                sig: int | None = None
                tm: str | None = None
                if cs.last_state and cs.last_state.terminated:
                    t = cs.last_state.terminated
                    tr = t.reason
                    ec = t.exit_code
                    sig = t.signal
                    tm = t.message
                    if lstr is None and tr:
                        lstr = tr
                briefs.append(
                    ContainerStateBrief(
                        name=cname,
                        restart_count=rc,
                        waiting_reason=wr,
                        terminated_reason=tr,
                        exit_code=ec,
                        signal=sig,
                        terminated_message=tm,
                    )
                )
        raw = None
        if status:
            raw = self._api_obj_to_dict(status)
        return PodSnapshot(
            exists=True,
            name=name,
            namespace=namespace,
            phase=phase,
            reason=reason,
            message=message,
            container_waiting_reason=cwr,
            last_state_terminated_reason=lstr,
            restart_count=restarts,
            container_states=tuple(briefs),
            raw_status=raw,
        )

    def list_configmap_names_for_container(
        self, namespace: str, pod_name: str, container_name: str
    ) -> list[str]:
        """ConfigMap names mounted into the given container (for provisioning forensics)."""
        pod = self._v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        spec = pod.spec
        if not spec or not spec.volumes:
            return []
        vol_by_name = {v.name: v for v in spec.volumes if v.name}
        names: list[str] = []
        for c in spec.containers or []:
            if c.name != container_name:
                continue
            for vm in c.volume_mounts or []:
                v = vol_by_name.get(vm.name)
                if v and v.config_map and v.config_map.name:
                    names.append(v.config_map.name)
        # preserve order, unique
        seen: set[str] = set()
        out: list[str] = []
        for n in names:
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def read_config_map_data(self, namespace: str, name: str) -> dict[str, str]:
        cm = self._v1.read_namespaced_config_map(name=name, namespace=namespace)
        return dict(cm.data or {})

    def read_pod_container_log(
        self,
        namespace: str,
        pod_name: str,
        container: str,
        *,
        previous: bool,
        tail_lines: int = 120,
    ) -> str | None:
        """Returns None if logs are unavailable (e.g. no previous instance yet)."""
        try:
            return self._v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container,
                previous=previous,
                tail_lines=tail_lines,
                timestamps=True,
            )
        except ApiException as e:
            if e.status in (400, 404):
                return None
            raise

    def list_recent_events(
        self,
        namespace: str,
        *,
        limit: int = 80,
        for_name_substring: str | None = None,
    ) -> list[EventSummary]:
        ev_list = self._v1.list_namespaced_event(
            namespace=namespace,
            limit=limit,
        )
        out: list[EventSummary] = []
        for ev in ev_list.items or []:
            involved = ev.involved_object
            ik = involved.kind if involved else None
            iname = involved.name if involved else None
            msg = ev.message or ""
            if for_name_substring and for_name_substring not in (
                iname or ""
            ) and for_name_substring not in msg:
                continue
            ref = f"event/{namespace}/{ev.metadata.uid or ev.metadata.name}"
            out.append(
                EventSummary(
                    ref=ref,
                    type=ev.type or "Normal",
                    reason=ev.reason or "",
                    message=msg,
                    involved_kind=ik,
                    involved_name=iname,
                )
            )
        return out[:limit]

    def read_deployment(self, namespace: str, name: str) -> dict[str, Any] | None:
        try:
            d = self._apps.read_namespaced_deployment(name=name, namespace=namespace)
        except ApiException as e:
            if e.status == 404:
                return None
            raise
        spec = d.spec
        st = d.status
        return {
            "name": d.metadata.name,
            "namespace": namespace,
            "replicas_desired": (spec.replicas if spec else None),
            "ready_replicas": st.ready_replicas if st else None,
            "available_replicas": st.available_replicas if st else None,
            "conditions": [
                {
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason,
                    "message": c.message,
                }
                for c in (st.conditions or [])
            ]
            if st
            else [],
        }

    @staticmethod
    def _api_obj_to_dict(obj: Any) -> dict[str, Any]:
        try:
            return obj.to_dict()  # type: ignore[no-any-return]
        except Exception:
            return {}
