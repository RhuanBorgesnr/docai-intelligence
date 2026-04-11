"""
Balanço Patrimonial (Balance Sheet) extractor.
"""
from decimal import Decimal
from typing import Dict, Any, List

from ..base import BaseDocumentExtractor


class BalancoExtractor(BaseDocumentExtractor):
    """Extractor for Balanço Patrimonial (Balance Sheet)."""

    KEYWORDS = {
        # Ativo
        "ativo_circulante": ["ativo circulante total", "total do ativo circulante", "ativo circulante"],
        "caixa_equivalentes": ["caixa e equivalentes", "disponibilidades", "caixa e bancos", "caixa"],
        "contas_receber": ["contas a receber", "clientes", "duplicatas a receber"],
        "estoques": ["estoques", "mercadorias", "produtos acabados"],
        "ativo_nao_circulante": ["ativo nao circulante", "ativo permanente"],
        "imobilizado": ["ativo imobilizado", "imobilizado"],
        "ativo_total": ["total do ativo", "ativo total"],
        # Passivo
        "passivo_circulante": ["passivo circulante total", "total do passivo circulante", "passivo circulante"],
        "fornecedores": ["fornecedores", "contas a pagar"],
        "emprestimos_cp": ["emprestimos e financiamentos", "emprestimos curto prazo"],
        "passivo_nao_circulante": ["passivo nao circulante", "exigivel a longo prazo"],
        "passivo_total": ["total do passivo", "passivo total"],
        # Patrimônio
        "capital_social": ["capital social realizado", "capital social"],
        "patrimonio_liquido": ["total do patrimonio liquido", "patrimonio liquido"],
    }

    def _get_keywords(self) -> Dict[str, List[str]]:
        return self.KEYWORDS

    def _get_minimum_fields(self) -> int:
        return 3

    def _post_process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate financial ratios."""
        ativo_circ = data.get("ativo_circulante")
        passivo_circ = data.get("passivo_circulante")
        ativo_total = data.get("ativo_total")
        passivo_total = data.get("passivo_total")
        caixa = data.get("caixa_equivalentes")
        estoques = data.get("estoques")

        # Liquidez Corrente
        if ativo_circ and passivo_circ and passivo_circ > 0:
            data["liquidez_corrente"] = (ativo_circ / passivo_circ).quantize(Decimal("0.01"))

        # Liquidez Seca
        if ativo_circ and estoques and passivo_circ and passivo_circ > 0:
            data["liquidez_seca"] = ((ativo_circ - estoques) / passivo_circ).quantize(Decimal("0.01"))

        # Liquidez Imediata
        if caixa and passivo_circ and passivo_circ > 0:
            data["liquidez_imediata"] = (caixa / passivo_circ).quantize(Decimal("0.01"))

        # Endividamento Geral
        if passivo_total and ativo_total and ativo_total > 0:
            data["endividamento_geral"] = ((passivo_total / ativo_total) * 100).quantize(Decimal("0.01"))

        return data
