"""
Certidão (Certificate) extractor.
"""
import re
from datetime import date
from typing import Dict, Any, List

from ..base import BaseDocumentExtractor
from ..utils import TextNormalizer, ValueParser


class CertidaoExtractor(BaseDocumentExtractor):
    """Extractor for Certidão (Certificate)."""

    CERTIDAO_TYPES = [
        ("cnd_federal", ["certidao negativa de debitos federais", "cnd federal", "receita federal"]),
        ("cnd_estadual", ["certidao negativa estadual", "fazenda estadual", "sefaz"]),
        ("cnd_municipal", ["certidao negativa municipal", "fazenda municipal", "iss"]),
        ("cndt", ["certidao negativa de debitos trabalhistas", "cndt", "tst"]),
        ("fgts", ["regularidade do fgts", "crf", "caixa economica"]),
        ("falencia", ["certidao negativa de falencia", "falencia e concordata"]),
    ]

    def _get_keywords(self) -> Dict[str, List[str]]:
        return {}

    def _get_minimum_fields(self) -> int:
        return 1

    def _extract_patterns(self, text: str) -> Dict[str, Any]:
        """Extract certificate-specific patterns."""
        result = {}
        text_norm = TextNormalizer.normalize(text)

        # Certificate Type
        for cert_type, keywords in self.CERTIDAO_TYPES:
            for keyword in keywords:
                if TextNormalizer.normalize(keyword) in text_norm:
                    result["tipo"] = cert_type
                    result["tipo_display"] = keyword.title()
                    break
            if "tipo" in result:
                break

        # Status
        if "negativa" in text_norm:
            if "positiva com efeito" in text_norm or "efeito de negativa" in text_norm:
                result["status"] = "positiva_efeito_negativa"
                result["status_display"] = "Positiva com Efeito de Negativa"
            else:
                result["status"] = "negativa"
                result["status_display"] = "Negativa (Regular)"
        elif "positiva" in text_norm:
            result["status"] = "positiva"
            result["status_display"] = "Positiva (Irregular)"

        # CNPJ
        cnpj_match = re.search(r'\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2}', text)
        if cnpj_match:
            result["cnpj"] = re.sub(r'[^\d]', '', cnpj_match.group())

        # Data de Emissão
        emissao_patterns = [
            r'emitida?\s*(?:em)?[:\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',
            r'data\s*(?:de?\s*)?emiss[aã]o[:\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',
        ]
        for pattern in emissao_patterns:
            match = re.search(pattern, text_norm)
            if match:
                result["data_emissao"] = ValueParser.to_date(match.group(1))
                break

        # Data de Validade
        validade_patterns = [
            r'v[aá]lid[ao]?\s*(?:at[eé])?\s*[:\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',
            r'validade[:\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',
            r'vencimento[:\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',
        ]
        for pattern in validade_patterns:
            match = re.search(pattern, text_norm)
            if match:
                result["data_validade"] = ValueParser.to_date(match.group(1))
                break

        # Verification Code
        codigo_patterns = [
            r'c[oó]digo\s*(?:de\s*)?verifica[cç][aã]o[:\s]*([A-Za-z0-9]+)',
            r'c[oó]digo\s*(?:de\s*)?autentica[cç][aã]o[:\s]*([A-Za-z0-9]+)',
        ]
        for pattern in codigo_patterns:
            match = re.search(pattern, text_norm)
            if match:
                result["codigo_verificacao"] = match.group(1).upper()
                break

        # Check if expired
        if result.get("data_validade"):
            result["expirado"] = result["data_validade"] < date.today()

        return result
