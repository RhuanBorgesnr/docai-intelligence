"""
Embedding service for semantic search and RAG.

Supports embedding of:
- Document chunks (existing)
- Case context (title + events + metadata)
- Approval decisions (for precedent search)
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model


def generate_embedding(text: str) -> list[float]:
    """Generate a 384-dimensional embedding for *text*."""
    model = get_model()
    return model.encode(text).tolist()


def content_hash(text: str) -> str:
    """Deterministic hash for deduplication / cache lookups."""
    return hashlib.sha256(text.encode()).hexdigest()[:64]


# ── Case context embedding ─────────────────────────────────────────────────────

def build_case_text(
    title: str,
    state: str = "",
    events: Optional[list[dict]] = None,
    metadata: Optional[dict] = None,
) -> str:
    """
    Build a textual representation of a Case suitable for embedding.

    Keeps it concise so the 384-dim model captures the semantic essence.
    """
    parts = [title]
    if state:
        parts.append(f"Estado: {state}")
    if metadata:
        for k, v in metadata.items():
            parts.append(f"{k}: {v}")
    if events:
        for evt in events[:10]:  # cap to avoid overlong text
            evt_text = f"{evt.get('event_type', '')} — {evt.get('source', '')}"
            payload_summary = str(evt.get("payload", ""))[:200]
            if payload_summary:
                evt_text += f": {payload_summary}"
            parts.append(evt_text)
    return "\n".join(parts)


def embed_case_context(
    title: str,
    state: str = "",
    events: Optional[list[dict]] = None,
    metadata: Optional[dict] = None,
) -> tuple[list[float], str]:
    """
    Return ``(embedding, text_hash)`` for a Case context.
    """
    text = build_case_text(title, state, events, metadata)
    return generate_embedding(text), content_hash(text)


# ── Approval decision embedding ────────────────────────────────────────────────

def build_approval_text(
    approval_type: str,
    summary: str = "",
    decision: str = "",
    payload: Optional[dict] = None,
) -> str:
    parts = [f"Tipo: {approval_type}"]
    if summary:
        parts.append(summary)
    if decision:
        parts.append(f"Decisão: {decision}")
    if payload:
        parts.append(str(payload)[:300])
    return "\n".join(parts)


def embed_approval(
    approval_type: str,
    summary: str = "",
    decision: str = "",
    payload: Optional[dict] = None,
) -> tuple[list[float], str]:
    text = build_approval_text(approval_type, summary, decision, payload)
    return generate_embedding(text), content_hash(text)