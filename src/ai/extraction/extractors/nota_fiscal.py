"""
Nota Fiscal (Invoice) extractor.
"""
import re
from typing import Dict, Any, List

from ..base import BaseDocumentExtractor
from ..utils import TextNormalizer, ValueParser


class NotaFiscalExtractor(BaseDocumentExtractor):
    """Extractor for Nota Fiscal (Invoice)."""

    KEYWORDS = {
        "valor_total": ["valor total da nota", "valor total", "total da nota", "total nf"],
        "valor_produtos": ["valor total dos produtos", "valor dos produtos", "total produtos"],
        "valor_icms": ["valor do icms", "valor icms"],
        "base_icms": ["base de calculo do icms", "base icms", "bc icms"],
        "valor_ipi": ["valor do ipi", "valor ipi"],
        "valor_frete": ["valor do frete", "frete"],
        "valor_desconto": ["desconto", "valor desconto"],
    }

    def _get_keywords(self) -> Dict[str, List[str]]:
        return self.KEYWORDS

    def _get_minimum_fields(self) -> int:
        return 1

    def _extract_patterns(self, text: str) -> Dict[str, Any]:
        """Extract NF-specific patterns."""
        result = {}
        text_norm = TextNormalizer.normalize(text)

        # CNPJ
        cnpjs = re.findall(r'\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2}', text)
        if cnpjs:
            cleaned = [re.sub(r'[^\d]', '', c) for c in cnpjs]
            if cleaned:
                result["cnpj_emitente"] = cleaned[0]
            if len(cleaned) >= 2:
                result["cnpj_destinatario"] = cleaned[1]

        # Número da NF
        nf_patterns = [r'n[uú]mero[:\s]*(\d+)', r'nf[:\s-]*(\d+)', r'nota fiscal[:\s]*(\d+)']
        for pattern in nf_patterns:
            match = re.search(pattern, text_norm)
            if match:
                result["numero_nf"] = match.group(1)
                break

        # Chave de Acesso (44 digits)
        chave_match = re.search(r'\d{44}', text)
        if chave_match:
            result["chave_acesso"] = chave_match.group()

        # Data de Emissão
        date_patterns = [
            r'data\s*(?:de\s*)?emiss[aã]o[:\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',
            r'emitida?\s*em[:\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text_norm)
            if match:
                result["data_emissao"] = ValueParser.to_date(match.group(1))
                break

        # Série
        serie_match = re.search(r's[eé]rie[:\s]*(\d+)', text_norm)
        if serie_match:
            result["serie"] = serie_match.group(1)

        return result
