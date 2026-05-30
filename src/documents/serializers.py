"""
Document API serializers.
"""
from rest_framework import serializers

from .models import Document, DocumentChunk, FinancialIndicator, ContractClause


class DocumentChunkSerializer(serializers.ModelSerializer):
    """Serializer for DocumentChunk model."""

    class Meta:
        model = DocumentChunk
        fields = ("id", "content", "chunk_index", "token_count", "created_at")


class FinancialIndicatorSerializer(serializers.ModelSerializer):
    """Serializer for FinancialIndicator model."""
    indicator_type_display = serializers.CharField(
        source='get_indicator_type_display', read_only=True
    )

    class Meta:
        model = FinancialIndicator
        fields = ("id", "indicator_type", "indicator_type_display", "value", "period", "extracted_at")


class ContractClauseSerializer(serializers.ModelSerializer):
    """Serializer for ContractClause model."""
    clause_type_display = serializers.CharField(
        source='get_clause_type_display', read_only=True
    )
    risk_level_display = serializers.CharField(
        source='get_risk_level_display', read_only=True
    )

    class Meta:
        model = ContractClause
        fields = (
            "id", "clause_type", "clause_type_display", "title", "content",
            "summary", "risk_level", "risk_level_display", "extracted_value", "extracted_at"
        )


class DocumentListSerializer(serializers.ModelSerializer):
    """Serializer for Document list/detail (without chunks)."""
    days_until_expiration = serializers.SerializerMethodField()
    document_type_display = serializers.CharField(
        source='get_document_type_display', read_only=True
    )

    class Meta:
        model = Document
        fields = (
            "id",
            "title",
            "file",
            "extracted_text",
            "processing_status",
            "document_type",
            "document_type_display",
            "reference_date",
            "expiration_date",
            "days_until_expiration",
            "extracted_metadata",
            "total_tokens",
            "created_at",
        )

    def get_days_until_expiration(self, obj):
        if not obj.expiration_date:
            return None
        from datetime import date
        delta = (obj.expiration_date - date.today()).days
        return delta


class DocumentDetailSerializer(DocumentListSerializer):
    """Serializer for Document detail including chunks."""

    chunks = DocumentChunkSerializer(many=True, read_only=True)
    financial_indicators = FinancialIndicatorSerializer(many=True, read_only=True)
    has_financial_data = serializers.SerializerMethodField()

    class Meta(DocumentListSerializer.Meta):
        fields = DocumentListSerializer.Meta.fields + ("chunks", "financial_indicators", "has_financial_data")

    def get_has_financial_data(self, obj):
        return obj.financial_indicators.exists()


class DocumentUploadSerializer(serializers.ModelSerializer):
    """Serializer for document upload with file validation."""

    ALLOWED_EXTENSIONS = {
        '.pdf', '.png', '.jpg', '.jpeg', '.xlsx', '.xls',
        '.docx', '.doc', '.txt', '.csv',
    }
    ALLOWED_MIME_TYPES = {
        'application/pdf',
        'image/png', 'image/jpeg',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/msword',
        'text/plain', 'text/csv',
    }
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

    class Meta:
        model = Document
        fields = ("file", "title", "document_type", "reference_date", "expiration_date")

    def validate_file(self, file):
        import os

        # Check file size
        if file.size > self.MAX_FILE_SIZE:
            raise serializers.ValidationError(
                f"Arquivo muito grande ({file.size // (1024*1024)}MB). Máximo: 10MB."
            )

        # Check extension
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"Extensão '{ext}' não permitida. "
                f"Aceitas: {', '.join(sorted(self.ALLOWED_EXTENSIONS))}"
            )

        # Check MIME type
        if file.content_type not in self.ALLOWED_MIME_TYPES:
            raise serializers.ValidationError(
                f"Tipo de arquivo '{file.content_type}' não permitido."
            )

        return file
