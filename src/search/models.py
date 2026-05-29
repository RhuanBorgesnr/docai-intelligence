"""
Search models for semantic memory.

CaseEmbedding stores a vector representation of a Case's context
(title, state, events, metadata) for similarity search across cases
and approval precedent lookup.
"""

from django.db import models
from pgvector.django import VectorField


class CaseEmbedding(models.Model):
    """384-dim embedding of a Case's aggregated context."""

    case = models.OneToOneField(
        "orchestrator.Case",
        on_delete=models.CASCADE,
        related_name="embedding_record",
    )
    embedding = VectorField(dimensions=384)
    content_hash = models.CharField(max_length=64, db_index=True)
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["content_hash"]),
        ]

    def __str__(self) -> str:
        return f"CaseEmbedding case={self.case_id}"
