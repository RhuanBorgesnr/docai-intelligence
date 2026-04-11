"""
Unit tests for extraction strategies.
"""
import pytest
from decimal import Decimal

from ai.extraction.strategies import RegexExtractionStrategy, AIExtractionStrategy


class TestRegexExtractionStrategy:
    """Tests for RegexExtractionStrategy."""

    def test_name(self):
        strategy = RegexExtractionStrategy()
        assert strategy.name == "regex"

    def test_extract_simple_values(self):
        text = """
        Receita Bruta: R$ 100.000,00
        Lucro Líquido: R$ 20.000,00
        """
        keywords = {
            "receita_bruta": ["receita bruta"],
            "lucro_liquido": ["lucro liquido"],
        }
        strategy = RegexExtractionStrategy()
        result = strategy.extract(text, keywords)

        assert result["receita_bruta"] == Decimal("100000.00")
        assert result["lucro_liquido"] == Decimal("20000.00")

    def test_extract_tabular_format(self):
        text = """
        Descrição           Jan      Fev       Mar      Acum
        Receita Bruta    50.000   55.000    60.000   165.000
        Custos          (30.000) (33.000)  (36.000)  (99.000)
        """
        keywords = {
            "receita_bruta": ["receita bruta"],
            "custos": ["custos"],
        }
        strategy = RegexExtractionStrategy()
        result = strategy.extract(text, keywords)

        # Should get last value (accumulated)
        assert result["receita_bruta"] == Decimal("165000")
        assert result["custos"] == Decimal("-99000")

    def test_extract_negative_values_in_parentheses(self):
        text = "Prejuízo do Exercício: (50.000,00)"
        keywords = {"prejuizo": ["prejuizo"]}
        strategy = RegexExtractionStrategy()
        result = strategy.extract(text, keywords)

        assert result["prejuizo"] == Decimal("-50000.00")

    def test_extract_with_accents(self):
        text = "Receita Líquida: 80.000,00"
        keywords = {"receita_liquida": ["receita liquida"]}
        strategy = RegexExtractionStrategy()
        result = strategy.extract(text, keywords)

        assert result["receita_liquida"] == Decimal("80000.00")

    def test_empty_text_returns_empty(self):
        strategy = RegexExtractionStrategy()
        result = strategy.extract("", {"field": ["keyword"]})
        assert result == {}

    def test_no_match_returns_empty(self):
        strategy = RegexExtractionStrategy()
        result = strategy.extract("Some random text", {"field": ["keyword"]})
        assert result == {}


class TestAIExtractionStrategy:
    """Tests for AIExtractionStrategy."""

    def test_name(self):
        strategy = AIExtractionStrategy()
        assert strategy.name == "ai"

    def test_build_prompt(self):
        strategy = AIExtractionStrategy()
        prompt = strategy._build_prompt(["receita", "lucro"])
        assert "receita" in prompt
        assert "lucro" in prompt
        assert "JSON" in prompt

    def test_parse_response_valid_json(self):
        strategy = AIExtractionStrategy()
        response = '{"receita": 100000, "lucro": 20000}'
        result = strategy._parse_response(response, ["receita", "lucro"])
        assert result["receita"] == 100000
        assert result["lucro"] == 20000

    def test_parse_response_json_with_text(self):
        strategy = AIExtractionStrategy()
        response = 'Here is the extracted data: {"receita": 100000} and more text'
        result = strategy._parse_response(response, ["receita"])
        assert result["receita"] == 100000

    def test_parse_response_invalid_json(self):
        strategy = AIExtractionStrategy()
        result = strategy._parse_response("invalid", ["field"])
        assert result == {}

    def test_parse_response_filters_fields(self):
        strategy = AIExtractionStrategy()
        response = '{"receita": 100000, "unknown_field": 999}'
        result = strategy._parse_response(response, ["receita"])
        assert "receita" in result
        assert "unknown_field" not in result

    def test_parse_response_removes_null(self):
        strategy = AIExtractionStrategy()
        response = '{"receita": 100000, "lucro": null}'
        result = strategy._parse_response(response, ["receita", "lucro"])
        assert "receita" in result
        assert "lucro" not in result
