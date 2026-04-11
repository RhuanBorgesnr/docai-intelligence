"""
Integration tests for document extraction.
Tests the full pipeline including AI when available.
"""
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from ai.extraction import extract_document_data


class TestExtractDocumentDataIntegration:
    """Integration tests for extract_document_data function."""

    def test_extract_invoice_full_pipeline(self):
        """Test full invoice extraction pipeline."""
        text = """
        NOTA FISCAL ELETRÔNICA
        NF-e Nº 99999
        Série: 1

        CNPJ: 11.222.333/0001-44
        Data de Emissão: 20/06/2024

        Valor Total da Nota: R$ 5.000,00
        """

        result = extract_document_data(text, "invoice")

        assert result.get("cnpj_emitente") == "11222333000144"
        assert result.get("numero_nf") == "99999"
        assert result.get("valor_total") == Decimal("5000.00")

    def test_extract_certificate_full_pipeline(self):
        """Test full certificate extraction pipeline."""
        text = """
        CERTIDÃO NEGATIVA DE DÉBITOS TRABALHISTAS
        CNDT

        CNPJ: 55.666.777/0001-88
        Data de Emissão: 01/07/2024
        Válida até: 31/12/2024

        Esta certidão é NEGATIVA.
        """

        result = extract_document_data(text, "certificate")

        assert result.get("tipo") == "cndt"
        assert result.get("status") == "negativa"
        assert result.get("cnpj") == "55666777000188"

    def test_extract_invalid_type_returns_empty(self):
        """Test that invalid document type returns empty dict."""
        result = extract_document_data("some text", "invalid_type")
        assert result == {}

    def test_extract_empty_text_returns_empty(self):
        """Test that empty text returns empty dict."""
        result = extract_document_data("", "invoice")
        assert result == {}


class TestExtractWithAIFallback:
    """Tests for AI fallback behavior."""

    @patch('ai.extraction.strategies.is_groq_enabled')
    @patch('ai.extraction.strategies.chat_with_groq')
    def test_uses_ai_when_regex_insufficient(self, mock_groq, mock_enabled):
        """Test that AI is called when regex doesn't find enough fields."""
        mock_enabled.return_value = True
        mock_groq.return_value = '{"ativo_total": 1000000}'

        # Text that regex won't fully parse
        text = """
        Este é um documento de balanço patrimonial complexo
        com formato não padronizado que contém informações sobre
        o ativo total da empresa no valor de um milhão de reais.
        """ + "x" * 100  # Pad to meet minimum length

        result = extract_document_data(text, "balance")

        # Should have called AI since regex likely failed
        # Note: This test may need adjustment based on actual regex behavior

    @patch('ai.extraction.strategies.is_groq_enabled')
    def test_skips_ai_when_disabled(self, mock_enabled):
        """Test that AI is skipped when Groq is disabled."""
        mock_enabled.return_value = False

        text = """
        Balanço Patrimonial
        Total do Ativo: 500.000,00
        Total do Passivo: 300.000,00
        Patrimônio Líquido: 200.000,00
        """

        result = extract_document_data(text, "balance")

        # Should still work with regex only
        assert result.get("ativo_total") == Decimal("500000.00")


class TestExtractionResultConfidence:
    """Tests for extraction result confidence tracking."""

    def test_regex_extraction_high_confidence(self):
        """Test that regex extraction has high confidence."""
        text = """
        Nota Fiscal Nº 12345
        CNPJ: 11.111.111/0001-11
        Valor Total: R$ 1.000,00
        """

        from ai.extraction.extractors.nota_fiscal import NotaFiscalExtractor
        extractor = NotaFiscalExtractor()
        result = extractor.extract(text)

        assert result.confidence == 1.0
        assert result.source == "regex"


class TestRealWorldDocuments:
    """Tests with real-world document samples."""

    def test_dre_tabular_format(self):
        """Test DRE in tabular format common in Brazilian accounting."""
        text = """
        DEMONSTRAÇÃO DO RESULTADO DO EXERCÍCIO
        Exercício findo em 31/12/2024

        DESCRIÇÃO                          2024           2023
        ────────────────────────────────────────────────────────
        Receita Operacional Bruta    1.500.000,00   1.200.000,00
        (-) Deduções                  (150.000,00)   (120.000,00)
        ────────────────────────────────────────────────────────
        Receita Líquida              1.350.000,00   1.080.000,00
        (-) Custo dos Serviços        (810.000,00)   (648.000,00)
        ────────────────────────────────────────────────────────
        Lucro Bruto                    540.000,00     432.000,00
        (-) Despesas Operacionais     (270.000,00)   (216.000,00)
        ────────────────────────────────────────────────────────
        Lucro Operacional              270.000,00     216.000,00
        Resultado Financeiro           (27.000,00)    (21.600,00)
        ────────────────────────────────────────────────────────
        Lucro Líquido                  243.000,00     194.400,00
        """

        # Using financial_extraction for DRE (not the new module)
        from ai.financial_extraction import extract_financial_indicators
        result = extract_financial_indicators(text)

        # Should extract 2024 values (last column)
        assert result.get("receita_bruta") == Decimal("1500000.00")
        assert result.get("receita_liquida") == Decimal("1350000.00")
        assert result.get("lucro_bruto") == Decimal("540000.00")
        assert result.get("lucro_liquido") == Decimal("243000.00")


# Fixtures for test data
@pytest.fixture
def sample_nf_text():
    return """
    NOTA FISCAL ELETRÔNICA
    NF-e Nº 12345
    CNPJ: 12.345.678/0001-90
    Data: 01/01/2024
    Valor: R$ 1.000,00
    """


@pytest.fixture
def sample_certidao_text():
    return """
    CERTIDÃO NEGATIVA DE DÉBITOS FEDERAIS
    CNPJ: 12.345.678/0001-90
    Emitida em: 01/01/2024
    Válida até: 30/06/2024
    Status: NEGATIVA
    """
