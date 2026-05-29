"""
RAG (Retrieval-Augmented Generation) pipeline.

Supports:
- Document-based Q&A (existing)
- Agent context injection via ``build_agent_rag_context``
- Case-aware answering via ``generate_case_answer``
"""

from __future__ import annotations

import logging
from typing import Optional

from ai.llm import generate_text
from documents.models import Document
from search.services import semantic_search

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARACTERS = 4000  # limite do contexto para o prompt


def _build_context(document_ids, question: str) -> str:
    """Build RAG context from semantic search results. Used by both regular and streaming chat."""
    chunks = semantic_search(document_ids=document_ids, query=question, limit=5)
    chunks = [c for c in chunks if c.get("content") and c.get("content").strip()]
    context = "\n\n".join([c["content"] for c in chunks])
    if len(context) > MAX_CONTEXT_CHARACTERS:
        context = context[:MAX_CONTEXT_CHARACTERS]
    return context


def build_prompt(context: str, question: str) -> str:
    return f"""
Você é um assistente especializado em analisar documentos.
Use exclusivamente o contexto abaixo para responder.
Se a informação não estiver no contexto, diga que não encontrou.

CONTEXTO:
{context}

PERGUNTA:
{question}

RESPOSTA:
"""


def _is_metadata_question(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ("título", "titulo", "title")):
        return "title"
    if any(k in q for k in ("autor", "author")):
        return "author"
    if any(k in q for k in ("data", "date", "quando")):
        return "date"
    return ""


def generate_answer(document_ids, question: str):
    """
    RAG flow with Groq (Llama 3 70B) as primary LLM:
    - Detect metadata questions (answer from DB)
    - Run semantic search
    - If no relevant chunks or context too small -> return explicit 'not found'
    - Try Groq first (fast, powerful), fallback to local Flan-T5
    """
    # Handle simple metadata queries without calling the LLM
    meta = _is_metadata_question(question)
    if meta and document_ids:
        # try to answer directly from the Document model when asking about a single document
        try:
            doc = Document.objects.filter(id__in=document_ids).first()
            if doc:
                if meta == "title":
                    return {"answer": doc.title or (doc.file.name.split('/')[-1] if doc.file else ""), "documents_used": [doc.id]}
                if meta == "date":
                    return {"answer": str(doc.created_at), "documents_used": [doc.id]}
                if meta == "author":
                    # no author field by default; return not found
                    return {"answer": "Nenhuma informação de autor encontrada no documento.", "documents_used": [doc.id]}
        except Exception:
            pass

    chunks = semantic_search(document_ids=document_ids, query=question, limit=5)


    chunks = [c for c in chunks if c.get("content") and c.get("content").strip()]

    context = "\n\n".join([c["content"] for c in chunks])

    if not chunks or len(context.strip()) < 50:
        return {
            "answer": "Não foram encontrados trechos relevantes no(s) documento(s) para responder a pergunta.",
            "documents_used": []
        }

    # Controle do tamanho do prompt
    if len(context) > MAX_CONTEXT_CHARACTERS:
        context = context[:MAX_CONTEXT_CHARACTERS]

    documents_used = list(dict.fromkeys([c["document_id"] for c in chunks]))

    # 1. Try Groq first (fast and powerful)
    try:
        from ai.groq_client import chat_with_groq, is_groq_enabled

        if is_groq_enabled():
            logger.info("Using Groq for chat...")
            answer = chat_with_groq(context, question)
            if answer:
                return {
                    "answer": answer,
                    "documents_used": documents_used
                }
    except Exception as e:
        logger.warning("Groq chat failed: %s", e)

    # 2. Fallback to local Flan-T5
    logger.info("Falling back to local LLM...")
    prompt = build_prompt(context=context, question=question)
    answer = generate_text(prompt)

    return {
        "answer": answer,
        "documents_used": documents_used
    }


# ── Agent RAG context builder ────────────────────────────────────────────────

def build_agent_rag_context(
    case_id: Optional[int] = None,
    query: Optional[str] = None,
    document_ids: Optional[list[int]] = None,
    max_chars: int = MAX_CONTEXT_CHARACTERS,
) -> dict:
    """
    Build a RAG context payload suitable for injection into an agent prompt.

    Combines:
    - Case context (events, approvals, metadata) via ``get_case_context``
    - Document chunks matching *query* via ``semantic_search``

    Returns ``{"rag_context": str, "sources": list[str], "chunk_count": int}``.
    """
    from search.services import get_case_context

    parts: list[str] = []
    sources: list[str] = []
    chunk_count = 0

    # 1. Case-level context
    if case_id:
        case_ctx = get_case_context(case_id, max_chars=max_chars // 2)
        if case_ctx["text"]:
            parts.append(case_ctx["text"])
            sources.extend(case_ctx["sources"])

    # 2. Document chunks
    search_query = query or ""
    if search_query:
        chunks = semantic_search(
            document_ids=document_ids,
            query=search_query,
            limit=5,
        )
        chunk_count = len(chunks)
        if chunks:
            parts.append("\n--- Trechos de documentos relevantes ---")
            for ch in chunks:
                parts.append(ch["content"][:400])
            sources.append("document_chunks")

    rag_text = "\n\n".join(parts)
    if len(rag_text) > max_chars:
        rag_text = rag_text[:max_chars]

    return {
        "rag_context": rag_text,
        "sources": sources,
        "chunk_count": chunk_count,
    }


def generate_case_answer(case_id: int, question: str) -> dict:
    """
    Answer a question about a specific Case using full RAG context.

    Combines case metadata, events, approvals, and related document chunks
    into a single prompt, then calls the LLM.
    """
    rag = build_agent_rag_context(case_id=case_id, query=question)

    context = rag["rag_context"]
    if not context or len(context.strip()) < 50:
        return {
            "answer": "Não há contexto suficiente para responder a essa pergunta.",
            "sources": [],
            "rag_context_used": False,
        }

    # Try Groq first
    try:
        from ai.groq_client import chat_with_groq, is_groq_enabled

        if is_groq_enabled():
            answer = chat_with_groq(context, question)
            if answer:
                return {
                    "answer": answer,
                    "sources": rag["sources"],
                    "rag_context_used": True,
                }
    except Exception as e:
        logger.warning("Groq failed for case answer: %s", e)

    # Fallback to local LLM
    prompt = build_prompt(context=context, question=question)
    answer = generate_text(prompt)

    return {
        "answer": answer,
        "sources": rag["sources"],
        "rag_context_used": True,
    }