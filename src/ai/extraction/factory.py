"""
Factory for creating document extractors (Factory Pattern).
"""
from typing import Dict, Type, List

from .base import BaseDocumentExtractor
from .extractors import (
    BalancoExtractor,
    NotaFiscalExtractor,
    CertidaoExtractor,
    RelatorioExtractor,
)


class DocumentExtractorFactory:
    """
    Factory for creating document extractors.

    Follows Open/Closed Principle: new extractors can be added
    without modifying existing code via register().

    Usage:
        extractor = DocumentExtractorFactory.create("invoice")
        result = extractor.extract(text)
    """

    _extractors: Dict[str, Type[BaseDocumentExtractor]] = {
        "balance": BalancoExtractor,
        "invoice": NotaFiscalExtractor,
        "certificate": CertidaoExtractor,
        "report": RelatorioExtractor,
    }

    @classmethod
    def create(cls, document_type: str) -> BaseDocumentExtractor:
        """Create an extractor for the given document type."""
        extractor_class = cls._extractors.get(document_type)
        if not extractor_class:
            raise ValueError(f"No extractor for document type: {document_type}")
        return extractor_class()

    @classmethod
    def register(cls, document_type: str, extractor_class: Type[BaseDocumentExtractor]) -> None:
        """Register a new extractor type."""
        cls._extractors[document_type] = extractor_class

    @classmethod
    def get_supported_types(cls) -> List[str]:
        """Get list of supported document types."""
        return list(cls._extractors.keys())
