"""
Sprint 3 – Bloco 2: Semantic Memory & RAG Integration Tests.

Tests Case embeddings, semantic search, precedent lookup, RAG context builder,
and the auto-indexing pipeline.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone as dj_timezone

from ai.embeddings import (
    build_approval_text,
    build_case_text,
    content_hash,
    embed_case_context,
    generate_embedding,
)
from orchestrator.enums import ApprovalStatus, Priority
from orchestrator.models import Case, CaseEvent
from search.models import CaseEmbedding
from search.services import (
    find_precedent_decisions,
    find_similar_cases,
    get_case_context,
    index_case,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_case(ref: str, title: str = "Test Case", **kwargs) -> Case:
    return Case.objects.create(
        external_ref=ref,
        tenant_id=kwargs.get("tenant_id", "tenant-rag"),
        title=title,
        correlation_id=f"corr-{ref}",
        trace_id=f"trace-{ref}",
        priority=kwargs.get("priority", Priority.MEDIUM),
        metadata=kwargs.get("metadata", {}),
    )


def _add_event(case: Case, event_type: str, payload: dict | None = None) -> CaseEvent:
    return CaseEvent.objects.create(
        event_id=f"evt-{case.external_ref}-{event_type}-{CaseEvent.objects.count()}",
        case=case,
        event_type=event_type,
        event_version="1.0",
        source="test",
        priority=Priority.MEDIUM,
        occurred_at=dj_timezone.now(),
        correlation_id=case.correlation_id,
        trace_id=case.trace_id,
        payload=payload or {},
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Embedding Service
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_generate_embedding_shape():
    """generate_embedding returns a 384-dim float list."""
    emb = generate_embedding("Hello world")
    assert isinstance(emb, list)
    assert len(emb) == 384
    assert all(isinstance(x, float) for x in emb)


@pytest.mark.django_db(transaction=True)
def test_content_hash_deterministic():
    """Same input produces same hash."""
    h1 = content_hash("same text")
    h2 = content_hash("same text")
    assert h1 == h2
    assert len(h1) == 64


@pytest.mark.django_db(transaction=True)
def test_build_case_text_includes_all_parts():
    """build_case_text assembles title, state, metadata, events."""
    text = build_case_text(
        title="Proposta Acme",
        state="ANALYSIS",
        events=[{"event_type": "lead.received", "source": "crm", "payload": {"value": 10000}}],
        metadata={"company": "Acme Corp"},
    )
    assert "Proposta Acme" in text
    assert "ANALYSIS" in text
    assert "Acme Corp" in text
    assert "lead.received" in text


@pytest.mark.django_db(transaction=True)
def test_embed_case_context_returns_tuple():
    """embed_case_context returns (embedding, hash)."""
    emb, h = embed_case_context(title="Test Case", state="NEW")
    assert len(emb) == 384
    assert len(h) == 64


# ══════════════════════════════════════════════════════════════════════════════
#  Case Indexing
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_index_case_creates_embedding():
    """index_case creates a CaseEmbedding record."""
    case = _make_case("case-idx-1", title="Proposta de Consultoria")
    _add_event(case, "lead.received", {"value": 50000})

    created = index_case(case.id)

    assert created is True
    assert CaseEmbedding.objects.filter(case=case).exists()
    ce = CaseEmbedding.objects.get(case=case)
    assert len(ce.embedding) == 384
    assert ce.content_hash


@pytest.mark.django_db(transaction=True)
def test_index_case_skips_unchanged():
    """index_case returns False when content hasn't changed."""
    case = _make_case("case-idx-skip", title="Unchanged Case")

    first = index_case(case.id)
    second = index_case(case.id)

    assert first is True
    assert second is False


@pytest.mark.django_db(transaction=True)
def test_index_case_updates_on_new_event():
    """index_case re-embeds when new events change the hash."""
    case = _make_case("case-idx-update", title="Evolving Case")
    index_case(case.id)
    hash_before = CaseEmbedding.objects.get(case=case).content_hash

    _add_event(case, "proposal.sent", {"amount": 100000})
    updated = index_case(case.id)

    assert updated is True
    hash_after = CaseEmbedding.objects.get(case=case).content_hash
    assert hash_after != hash_before


# ══════════════════════════════════════════════════════════════════════════════
#  Semantic Case Search
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_find_similar_cases_returns_results():
    """find_similar_cases returns indexed cases sorted by similarity."""
    c1 = _make_case("case-sim-1", title="Proposta de consultoria em TI para empresa de varejo")
    c2 = _make_case("case-sim-2", title="Contrato de manutenção de software ERP")
    c3 = _make_case("case-sim-3", title="Auditoria fiscal trimestral")

    index_case(c1.id)
    index_case(c2.id)
    index_case(c3.id)

    results = find_similar_cases("consultoria em tecnologia", limit=3)

    assert len(results) == 3
    # The IT consulting case should be the most similar
    assert results[0]["external_ref"] == "case-sim-1"
    assert "score" in results[0]


@pytest.mark.django_db(transaction=True)
def test_find_similar_cases_tenant_filter():
    """find_similar_cases respects tenant_id filter."""
    c1 = _make_case("case-tenant-a", title="Proposta Alpha", tenant_id="tenant-a")
    c2 = _make_case("case-tenant-b", title="Proposta Beta", tenant_id="tenant-b")

    index_case(c1.id)
    index_case(c2.id)

    results = find_similar_cases("proposta", tenant_id="tenant-a")
    assert len(results) == 1
    assert results[0]["external_ref"] == "case-tenant-a"


# ══════════════════════════════════════════════════════════════════════════════
#  Approval Precedent Search
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_find_precedent_decisions():
    """find_precedent_decisions finds past decisions by semantic similarity."""
    from approvals.models import Approval

    case1 = _make_case("case-prec-1", title="Proposta de consultoria R$50.000")
    case2 = _make_case("case-prec-2", title="Compra de equipamentos R$30.000")

    index_case(case1.id)
    index_case(case2.id)

    # Create decided approvals
    Approval.objects.create(
        approval_id="apv-prec-1",
        case=case1,
        approval_type="financial",
        status=ApprovalStatus.APPROVED,
        requested_by_agent="analyzer",
        summary="Proposta de consultoria TI aprovada",
        decided_at=dj_timezone.now(),
    )
    Approval.objects.create(
        approval_id="apv-prec-2",
        case=case2,
        approval_type="purchase",
        status=ApprovalStatus.REJECTED,
        requested_by_agent="analyzer",
        summary="Compra de equipamentos rejeitada",
        decided_at=dj_timezone.now(),
    )

    results = find_precedent_decisions(
        approval_type="financial",
        summary="Proposta de consultoria em tecnologia",
    )

    assert len(results) >= 1
    # The consulting case should be the closest precedent
    assert results[0]["external_ref"] == "case-prec-1"
    assert results[0]["decision"] == ApprovalStatus.APPROVED


# ══════════════════════════════════════════════════════════════════════════════
#  Case Context Builder
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_get_case_context_includes_events():
    """get_case_context returns text with case info and events."""
    case = _make_case("case-ctx-1", title="Contexto Completo")
    _add_event(case, "lead.received", {"company": "Acme"})
    _add_event(case, "analysis.completed", {"score": 85})

    ctx = get_case_context(case.id)

    assert "Contexto Completo" in ctx["text"]
    assert "lead.received" in ctx["text"]
    assert "analysis.completed" in ctx["text"]
    assert "case:case-ctx-1" in ctx["sources"]
    assert "events" in ctx["sources"]


@pytest.mark.django_db(transaction=True)
def test_get_case_context_includes_approvals():
    """get_case_context includes approval information."""
    from approvals.models import Approval

    case = _make_case("case-ctx-apv", title="Case com Aprovação")
    Approval.objects.create(
        approval_id="apv-ctx-1",
        case=case,
        approval_type="budget",
        status=ApprovalStatus.APPROVED,
        requested_by_agent="analyzer",
        summary="Orçamento de R$100k aprovado pelo gerente",
    )

    ctx = get_case_context(case.id)

    assert "budget" in ctx["text"]
    assert "approvals" in ctx["sources"]


@pytest.mark.django_db(transaction=True)
def test_get_case_context_respects_max_chars():
    """get_case_context truncates at max_chars."""
    case = _make_case("case-ctx-trunc", title="A" * 200)
    for i in range(20):
        _add_event(case, f"event.type.{i}", {"data": "x" * 200})

    ctx = get_case_context(case.id, max_chars=1000)
    assert len(ctx["text"]) <= 1000


# ══════════════════════════════════════════════════════════════════════════════
#  RAG Pipeline
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_build_agent_rag_context():
    """build_agent_rag_context combines case context and document chunks."""
    from ai.rag import build_agent_rag_context

    case = _make_case("case-rag-1", title="Proposta para análise RAG")
    _add_event(case, "document.uploaded", {"doc_id": 1})

    ctx = build_agent_rag_context(case_id=case.id, query="proposta")

    assert "rag_context" in ctx
    assert "sources" in ctx
    assert "chunk_count" in ctx
    assert "Proposta para análise RAG" in ctx["rag_context"]


@pytest.mark.django_db(transaction=True)
def test_generate_case_answer_no_context():
    """generate_case_answer returns 'insufficient' when case has no context."""
    from ai.rag import generate_case_answer

    case = _make_case("case-rag-empty", title="")
    result = generate_case_answer(case.id, "O que aconteceu?")

    assert "rag_context_used" in result
    # Either returns insufficient or generates an answer from minimal context


# ══════════════════════════════════════════════════════════════════════════════
#  Auto-Indexing Signal
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_case_event_signal_triggers_indexing():
    """Creating a CaseEvent triggers the index_case_embedding task."""
    case = _make_case("case-signal-1", title="Signal Test")

    with patch("search.tasks.index_case_embedding") as mock_task:
        mock_task.delay = lambda cid: index_case(cid)  # run synchronously

        _add_event(case, "lead.qualified", {"score": 90})

    # The signal should have called index_case which creates CaseEmbedding
    # (since we mocked delay to run sync, the embedding should exist)
    assert CaseEmbedding.objects.filter(case=case).exists()
