"""
DEPRECATED: This module has been refactored.

Import from ai.extraction instead:
    from ai.extraction import extract_document_data

This file is kept for backwards compatibility.
"""
from ai.extraction import extract_document_data, DocumentExtractorFactory

__all__ = ["extract_document_data", "DocumentExtractorFactory"]
