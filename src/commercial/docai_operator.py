"""
DocAI Operator (Sprint 4 / Phase 2 — real implementation).

Pipeline:  Lead + Document → RAG context retrieval → DOCAI_OPERATOR (normalize)
           → ANALYST (ranked commercial insights) → persist + emit.

Uses Sprint 3 infra:
- ``search.services.semantic_search``  — document-chunk vector search
- ``search.services.get_case_context`` — RAG context builder
- ``search.services.index_case``       — upsert case embedding
- ``ai.embeddings.generate_embedding`` — 384-dim sentence-transformers

Approval-first: the output itself is informational. Any **external action**
(follow-up, proposal) triggered from these insights still goes through
ApprovalGateway.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from django.utils import timezone

from agent_runtime.prompt_registry import AgentType, PromptRegistry
from agent_runtime.runner import AgentRunner
from audit.services import write_audit_log
from commercial.models import Lead
from commercial.services import _hash_inputs, _new_correlation_id, _new_event_id, _run_async
from core.governance import DecisionLineage
from core.settings import LLM_PROVIDER
from documents.models import Document
from orchestrator.enums import EventType, Priority
from orchestrator.services import ingest_event

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _summarise_document(document: Document) -> dict[str, Any]:
    """Extract a concise, structured representation of a Document for the LLM."""
    metadata = document.extracted_metadata or {}
    text = (document.extracted_text or "")[:4000]
    return {
        "document_id": document.id,
        "title": document.title,
        "document_type": document.document_type,
        "processing_status": document.processing_status,
        "reference_date": document.reference_date.isoformat() if document.reference_date else None,
        "expiration_date": document.expiration_date.isoformat() if document.expiration_date else None,
        "metadata_summary": {
            k: v
            for k, v in metadata.items()
            if isinstance(v, (str, int, float, bool, list, dict)) and k not in {"raw_text"}
        },
        "text_excerpt": text,
    }


def _build_rag_context(lead: Lead, document: Document) -> str:
    """
    Build a RAG context window from:
    1. Semantic search on document chunks (vector similarity to lead profile).
    2. Case context (events, approvals, memory) if the lead has a Case.
    3. Similar-case precedents.
    """
    parts: list[str] = []
    retrieved_ids: list[str] = []

    # 1. Semantic search on document chunks by lead profile query.
    query = f"{lead.company_name or ''} {lead.industry or ''} {document.title} {document.document_type}"
    try:
        from search.services import semantic_search
        chunks = semantic_search(
            document_ids=[document.id],
            query=query.strip(),
            limit=5,
        )
        for ch in chunks:
            parts.append(ch["content"][:600])
            retrieved_ids.append(f"chunk:{ch['chunk_id']}")
    except Exception as exc:
        logger.debug("RAG chunk search unavailable: %s", exc)

    # 2. Case context (if lead has a linked case).
    if lead.case_id:
        try:
            from search.services import get_case_context
            ctx = get_case_context(lead.case_id, max_chars=2000)
            if ctx["text"]:
                parts.append("--- Contexto do case ---")
                parts.append(ctx["text"])
                retrieved_ids.extend(ctx["sources"])
        except Exception as exc:
            logger.debug("RAG case context unavailable: %s", exc)

    # 3. Find similar cases (cross-tenant for internal ops).
    try:
        from search.services import find_similar_cases
        similar = find_similar_cases(query=query.strip(), limit=3, tenant_id=lead.tenant_id)
        if similar:
            parts.append("--- Cases similares ---")
            for s in similar:
                parts.append(f"[{s['external_ref']}] {s['title']} ({s['state']}) score={s['score']:.3f}")
                retrieved_ids.append(f"case:{s['case_id']}")
    except Exception as exc:
        logger.debug("RAG similar cases unavailable: %s", exc)

    return "\n".join(parts) if parts else "(nenhum contexto RAG disponível)", retrieved_ids


def _rank_insights(insights: list[dict]) -> list[dict]:
    """Sort insights by score (descending) and cap at 5."""
    for ins in insights:
        if "score" not in ins or not isinstance(ins.get("score"), (int, float)):
            ins["score"] = 50
    return sorted(insights, key=lambda x: x.get("score", 0), reverse=True)[:5]


# ── Main entry point ─────────────────────────────────────────────────────────

def run_docai_demo(*, lead_id: int, document_id: int) -> dict[str, Any]:
    """
    Run a full DocAI demo analysis for a lead's document.

    Steps:
    1. Build RAG context (embeddings + vector search + case context).
    2. DOCAI_OPERATOR agent normalises/validates the document analysis.
    3. ANALYST agent generates ranked commercial insights.
    4. Persist insights on Lead, write audit, emit event.

    Returns the complete insight payload.
    """
    lead = Lead.objects.select_related("case").get(pk=lead_id)
    document = Document.objects.get(pk=document_id)
    correlation_id = lead.correlation_id or _new_correlation_id()

    doc_summary = _summarise_document(document)

    # ── Step 0: Ensure case is indexed for future similarity lookups ──────
    if lead.case_id:
        try:
            from search.services import index_case
            index_case(lead.case_id)
        except Exception:
            logger.debug("Could not index case for lead %s", lead.lead_id)

    # ── Step 1: RAG context ───────────────────────────────────────────────
    rag_text, retrieved_ids = _build_rag_context(lead, document)

    # ── Step 2: DOCAI_OPERATOR — normalise document analysis ──────────────
    operator_context = {
        "document_info": doc_summary,
        "previous_analyses": [],
    }

    runner = AgentRunner(llm_provider=LLM_PROVIDER)

    operator_result = _run_async(
        runner.execute_agent_command(
            agent_type=AgentType.DOCAI_OPERATOR,
            context=operator_context,
            correlation_id=correlation_id,
            use_cache=False,
        )
    )

    operator_output = operator_result.output or {}
    extracted_data = operator_output.get("extracted_data") or doc_summary["metadata_summary"]

    # ── Step 3: ANALYST — commercial insights with RAG context ────────────
    analyst_context = {
        "lead_profile": {
            "lead_id": lead.lead_id,
            "company_name": lead.company_name,
            "industry": lead.industry,
            "score": lead.score,
            "country": lead.country,
            "company_size": lead.company_size,
        },
        "docai_analysis": extracted_data,
        "document_summary": doc_summary,
        "rag_context": rag_text,
    }

    # Resolve prompt version for lineage tracking.
    prompt_record = PromptRegistry.get_prompt(AgentType.ANALYST)
    prompt_version = prompt_record.version if prompt_record else 0

    analyst_result = _run_async(
        runner.execute_agent_command(
            agent_type=AgentType.ANALYST,
            context=analyst_context,
            correlation_id=correlation_id,
            use_cache=False,
        )
    )
    analyst_output = analyst_result.output or {}

    # ── Step 4: Build the output ──────────────────────────────────────────
    used_heuristic = False
    insights = analyst_output.get("insights")
    if not insights:
        insights = _heuristic_insights(lead=lead, document=document, extracted=extracted_data)
        used_heuristic = True

    insights = _rank_insights(insights)

    summary_text = analyst_output.get("summary")
    if not summary_text:
        summary_text = _heuristic_summary(lead=lead, document=document, extracted=extracted_data)
        used_heuristic = True

    automations = analyst_output.get("automations") or _heuristic_automations(document)

    # Provider info for frontend
    provider_used = LLM_PROVIDER if (operator_result.is_success() or analyst_result.is_success()) else "heuristic"

    insight_payload: dict[str, Any] = {
        "lead_id": lead.lead_id,
        "document_id": document.id,
        "generated_at": timezone.now().isoformat(),
        "extracted_data": extracted_data,
        "insights": insights,
        "seller_summary": summary_text,
        "automations": automations,
        "rag_sources": retrieved_ids,
        "operator_confidence": operator_output.get("confidence"),
        "analyst_confidence": analyst_output.get("confidence"),
        "prompt_version": prompt_version,
        "provider": provider_used,
        "used_heuristic": used_heuristic,
    }

    # ── Step 5: Persist on Lead ───────────────────────────────────────────
    payload = dict(lead.payload or {})
    history = payload.get("docai_insights", [])
    if not isinstance(history, list):
        history = []
    history.append({
        "document_id": document.id,
        "generated_at": insight_payload["generated_at"],
        "summary": summary_text,
        "insights": insights,
        "automations": automations,
        "rag_sources": retrieved_ids,
    })
    payload["docai_insights"] = history[-10:]
    lead.payload = payload
    lead.save(update_fields=["payload", "updated_at"])

    # ── Step 6: Audit + lineage ───────────────────────────────────────────
    lineage = DecisionLineage(
        agent_type=AgentType.ANALYST.value,
        decision="demo_insight_generated",
        prompt_version=prompt_version,
        provider=provider_used,
        inputs_hash=_hash_inputs(analyst_context),
        confidence=float(analyst_output.get("confidence") or 0.0),
        retrieved_context_ids=retrieved_ids,
    )

    write_audit_log(
        action="commercial.docai_demo.generated",
        case_id=lead.case_id,
        actor_type="agent",
        actor_id=AgentType.ANALYST.value,
        trace_id=correlation_id,
        correlation_id=correlation_id,
        details={
            "lead_id": lead.lead_id,
            "document_id": document.id,
            "lineage": lineage.to_dict(),
            "insight_count": len(insights),
            "rag_source_count": len(retrieved_ids),
        },
    )

    # ── Step 7: Emit event ────────────────────────────────────────────────
    ingest_event(
        data={
            "event_id": _new_event_id("evt_demo_insight"),
            "event_type": EventType.DEMO_INSIGHT_GENERATED,
            "source": "commercial.docai_operator",
            "occurred_at": timezone.now(),
            "correlation_id": correlation_id,
            "tenant_id": lead.tenant_id,
            "priority": Priority.MEDIUM,
            "payload": {
                "case_id": lead.lead_id,
                "lead_id": lead.lead_id,
                "document_id": document.id,
                "summary": summary_text,
                "insight_count": len(insights),
            },
            "meta": {"trace_id": correlation_id, "lineage": lineage.to_dict()},
        }
    )

    return insight_payload


# ── Deterministic fallbacks (operational even without a live LLM) ────────────

def _heuristic_insights(*, lead: Lead, document: Document, extracted: dict) -> list[dict]:
    insights: list[dict] = []
    doc_type = (document.document_type or "").lower()

    if doc_type in {"balance", "dre", "report"}:
        receita = extracted.get("receita_liquida") or extracted.get("receita_bruta")
        ebitda = extracted.get("ebitda")
        if receita:
            insights.append({
                "type": "opportunity",
                "title": "Volume financeiro relevante para automação",
                "evidence": f"Receita identificada: {receita}",
                "action": "Posicionar ROI de automação documental sobre o ciclo financeiro.",
                "score": 85,
            })
        if ebitda:
            insights.append({
                "type": "value",
                "title": "EBITDA permite investimento em IA documental",
                "evidence": f"EBITDA: {ebitda}",
                "action": "Sugerir plano Enterprise com SLA dedicado.",
                "score": 80,
            })
    if doc_type in {"contract"}:
        insights.append({
            "type": "pain",
            "title": "Cláusulas contratuais necessitam extração e monitoramento",
            "evidence": f"Documento contratual ({document.title}) processado pelo DocAI.",
            "action": "Demonstrar extração automática de cláusulas críticas e alertas de vencimento.",
            "score": 90,
        })
    if doc_type in {"certificate", "invoice"}:
        insights.append({
            "type": "compliance",
            "title": "Risco de vencimento e conformidade fiscal/regulatória",
            "evidence": f"Documento {doc_type} carregado: {document.title}.",
            "action": "Mostrar painel de alertas de vencimento + automação de certidões.",
            "score": 75,
        })

    if not insights:
        insights.append({
            "type": "opportunity",
            "title": "Caso de uso identificado para automação documental",
            "evidence": f"Documento '{document.title}' analisado pelo DocAI.",
            "action": "Agendar demo personalizada com base no perfil do lead.",
            "score": 50,
        })
    return insights


def _heuristic_summary(*, lead: Lead, document: Document, extracted: dict) -> str:
    company = lead.company_name or lead.contact_email or lead.lead_id
    doc_type_display = document.get_document_type_display() if hasattr(document, 'get_document_type_display') else document.document_type
    key_data = []
    for k in ["receita_bruta", "receita_liquida", "ebitda", "valor_total", "status"]:
        if k in extracted:
            key_data.append(f"{k}: {extracted[k]}")
    data_line = "; ".join(key_data) if key_data else "dados extraídos pelo DocAI"

    return (
        f"Resumo para o vendedor — Lead {company}:\n"
        f"- Documento analisado: {document.title} ({doc_type_display}).\n"
        f"- Dados-chave: {data_line}.\n"
        f"- Score do lead: {lead.score}/100 | Indústria: {lead.industry or 'não informada'}.\n"
        f"- Próximo passo sugerido: agendar demo mostrando como o DocAI "
        f"processa este tipo de documento em segundos, gerando indicadores, "
        f"alertas e insights automaticamente."
    )


def _heuristic_automations(document: Document) -> list[str]:
    """Suggest concrete DocAI automations based on document type."""
    doc_type = (document.document_type or "").lower()
    automations = ["Upload e processamento automático de documentos"]

    if doc_type in {"balance", "dre", "report"}:
        automations.extend([
            "Extração automática de indicadores financeiros (receita, EBITDA, margens)",
            "Comparação entre períodos com detecção de anomalias",
            "Dashboard financeiro em tempo real",
        ])
    if doc_type == "contract":
        automations.extend([
            "Extração de cláusulas críticas (multa, reajuste, rescisão)",
            "Alertas automáticos de vencimento e renovação",
            "Classificação de risco por cláusula",
        ])
    if doc_type in {"certificate", "invoice"}:
        automations.extend([
            "Monitoramento de validade de certidões",
            "Extração de dados fiscais (CNPJ, valores, impostos)",
            "Alertas de vencimento por WhatsApp/email",
        ])
    if doc_type == "other":
        automations.append("Classificação automática de tipo documental via IA")

    return automations
