from django.conf import settings
from pgvector.django import CosineDistance
from documents.models import DocumentChunk
from ai.embeddings import generate_embedding


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