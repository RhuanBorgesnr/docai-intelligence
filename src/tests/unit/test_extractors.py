"""
Unit tests for document extractors.
"""
import pytest
from decimal import Decimal
from datetime import date

from ai.extraction.factory import DocumentExtractorFactory
from ai.extraction.extractors.balanco import BalancoExtractor
from ai.extraction.extractors.nota_fiscal import NotaFiscalExtractor
from ai.extraction.extractors.certidao import CertidaoExtractor
from ai.extraction.extractors.relatorio import RelatorioExtractor


class TestDocumentExtractorFactory:
    """Tests for DocumentExtractorFactory."""

    def test_create_balance_extractor(self):
        extractor = DocumentExtractorFactory.create("balance")
        assert isinstance(extractor, BalancoExtractor)

    def test_create_invoice_extractor(self):
        extractor = DocumentExtractorFactory.create("invoice")
        assert isinstance(extractor, NotaFiscalExtractor)

    def test_create_certificate_extractor(self):
        extractor = DocumentExtractorFactory.create("certificate")
        assert isinstance(extractor, CertidaoExtractor)

    def test_create_report_extractor(self):
        extractor = DocumentExtractorFactory.create("report")
        assert isinstance(extractor, RelatorioExtractor)

    def test_create_invalid_type_raises(self):
        with pytest.raises(ValueError):
            DocumentExtractorFactory.create("invalid_type")

    def test_get_supported_types(self):
        types = DocumentExtractorFactory.get_supported_types()
        assert "balance" in types
        assert "invoice" in types
        assert "certificate" in types
        assert "report" in types


class TestBalancoExtractor:
    """Tests for Balance Sheet extractor."""

    SAMPLE_BALANCO = """
    BALANÇO PATRIMONIAL
    Em 31/12/2024

    ATIVO
    Ativo Circulante                    500.000,00
      Caixa e Equivalentes              100.000,00
      Contas a Receber                  250.000,00
      Estoques                          150.000,00
    Ativo Não Circulante                300.000,00
      Imobilizado                       300.000,00
    Total do Ativo                      800.000,00

    PASSIVO
    Passivo Circulante                  200.000,00
      Fornecedores                      120.000,00
      Empréstimos                        80.000,00
    Passivo Não Circulante              100.000,00
    Total do Passivo                    300.000,00

    PATRIMÔNIO LÍQUIDO
    Capital Social                      400.000,00
    Lucros Acumulados                   100.000,00
    Total do Patrimônio Líquido         500.000,00
    """

    def test_extract_ativo_total(self):
        extractor = BalancoExtractor()
        result = extractor.extract(self.SAMPLE_BALANCO)
        assert result.success
        assert result.data.get("ativo_total") == Decimal("800000.00")

    def test_extract_ativo_circulante(self):
        extractor = BalancoExtractor()
        result = extractor.extract(self.SAMPLE_BALANCO)
        assert result.data.get("ativo_circulante") == Decimal("500000.00")

    def test_extract_patrimonio_liquido(self):
        extractor = BalancoExtractor()
        result = extractor.extract(self.SAMPLE_BALANCO)
        assert result.data.get("patrimonio_liquido") == Decimal("500000.00")

    def test_calculates_liquidez_corrente(self):
        extractor = BalancoExtractor()
        result = extractor.extract(self.SAMPLE_BALANCO)
        # Liquidez Corrente = Ativo Circ / Passivo Circ = 500000 / 200000 = 2.5
        assert result.data.get("liquidez_corrente") == Decimal("2.50")

    def test_empty_text_fails(self):
        extractor = BalancoExtractor()
        result = extractor.extract("")
        assert not result.success


class TestNotaFiscalExtractor:
    """Tests for Invoice extractor."""

    SAMPLE_NF = """
    NOTA FISCAL ELETRÔNICA
    NF-e Nº 12345
    Série: 1

    CNPJ do Emitente: 12.345.678/0001-90
    CNPJ do Destinatário: 98.765.432/0001-10

    Data de Emissão: 15/03/2024

    Chave de Acesso: 35240312345678000190550010000123451234567890

    VALORES
    Valor Total dos Produtos: R$ 10.000,00
    Valor do ICMS: R$ 1.800,00
    Base de Cálculo do ICMS: R$ 10.000,00
    Valor Total da Nota: R$ 10.500,00
    """

    def test_extract_cnpj_emitente(self):
        extractor = NotaFiscalExtractor()
        result = extractor.extract(self.SAMPLE_NF)
        assert result.success
        assert result.data.get("cnpj_emitente") == "12345678000190"

    def test_extract_numero_nf(self):
        extractor = NotaFiscalExtractor()
        result = extractor.extract(self.SAMPLE_NF)
        assert result.data.get("numero_nf") == "12345"

    def test_extract_chave_acesso(self):
        extractor = NotaFiscalExtractor()
        result = extractor.extract(self.SAMPLE_NF)
        assert result.data.get("chave_acesso") == "35240312345678000190550010000123451234567890"

    def test_extract_valor_total(self):
        extractor = NotaFiscalExtractor()
        result = extractor.extract(self.SAMPLE_NF)
        assert result.data.get("valor_total") == Decimal("10500.00")

    def test_extract_data_emissao(self):
        extractor = NotaFiscalExtractor()
        result = extractor.extract(self.SAMPLE_NF)
        assert result.data.get("data_emissao") == date(2024, 3, 15)


class TestCertidaoExtractor:
    """Tests for Certificate extractor."""

    SAMPLE_CND = """
    CERTIDÃO NEGATIVA DE DÉBITOS
    RELATIVOS AOS TRIBUTOS FEDERAIS

    Certidão emitida em: 01/04/2024
    Válida até: 30/09/2024

    CNPJ: 12.345.678/0001-90

    Certifica-se que não constam débitos relativos aos tributos federais
    e à Dívida Ativa da União.

    Esta certidão é NEGATIVA.

    Código de Verificação: ABC123XYZ
    """

    def test_extract_tipo(self):
        extractor = CertidaoExtractor()
        result = extractor.extract(self.SAMPLE_CND)
        assert result.success
        assert result.data.get("tipo") == "cnd_federal"

    def test_extract_status_negativa(self):
        extractor = CertidaoExtractor()
        result = extractor.extract(self.SAMPLE_CND)
        assert result.data.get("status") == "negativa"

    def test_extract_cnpj(self):
        extractor = CertidaoExtractor()
        result = extractor.extract(self.SAMPLE_CND)
        assert result.data.get("cnpj") == "12345678000190"

    def test_extract_data_validade(self):
        extractor = CertidaoExtractor()
        result = extractor.extract(self.SAMPLE_CND)
        assert result.data.get("data_validade") == date(2024, 9, 30)

    def test_extract_codigo_verificacao(self):
        extractor = CertidaoExtractor()
        result = extractor.extract(self.SAMPLE_CND)
        assert result.data.get("codigo_verificacao") == "ABC123XYZ"

    def test_certidao_positiva(self):
        texto = """
        CERTIDÃO POSITIVA DE DÉBITOS
        Esta certidão é POSITIVA.
        """
        extractor = CertidaoExtractor()
        result = extractor.extract(texto)
        assert result.data.get("status") == "positiva"


class TestRelatorioExtractor:
    """Tests for Report extractor."""

    SAMPLE_RELATORIO = """
    RELATÓRIO GERENCIAL
    Período: 01/01/2024 a 31/03/2024

    RESUMO EXECUTIVO

    Faturamento do período: R$ 1.500.000,00
    Crescimento em relação ao período anterior: 15%
    Meta atingida: 95%

    Margem de lucro: 22,5%
    Ticket médio: R$ 850,00

    Principais indicadores:
    - ROI: 18%
    - Satisfação do cliente: 92%

    Data do relatório: 15/04/2024
    """

    def test_extract_datas(self):
        extractor = RelatorioExtractor()
        result = extractor.extract(self.SAMPLE_RELATORIO)
        assert result.success
        assert "01/01/2024" in result.data.get("datas_encontradas", [])

    def test_extract_valores(self):
        extractor = RelatorioExtractor()
        result = extractor.extract(self.SAMPLE_RELATORIO)
        valores = result.data.get("valores_encontrados", [])
        assert len(valores) > 0

    def test_extract_percentuais(self):
        extractor = RelatorioExtractor()
        result = extractor.extract(self.SAMPLE_RELATORIO)
        percentuais = result.data.get("percentuais_encontrados", [])
        assert "15%" in percentuais or "15 %" in percentuais

    def test_extract_stats(self):
        extractor = RelatorioExtractor()
        result = extractor.extract(self.SAMPLE_RELATORIO)
        assert result.data.get("total_caracteres") > 0
        assert result.data.get("total_palavras") > 0
