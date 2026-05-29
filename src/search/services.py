"""
Semantic search services.

- ``semantic_search``           — Document chunk similarity (existing)
- ``find_similar_cases``        — Case-level similarity via CaseEmbedding
- ``find_precedent_decisions``  — Approval precedent lookup
- ``get_case_context``          — Build a RAG context window for a Case
- ``index_case``                — Upsert embedding for a Case
"""

from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from pgvector.django import CosineDistance

from ai.embeddings import (
    content_hash,
    embed_approval,
    embed_case_context,
    generate_embedding,
)
from documents.models import DocumentChunk

logger = logging.getLogger(__name__)


# ── Document chunk search (existing) ──────────────────────────────────────────

def semantic_search(document_ids, query, limit=5):
    query_embedding = generate_embedding(query)

    qs = DocumentChunk.objects
    if document_ids:
        qs = qs.filter(document_id__in=document_ids)

    chunks = (
        qs
        .annotate(similarity=CosineDistance("embedding", query_embedding))
        .order_by("similarity")[:limit]
    )

    results = []

    for chunk in chunks:
        results.append({
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "content": chunk.content,
            "score": float(chunk.similarity),
        })

    return results


# ── Case-level similarity search ──────────────────────────────────────────────

def find_similar_cases(query: str, limit: int = 5, tenant_id: str | None = None) -> list[dict]:
    """
    Find Cases whose embedded context is closest to *query*.

    Returns a list of dicts with ``case_id``, ``external_ref``, ``title``,
    ``state``, ``score`` (cosine distance — lower is more similar).
    """
    from search.models import CaseEmbedding

    query_embedding = generate_embedding(query)

    qs = CaseEmbedding.objects.select_related("case")
    if tenant_id:
        qs = qs.filter(case__tenant_id=tenant_id)

    results = (
        qs
        .annotate(distance=CosineDistance("embedding", query_embedding))
        .order_by("distance")[:limit]
    )

    return [
        {
            "case_id": r.case_id,
            "external_ref": r.case.external_ref,
            "title": r.case.title,
            "state": r.case.state,
            "score": float(r.distance),
        }
        for r in results
    ]


# ── Approval precedent search ────────────────────────────────────────────────

def find_precedent_decisions(
    approval_type: str,
    summary: str = "",
    payload: Optional[dict] = None,
    limit: int = 5,
) -> list[dict]:
    """
    Find past Approval decisions that are semantically similar to a new request.

    Embeds the query from approval fields, then searches approved/rejected
    approvals by their Case embeddings.
    """
    from approvals.models import Approval
    from orchestrator.enums import ApprovalStatus
    from search.models import CaseEmbedding

    embedding, _ = embed_approval(
        approval_type=approval_type,
        summary=summary,
        payload=payload,
    )

    # Find cases with similar embeddings that have completed approvals
    case_ids_with_decisions = (
        Approval.objects
        .filter(status__in=[ApprovalStatus.APPROVED, ApprovalStatus.REJECTED])
        .values_list("case_id", flat=True)
        .distinct()
    )

    qs = (
        CaseEmbedding.objects
        .filter(case_id__in=case_ids_with_decisions)
        .select_related("case")
        .annotate(distance=CosineDistance("embedding", embedding))
        .order_by("distance")[:limit]
    )

    results = []
    for r in qs:
        # Fetch the most recent approval decision for this case
        approval = (
            Approval.objects
            .filter(
                case_id=r.case_id,
                status__in=[ApprovalStatus.APPROVED, ApprovalStatus.REJECTED],
            )
            .order_by("-decided_at")
            .first()
        )
        if approval:
            results.append({
                "case_id": r.case_id,
                "external_ref": r.case.external_ref,
                "title": r.case.title,
                "approval_type": approval.approval_type,
                "decision": approval.status,
                "decided_at": approval.decided_at,
                "summary": approval.summary,
                "score": float(r.distance),
            })

    return results


# ── RAG context builder ──────────────────────────────────────────────────────

def get_case_context(case_id: int, max_chars: int = 4000) -> dict:
    """
    Build a rich context window for a Case, combining:
    - Case metadata
    - Recent events
    - Related document chunks (top-5 most relevant)
    - Past approval decisions

    Returns ``{"text": str, "sources": list[str]}``.
    """
    from orchestrator.models import Case, CaseEvent
    from approvals.models import Approval

    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return {"text": "", "sources": []}

    parts: list[str] = []
    sources: list[str] = []

    # Case header
    parts.append(f"Case: {case.title} ({case.external_ref})")
    parts.append(f"Estado: {case.state} | Prioridade: {case.priority}")
    if case.metadata:
        parts.append(f"Metadata: {str(case.metadata)[:300]}")
    sources.append(f"case:{case.external_ref}")

    # Recent events (last 10)
    events = (
        CaseEvent.objects
        .filter(case=case)
        .order_by("-occurred_at")[:10]
    )
    if events:
        parts.append("\n--- Eventos recentes ---")
        for evt in events:
            payload_str = str(evt.payload)[:150]
            parts.append(f"[{evt.event_type}] {evt.source}: {payload_str}")
        sources.append("events")

    # Approvals
    approvals = Approval.objects.filter(case=case).order_by("-requested_at")[:5]
    if approvals:
        parts.append("\n--- Aprovações ---")
        for apv in approvals:
            parts.append(f"[{apv.status}] {apv.approval_type}: {apv.summary[:100]}")
        sources.append("approvals")

    # Related document chunks (semantic search by case title)
    try:
        doc_chunks = semantic_search(
            document_ids=None,
            query=case.title,
            limit=5,
        )
        if doc_chunks:
            parts.append("\n--- Documentos relacionados ---")
            for ch in doc_chunks:
                parts.append(ch["content"][:300])
            sources.append("documents")
    except Exception:
        logger.debug("No document chunks available for case context", exc_info=True)

    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars]

    return {"text": text, "sources": sources}


# ── Case indexing ─────────────────────────────────────────────────────────────

def index_case(case_id: int) -> bool:
    """
    Upsert the CaseEmbedding for a given Case.

    Skips re-embedding if the content hash hasn't changed.
    Returns True if a new embedding was written.
    """
    from orchestrator.models import Case, CaseEvent
    from search.models import CaseEmbedding

    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return False

    events = list(
        CaseEvent.objects
        .filter(case=case)
        .order_by("-occurred_at")[:10]
        .values("event_type", "source", "payload")
    )

    embedding, text_hash = embed_case_context(
        title=case.title,
        state=case.state,
        events=events,
        metadata=case.metadata,
    )

    # Skip if unchanged
    existing = CaseEmbedding.objects.filter(case=case).first()
    if existing and existing.content_hash == text_hash:
        return False

    CaseEmbedding.objects.update_or_create(
        case=case,
        defaults={"embedding": embedding, "content_hash": text_hash},
    )
    logger.info("[search] indexed case=%s hash=%s", case.external_ref, text_hash[:12])
    return True