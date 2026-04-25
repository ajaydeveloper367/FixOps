"""Backfill ``ExtractedEntity`` from ``normalized.raw`` when the LLM leaves fields blank."""

from __future__ import annotations

import pytest
from fixops_contract.entities import ExtractedEntity

from fixops_controller.llm.extract import (
    _sanitize_llm_extracted_dict,
    coalesce_extracted_from_normalized,
)


def test_coalesce_fills_entity_name_from_pod_and_namespace_from_raw() -> None:
    normalized = {
        "source": "alert",
        "raw": {
            "alertname": "PodCrashLoopBackOff",
            "namespace": "prod",
            "pod": "checkout-api-7d8f9",
            "labels": {"entity_type": "pod", "app": "checkout-api"},
        },
    }
    bad = ExtractedEntity(
        entity_type="pod",
        entity_name="",
        namespace=None,
        alert_class=None,
        labels={"app": ""},
    )
    out = coalesce_extracted_from_normalized(bad, normalized)
    assert out.entity_name == "checkout-api-7d8f9"
    assert out.namespace == "prod"
    assert out.alert_class == "PodCrashLoopBackOff"
    assert out.labels["app"] == "checkout-api"
    assert out.labels["entity_type"] == "pod"


def test_coalesce_entity_name_from_app_when_no_pod() -> None:
    normalized = {
        "source": "alert",
        "raw": {
            "namespace": "ns1",
            "labels": {"app": "payments-api"},
        },
    }
    bad = ExtractedEntity(entity_type="pod", entity_name="   ", labels={})
    out = coalesce_extracted_from_normalized(bad, normalized)
    assert out.entity_name == "payments-api"
    assert out.namespace == "ns1"


def test_coalesce_unknown_when_raw_empty() -> None:
    bad = ExtractedEntity(entity_type="", entity_name="", labels={})
    out = coalesce_extracted_from_normalized(bad, {"source": "alert", "raw": {}})
    assert out.entity_name == "unknown"
    assert out.entity_type == "pod"


def test_extract_entity_llm_coalesces_after_llm_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM path is patched to return blanks; coalesce must still fill from ``raw``."""
    from fixops_controller.llm import extract as extract_mod
    from fixops_controller.llm.extract import extract_entity_llm
    from fixops_controller.settings import settings

    monkeypatch.setattr(settings, "mock_llm", False)
    monkeypatch.setattr(settings, "llm_base_url", "http://127.0.0.1:9/v1")

    def fake_json(*_a: object, **_k: object) -> dict:
        return {
            "entity_type": "pod",
            "entity_name": "",
            "namespace": None,
            "alert_class": None,
            "labels": {"app": ""},
        }

    monkeypatch.setattr(extract_mod, "chat_completion_json", fake_json)

    normalized = {
        "source": "alert",
        "raw": {
            "alertname": "PodCrashLoopBackOff",
            "namespace": "prod",
            "pod": "checkout-api-7d8f9",
            "labels": {"entity_type": "pod", "app": "checkout-api"},
        },
    }
    out = extract_entity_llm(normalized)
    assert out.entity_name == "checkout-api-7d8f9"
    assert out.namespace == "prod"
    assert out.alert_class == "PodCrashLoopBackOff"
    assert out.labels["app"] == "checkout-api"


def test_sanitize_llm_extracted_strips_null_and_empty_label_keys() -> None:
    """Ollama/OpenAI sometimes emit null label values or \"\" keys — must validate."""
    raw = {
        "entity_type": "pod",
        "entity_name": "p-1",
        "namespace": "prod",
        "alert_class": "PodCrashLoopBackOff",
        "labels": {
            "app": "checkout-api",
            "empty": None,
            "": None,
            "nested": {"k": 1},
        },
    }
    clean = _sanitize_llm_extracted_dict(raw)
    ent = ExtractedEntity.model_validate(clean)
    assert ent.labels["app"] == "checkout-api"
    assert "empty" not in ent.labels
    assert "" not in ent.labels
    assert "nested" in ent.labels
    assert "k" in ent.labels["nested"]
