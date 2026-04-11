"""
Unit tests for extraction utilities.
"""
import pytest
from decimal import Decimal
from datetime import date

from ai.extraction.utils import TextNormalizer, ValueParser


class TestTextNormalizer:
    """Tests for TextNormalizer class."""

    def test_normalize_removes_accents(self):
        assert TextNormalizer.normalize("Receita Líquida") == "receita liquida"
        assert TextNormalizer.normalize("Ação") == "acao"
        assert TextNormalizer.normalize("Código") == "codigo"

    def test_normalize_lowercases(self):
        assert TextNormalizer.normalize("RECEITA BRUTA") == "receita bruta"
        assert TextNormalizer.normalize("Lucro Líquido") == "lucro liquido"

    def test_normalize_empty_string(self):
        assert TextNormalizer.normalize("") == ""

    def test_clean_number_brazilian_format(self):
        assert TextNormalizer.clean_number("R$ 1.234,56") == "1234.56"
        assert TextNormalizer.clean_number("1.234.567,89") == "1234567.89"

    def test_clean_number_simple(self):
        assert TextNormalizer.clean_number("1234.56") == "1234.56"
        assert TextNormalizer.clean_number("1234,56") == "1234.56"

    def test_clean_number_with_spaces(self):
        assert TextNormalizer.clean_number("  R$ 100,00  ") == "100.00"


class TestValueParser:
    """Tests for ValueParser class."""

    def test_to_decimal_from_string(self):
        assert ValueParser.to_decimal("1234.56") == Decimal("1234.56")
        assert ValueParser.to_decimal("R$ 1.234,56") == Decimal("1234.56")

    def test_to_decimal_from_int(self):
        assert ValueParser.to_decimal(1234) == Decimal("1234")

    def test_to_decimal_from_float(self):
        assert ValueParser.to_decimal(1234.56) == Decimal("1234.56")

    def test_to_decimal_none(self):
        assert ValueParser.to_decimal(None) is None

    def test_to_decimal_invalid(self):
        assert ValueParser.to_decimal("abc") is None
        assert ValueParser.to_decimal("") is None

    def test_to_date_brazilian_format(self):
        assert ValueParser.to_date("25/12/2024") == date(2024, 12, 25)
        assert ValueParser.to_date("01/01/2025") == date(2025, 1, 1)

    def test_to_date_iso_format(self):
        assert ValueParser.to_date("2024-12-25") == date(2024, 12, 25)

    def test_to_date_invalid(self):
        assert ValueParser.to_date("invalid") is None
        assert ValueParser.to_date("32/13/2024") is None
