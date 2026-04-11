"""
Utility classes for text processing and value parsing.
"""
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from typing import Optional, Any


class TextNormalizer:
    """Utility class for text normalization."""

    @staticmethod
    def normalize(text: str) -> str:
        """Remove accents and convert to lowercase."""
        normalized = unicodedata.normalize('NFD', text)
        without_accents = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        return without_accents.lower()

    @staticmethod
    def clean_number(value: str) -> str:
        """Clean a number string for parsing."""
        cleaned = re.sub(r'[R$\s]', '', value.strip())
        if ',' in cleaned and '.' in cleaned:
            cleaned = cleaned.replace('.', '').replace(',', '.')
        elif ',' in cleaned:
            cleaned = cleaned.replace(',', '.')
        return re.sub(r'[^\d.\-]', '', cleaned)


class ValueParser:
    """Parser for different value types."""

    @staticmethod
    def to_decimal(value: Any) -> Optional[Decimal]:
        """Parse value to Decimal."""
        if value is None:
            return None

        if isinstance(value, (int, float)):
            try:
                return Decimal(str(value))
            except InvalidOperation:
                return None

        if isinstance(value, str):
            cleaned = TextNormalizer.clean_number(value)
            try:
                return Decimal(cleaned) if cleaned else None
            except InvalidOperation:
                return None

        return None

    @staticmethod
    def to_date(text: str) -> Optional[date]:
        """Parse Brazilian date formats."""
        patterns = [
            (r'(\d{2})/(\d{2})/(\d{4})', '%d/%m/%Y'),
            (r'(\d{2})-(\d{2})-(\d{4})', '%d-%m-%Y'),
            (r'(\d{2})\.(\d{2})\.(\d{4})', '%d.%m.%Y'),
            (r'(\d{4})-(\d{2})-(\d{2})', '%Y-%m-%d'),
        ]
        for pattern, fmt in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return datetime.strptime(match.group(), fmt).date()
                except ValueError:
                    continue
        return None
