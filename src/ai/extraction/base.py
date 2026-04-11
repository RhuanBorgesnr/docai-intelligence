"""
Value objects and base classes for document extraction.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List
from enum import Enum


@dataclass
class ExtractedValue:
    """Value object representing an extracted piece of data."""
    key: str
    value: Any
    confidence: float = 1.0
    source: str = "regex"


@dataclass
class ExtractionResult:
    """Result of document extraction."""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    source: str = "regex"
    confidence: float = 1.0


class DocumentTypeEnum(Enum):
    """Supported document types for extraction."""
    BALANCE = "balance"
    INVOICE = "invoice"
    CERTIFICATE = "certificate"
    REPORT = "report"


class ExtractionStrategy(ABC):
    """Abstract base class for extraction strategies (Strategy Pattern)."""

    @abstractmethod
    def extract(self, text: str, keywords: Dict[str, List[str]]) -> Dict[str, Any]:
        """Extract data from text using specific strategy."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for logging."""
        pass


class BaseDocumentExtractor(ABC):
    """
    Base class for document extractors (Template Method Pattern).

    Defines the skeleton of extraction algorithm,
    letting subclasses override specific steps.
    """

    def __init__(self):
        from .strategies import RegexExtractionStrategy, AIExtractionStrategy
        self.strategies: List[ExtractionStrategy] = [
            RegexExtractionStrategy(),
            AIExtractionStrategy(),
        ]

    def extract(self, text: str) -> ExtractionResult:
        """Template method for document extraction."""
        import logging
        logger = logging.getLogger(__name__)

        # Validate
        if not self._validate_input(text):
            return ExtractionResult(success=False, errors=["Invalid or empty text"])

        # Get keywords
        keywords = self._get_keywords()

        # Try strategies in order
        data = {}
        source = "unknown"

        for strategy in self.strategies:
            extracted = strategy.extract(text, keywords)

            if extracted:
                data.update(extracted)
                source = strategy.name

                if strategy.name == "regex" and self._has_sufficient_data(data):
                    break

        # Extract additional patterns
        additional = self._extract_patterns(text)
        data.update(additional)

        # Post-process
        data = self._post_process(data)

        return ExtractionResult(
            success=bool(data),
            data=data,
            source=source,
            confidence=1.0 if source == "regex" else 0.7
        )

    def _validate_input(self, text: str) -> bool:
        return bool(text and len(text.strip()) >= 50)

    def _has_sufficient_data(self, data: Dict) -> bool:
        return len(data) >= self._get_minimum_fields()

    @abstractmethod
    def _get_keywords(self) -> Dict[str, List[str]]:
        pass

    @abstractmethod
    def _get_minimum_fields(self) -> int:
        pass

    def _extract_patterns(self, text: str) -> Dict[str, Any]:
        return {}

    def _post_process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return data
