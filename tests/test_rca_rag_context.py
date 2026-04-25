"""RCA node includes bounded institutional context in evidence chain."""

from fixops_controller.graph.nodes import node_rca


def test_node_rca_includes_rag_context(monkeypatch) -> None:
    monkeypatch.setattr("fixops_controller.graph.nodes.settings.mock_llm", True)
    monkeypatch.setattr(
        "fixops_controller.graph.nodes.retrieve_relevant_chunks_sync",
        lambda *a, **k: [
            {
                "source_uri": "runbook://checkout-crashloop",
                "title": "CrashLoopBackOff Runbook",
                "snippet": "Check init containers and recent config changes.",
                "score": 2.5,
            }
        ],
    )
    state = {
        "normalized": {"source": "alert", "raw": {"alertname": "PodCrashLoopBackOff"}},
        "extracted": {"entity_type": "pod", "entity_name": "checkout-api-123", "alert_class": "PodCrashLoopBackOff"},
        "merged": {
            "checked": ["prom query"],
            "findings": ["pod repeatedly restarting"],
            "evidence_refs": ["prom:query:..."],
            "ruled_out": [],
            "confidence": 0.82,
        },
        "investigation_id": "i-1",
    }
    out = node_rca(state)  # mock_llm path in tests echoes evidence_chain
    chain = out["rca"]["evidence_chain"]
    assert chain["institutional_context"]
    assert chain["institutional_context"][0]["source_uri"] == "runbook://checkout-crashloop"
