"""
Relatório (Report) extractor.
"""
import re
from decimal import Decimal
from typing import Dict, Any, List

from ..base import BaseDocumentExtractor
from ..utils import ValueParser


class RelatorioExtractor(BaseDocumentExtractor):
    """Extractor for general reports."""

    METRICS_KEYWORDS = {
        "faturamento": ["faturamento", "receita", "vendas"],
        "crescimento": ["crescimento", "aumento", "variacao"],
        "reducao": ["reducao", "queda", "diminuicao"],
        "meta": ["meta", "objetivo", "target"],
        "resultado": ["resultado", "lucro", "prejuizo"],
        "margem": ["margem", "rentabilidade"],
        "roi": ["roi", "retorno sobre investimento"],
        "ticket_medio": ["ticket medio", "valor medio"],
    }

    def _get_keywords(self) -> Dict[str, List[str]]:
        return self.METRICS_KEYWORDS

    def _get_minimum_fields(self) -> int:
        return 0

    def _extract_patterns(self, text: str) -> Dict[str, Any]:
        """Extract dates, values, and percentages from report."""
        result = {
            "datas_encontradas": [],
            "valores_encontrados": [],
            "percentuais_encontrados": [],
        }

        # Dates
        dates = re.findall(r'\d{2}[/\-\.]\d{2}[/\-\.]\d{4}', text)
        result["datas_encontradas"] = list(set(dates))[:10]

        # Monetary values
        values = re.findall(r'R\$\s*[\d.,]+|\d+(?:[.,]\d{3})*(?:[.,]\d{2})?', text)
        parsed_values = []
        for v in values:
            parsed = ValueParser.to_decimal(v)
            if parsed and parsed > 100:
                parsed_values.append(str(parsed))
        result["valores_encontrados"] = list(set(parsed_values))[:20]

        # Percentages
        percentages = re.findall(r'[\d.,]+\s*%', text)
        result["percentuais_encontrados"] = list(set(percentages))[:10]

        # Stats
        result["total_caracteres"] = len(text)
        result["total_palavras"] = len(text.split())

        return result

    def _post_process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Move metrics to nested dict."""
        metricas = {}
        to_remove = []

        for key, value in data.items():
            if key in self.METRICS_KEYWORDS and isinstance(value, (Decimal, int, float)):
                metricas[key] = str(value)
                to_remove.append(key)

        for key in to_remove:
            del data[key]

        if metricas:
            data["metricas"] = metricas

        return data
