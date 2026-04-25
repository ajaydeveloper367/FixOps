"""Routing table sends known alert classes to new domain workers."""

from fixops_contract.entities import ExtractedEntity

from fixops_controller.routing.rules import load_routing_table, resolve_route


def _registry() -> dict[str, str]:
    return {
        "worker-obs": "http://worker-obs.test",
        "worker-k8s": "http://worker-k8s.test",
        "worker-pipeline": "http://worker-pipeline.test",
        "worker-db": "http://worker-db.test",
        "worker-app-rca": "http://worker-app-rca.test",
    }


def test_pipeline_alert_class_routes_to_pipeline_worker() -> None:
    routing = load_routing_table("config/routing_rules.yaml")
    e = ExtractedEntity(entity_type="service", entity_name="checkout-api", alert_class="PipelineFailure")
    d = resolve_route(e, routing, inventory_entities=[], worker_registry=_registry())
    assert d.worker_id == "worker-pipeline"


def test_db_alert_class_routes_to_db_worker() -> None:
    routing = load_routing_table("config/routing_rules.yaml")
    e = ExtractedEntity(entity_type="service", entity_name="checkout-api", alert_class="DatabaseLatency")
    d = resolve_route(e, routing, inventory_entities=[], worker_registry=_registry())
    assert d.worker_id == "worker-db"


def test_app_alert_class_routes_to_app_rca_worker() -> None:
    routing = load_routing_table("config/routing_rules.yaml")
    e = ExtractedEntity(entity_type="service", entity_name="checkout-api", alert_class="AppRegression")
    d = resolve_route(e, routing, inventory_entities=[], worker_registry=_registry())
    assert d.worker_id == "worker-app-rca"
