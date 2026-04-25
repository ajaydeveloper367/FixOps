"""AD-009 bounded retrieval tests."""

from fixops_controller.db.models import RagChunk
from fixops_controller.db.sync_session import SyncSessionLocal, init_sync_schema
from fixops_controller.rag.retrieve import retrieve_relevant_chunks_sync


def test_retrieve_relevant_chunks_respects_topk_and_budget() -> None:
    init_sync_schema()
    with SyncSessionLocal() as s:
        s.add_all(
            [
                RagChunk(
                    source_uri="runbook://checkout-crashloop",
                    title="Checkout CrashLoopBackOff Runbook",
                    body="checkout-api crashloop usually means bad env var or failed dependency init.",
                ),
                RagChunk(
                    source_uri="runbook://db-latency",
                    title="Database Latency Playbook",
                    body="Investigate DB locks, connection saturation, and slow query regression first.",
                ),
                RagChunk(
                    source_uri="runbook://noise",
                    title="Unrelated topic",
                    body="This body has unrelated terms and should not score well for checkout crashloop.",
                ),
            ]
        )
        s.commit()

    out = retrieve_relevant_chunks_sync(
        "checkout crashloopbackoff pod failing",
        top_k=2,
        char_budget=180,
    )
    assert len(out) <= 2
    assert out
    assert sum(len(x["snippet"]) for x in out) <= 180
    assert any("checkout" in x["source_uri"] for x in out)


def test_retrieve_empty_query_returns_empty() -> None:
    out = retrieve_relevant_chunks_sync("", top_k=3, char_budget=300)
    assert out == []
