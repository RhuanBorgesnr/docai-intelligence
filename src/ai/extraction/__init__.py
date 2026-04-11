"""
Document Extraction Module

Clean Architecture with Design Patterns:
- Strategy Pattern: Regex vs AI extraction strategies
- Factory Pattern: Create extractors by document type
- Template Method: Common extraction flow with customizable steps

Usage:
    from ai.extraction import extract_document_data, extract_text_from_pdf

    text = extract_text_from_pdf("/path/to/file.pdf")
    data = extract_document_data(text, "invoice")
    print(data["valor_total"])
"""
import logging
from typing import Dict, Any

import fitz

from .factory import DocumentExtractorFactory
from .base import ExtractionResult, BaseDocumentExtractor

logger = logging.getLogger(__name__)

__all__ = [
    "extract_text_from_pdf",
    "extract_document_data",
    "DocumentExtractorFactory",
    "ExtractionResult",
    "BaseDocumentExtractor",
]


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract plain text from a PDF file.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Extracted text concatenated from all pages.
    """
    text_parts = []
    with fitz.open(file_path) as doc:
        for page in doc:
            text_parts.append(page.get_text("text", sort=True))
    return "\n".join(text_parts).strip()


def extract_document_data(text: str, document_type: str) -> Dict[str, Any]:
    """
    Main entry point for document extraction (Facade Pattern).

    Args:
        text: Document text content.
        document_type: One of 'balance', 'invoice', 'certificate', 'report'.

    Returns:
        Dict with extracted data, or empty dict if extraction failed.

    Example:
        >>> data = extract_document_data(pdf_text, "invoice")
        >>> print(data["cnpj_emitente"])
        '12345678000190'
    """
    try:
        extractor = DocumentExtractorFactory.create(document_type)
        result = extractor.extract(text)

        if result.success:
            logger.info(
                "Extracted %d fields from %s using %s (confidence: %.0f%%)",
                len(result.data), document_type, result.source, result.confidence * 100
            )
            return result.data
        else:
            logger.warning("Extraction failed for %s: %s", document_type, result.errors)
            return {}

    except ValueError as e:
        logger.error("Invalid document type: %s", e)
        return {}
    except Exception as e:
        logger.exception("Extraction error for %s: %s", document_type, e)
        return {"error": str(e)}
