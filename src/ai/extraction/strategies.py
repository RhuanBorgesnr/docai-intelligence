"""
Extraction strategies (Strategy Pattern).
"""
import re
import json
import logging
from typing import Dict, Any, List

from .base import ExtractionStrategy
from .utils import TextNormalizer, ValueParser

logger = logging.getLogger(__name__)


class RegexExtractionStrategy(ExtractionStrategy):
    """Extract data using regex patterns."""

    @property
    def name(self) -> str:
        return "regex"

    def extract(self, text: str, keywords: Dict[str, List[str]]) -> Dict[str, Any]:
        """Extract values by matching keywords and finding adjacent numbers."""
        indicators = {}
        lines = text.split('\n')
        matched_lines = set()

        for indicator_type, keyword_list in keywords.items():
            if indicator_type in indicators:
                continue

            for keyword in keyword_list:
                keyword_norm = TextNormalizer.normalize(keyword)

                for i, line in enumerate(lines):
                    if i in matched_lines:
                        continue

                    line_norm = TextNormalizer.normalize(line)

                    if keyword_norm in line_norm:
                        numbers = re.findall(r'\(?([\d]+(?:[.,][\d]+)*)\)?', line)

                        if numbers:
                            last_number = numbers[-1]
                            is_negative = f"({last_number})" in line

                            value = ValueParser.to_decimal(last_number)
                            if value is not None and value != 0:
                                if is_negative:
                                    value = -abs(value)
                                indicators[indicator_type] = value
                                matched_lines.add(i)
                                break

                if indicator_type in indicators:
                    break

        return indicators


class AIExtractionStrategy(ExtractionStrategy):
    """Extract data using AI (Groq/Llama)."""

    @property
    def name(self) -> str:
        return "ai"

    def extract(self, text: str, keywords: Dict[str, List[str]]) -> Dict[str, Any]:
        """Use AI to extract data from complex documents."""
        try:
            from ai.groq_client import is_groq_enabled, chat_with_groq

            if not is_groq_enabled():
                logger.debug("Groq not enabled, skipping AI extraction")
                return {}

            fields = list(keywords.keys())
            if not fields:
                return {}

            prompt = self._build_prompt(fields)
            response = chat_with_groq(text[:4000], prompt)

            if response:
                return self._parse_response(response, fields)

        except Exception as e:
            logger.warning("AI extraction failed: %s", e)

        return {}

    def _build_prompt(self, fields: List[str]) -> str:
        """Build prompt for AI extraction."""
        fields_str = ", ".join(fields)
        return f"""Extraia os seguintes campos do documento: {fields_str}

Retorne APENAS um JSON válido com os valores encontrados.
Use null para valores não encontrados.
Valores numéricos sem R$, sem pontos de milhar.
Datas no formato YYYY-MM-DD.

JSON:"""

    def _parse_response(self, response: str, fields: List[str]) -> Dict[str, Any]:
        """Parse AI response to extract JSON data."""
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return {k: v for k, v in data.items() if k in fields and v is not None}
            except json.JSONDecodeError:
                pass
        return {}
