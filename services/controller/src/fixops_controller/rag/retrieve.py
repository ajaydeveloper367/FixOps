"""AD-009 bounded institutional retrieval (sync path for graph nodes)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from fixops_controller.db.models import RagChunk
from fixops_controller.db.sync_session import SyncSessionLocal


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]+", text.lower()) if len(t) >= 3}


def retrieve_relevant_chunks_sync(
    query_text: str,
    *,
    top_k: int = 3,
    char_budget: int = 1200,
) -> list[dict[str, Any]]:
    """Return bounded top-k snippets by lexical overlap score."""
    q = (query_text or "").strip()
    if not q or top_k <= 0 or char_budget <= 0:
        return []
    query_terms = _tokens(q)
    if not query_terms:
        return []

    try:
        with SyncSessionLocal() as s:
            rows = s.scalars(select(RagChunk).order_by(RagChunk.id.desc()).limit(300)).all()
    except SQLAlchemyError:
        # RAG schema may be absent in early environments; retrieval must fail open.
        return []

    scored: list[tuple[float, RagChunk]] = []
    for r in rows:
        title = str(r.title or "")
        body = str(r.body or "")
        terms = _tokens(f"{title} {body}")
        if not terms:
            continue
        overlap = query_terms.intersection(terms)
        if not overlap:
            continue
        # Favor dense overlap with slight title weight.
        title_terms = _tokens(title)
        title_overlap = len(query_terms.intersection(title_terms))
        score = float(len(overlap)) + (0.25 * float(title_overlap))
        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    out: list[dict[str, Any]] = []
    used_chars = 0
    for score, row in scored:
        if len(out) >= top_k:
            break
        snippet = (row.body or "").strip()
        if not snippet:
            continue
        # Keep each chunk compact so total fits bounded prompt budget.
        snippet = snippet[:320]
        if used_chars + len(snippet) > char_budget:
            remain = char_budget - used_chars
            if remain < 80:
                break
            snippet = snippet[:remain]
        out.append(
            {
                "source_uri": row.source_uri,
                "title": row.title or "",
                "snippet": snippet,
                "score": round(score, 3),
            }
        )
        used_chars += len(snippet)
        if used_chars >= char_budget:
            break
    return out
