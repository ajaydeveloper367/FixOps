"""Same extracted entity + rules → same worker (AD-002)."""

from fixops_contract.entities import ExtractedEntity

from fixops_controller.routing.rules import resolve_route


def test_pod_alert_routes_to_worker_obs():
    extracted = ExtractedEntity(
        entity_type="pod",
        entity_name="checkout-api-7d8f9",
        namespace="prod",
        alert_class="PodCrashLoopBackOff",
        labels={},
    )
    routing = {
        "default_worker_id": "worker-obs",
        "rules": [{"match": {"entity_type": "service"}, "worker_id": "worker-obs"}],
    }
    inv = [
        {
            "id": "service:checkout-api",
            "entity_type": "service",
            "data": {
                "service_name": "other",
                "cluster_id": "c1",
                "credentials_ref": "ref:c1",
            },
        }
    ]
    reg = {"worker-obs": "http://worker-obs:8081"}
    d = resolve_route(extracted, routing, inv, reg)
    assert d.worker_id == "worker-obs"
    assert d.worker_base_url == "http://worker-obs:8081"


def test_high_error_rate_rule_overrides_default():
    extracted = ExtractedEntity(
        entity_type="service",
        entity_name="checkout-api",
        alert_class="HighErrorRate",
        labels={},
    )
    routing = {
        "default_worker_id": "worker-obs",
        "rules": [
            {"match": {"alert_class": "HighErrorRate"}, "worker_id": "worker-obs"},
        ],
    }
    inv = [
        {
            "id": "service:checkout-api",
            "entity_type": "service",
            "data": {
                "service_name": "checkout-api",
                "cluster_id": "dev-eks",
                "credentials_ref": "ref:dev",
            },
        }
    ]
    reg = {"worker-obs": "http://obs:8081"}
    d1 = resolve_route(extracted, routing, inv, reg)
    d2 = resolve_route(extracted, routing, inv, reg)
    assert d1.worker_id == d2.worker_id == "worker-obs"
    assert d1.cluster_id == "dev-eks"
