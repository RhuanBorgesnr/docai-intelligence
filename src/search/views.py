"""
Semantic search API views.
"""
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from ai.embeddings import generate_embedding
from documents.models import DocumentChunk
from pgvector.django import CosineDistance


class SemanticSearchView(APIView):
    """Search documents by semantic similarity."""

    def post(self, request: Request) -> Response:
        """Search chunks by query text using vector similarity."""
        query = request.data.get("query")
        if not query or not isinstance(query, str):
            return Response(
                {"error": "query field is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        limit = int(request.data.get("limit", 10))
        limit = min(max(1, limit), 50)

        query_embedding = generate_embedding(query.strip())
        chunks = (
            DocumentChunk.objects.filter(
                document__processing_status="completed",
                # posteriomente para virar um SaaS tem um (document__organization=request.user.organization,)
            )
            .annotate(distance=CosineDistance("embedding", query_embedding))
            .order_by("distance")[:limit]
            .select_related("document")
        )

        results = [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
                "similarity": 1 - float(chunk.distance),
            }
            for chunk in chunks
        ]

        return Response({"results": results})
