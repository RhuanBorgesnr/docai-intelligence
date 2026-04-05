"""
Financial indicator extraction from documents using AI.
"""
import re
import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

from ai.llm import generate_text

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """
Analise o texto financeiro abaixo e extraia os indicadores numéricos.
Retorne APENAS um JSON válido com os valores encontrados.
Use null para valores não encontrados.
Valores devem ser números (sem R$, sem pontos de milhar, use ponto para decimal).

Indicadores a extrair:
- receita_bruta
- receita_liquida
- custo (custo dos produtos/serviços vendidos)
- lucro_bruto
- despesas_op (despesas operacionais)
- ebitda
- lucro_op (lucro operacional)
- lucro_liquido
- ativo_total
- passivo_total
- patrimonio_liq (patrimônio líquido)

TEXTO:
{text}

JSON:
"""

INDICATOR_MAPPING = {
    "receita_bruta": "receita_bruta",
    "receita_liquida": "receita_liquida",
    "custo": "custo",
    "lucro_bruto": "lucro_bruto",
    "despesas_op": "despesas_op",
    "ebitda": "ebitda",
    "lucro_op": "lucro_op",
    "lucro_liquido": "lucro_liquido",
    "ativo_total": "ativo_total",
    "passivo_total": "passivo_total",
    "patrimonio_liq": "patrimonio_liq",
}


def parse_value(value) -> Optional[Decimal]:
    """Parse a value to Decimal, handling various formats."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None

    if isinstance(value, str):
        # Remove currency symbols and whitespace
        cleaned = value.strip()
        cleaned = re.sub(r'[R$\s]', '', cleaned)

        # Handle Brazilian format: 1.234.567,89 -> 1234567.89
        if ',' in cleaned and '.' in cleaned:
            cleaned = cleaned.replace('.', '').replace(',', '.')
        elif ',' in cleaned:
            cleaned = cleaned.replace(',', '.')

        # Remove remaining non-numeric chars except minus and dot
        cleaned = re.sub(r'[^\d.\-]', '', cleaned)

        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    return None


def extract_json_from_response(response: str) -> dict:
    """Extract JSON from LLM response, handling common issues."""
    # Try direct parse
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in response
    json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Try to fix common issues
    fixed = response.strip()
    if not fixed.startswith('{'):
        fixed = '{' + fixed
    if not fixed.endswith('}'):
        fixed = fixed + '}'

    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        logger.warning("Could not parse JSON from response: %s", response[:200])
        return {}


def calculate_margins(indicators: dict) -> dict:
    """Calculate margin percentages from extracted values."""
    margins = {}

    receita = indicators.get("receita_liquida") or indicators.get("receita_bruta")

    if receita and receita > 0:
        if indicators.get("lucro_bruto"):
            margins["margem_bruta"] = (indicators["lucro_bruto"] / receita * 100).quantize(Decimal("0.01"))

        if indicators.get("lucro_liquido"):
            margins["margem_liquida"] = (indicators["lucro_liquido"] / receita * 100).quantize(Decimal("0.01"))

        if indicators.get("ebitda"):
            margins["margem_ebitda"] = (indicators["ebitda"] / receita * 100).quantize(Decimal("0.01"))

    return margins


def normalize_text(text: str) -> str:
    """Normalize text for matching: remove accents and convert to lowercase."""
    import unicodedata
    # Normalize unicode and remove accents
    normalized = unicodedata.normalize('NFD', text)
    without_accents = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    return without_accents.lower()


# Standard DRE structure keywords - ordered by priority (more specific first)
# Based on Brazilian accounting standards (Lei 6.404/76 and CPC)
DRE_KEYWORDS = [
    # Receitas
    ("receita_bruta", [
        "receita operacional bruta",
        "receita bruta de vendas",
        "receita bruta",
        "faturamento bruto",
        "vendas brutas",
        "receitas de vendas",
    ]),
    ("receita_liquida", [
        "receita operacional liquida",
        "receita liquida de vendas",
        "receita liquida",
        "faturamento liquido",
        "vendas liquidas",
    ]),
    # Custos
    ("custo", [
        "custo dos servicos prestados",
        "custo dos produtos vendidos",
        "custo das mercadorias vendidas",
        "custo dos bens vendidos",
        "custos operacionais",
        "custo de vendas",
        "(-) custos",
        "cmv",
        "cpv",
        "csv",
    ]),
    # Lucro Bruto
    ("lucro_bruto", [
        "resultado bruto",
        "lucro bruto",
        "margem bruta",
    ]),
    # Despesas
    ("despesas_op", [
        "despesas operacionais",
        "despesas gerais e administrativas",
        "despesas administrativas",
        "despesas com vendas",
        "despesas comerciais",
    ]),
    # EBITDA
    ("ebitda", [
        "ebitda",
        "lajida",
        "lucro antes de juros impostos depreciacao",
    ]),
    # Resultado Operacional
    ("lucro_op", [
        "resultado operacional antes",
        "resultado operacional liquido",
        "resultado operacional",
        "lucro operacional",
        "resultado antes do resultado financeiro",
        "lair",  # Lucro Antes do IR
    ]),
    # Resultado Financeiro
    ("resultado_fin", [
        "resultado financeiro liquido",
        "resultado financeiro",
        "receitas financeiras",
    ]),
    # Lucro/Prejuízo Líquido
    ("lucro_liquido", [
        "prejuizo liquido do exercicio",
        "prejuizo do exercicio",
        "prejuizo liquido",
        "lucro liquido do exercicio",
        "lucro do exercicio",
        "lucro liquido",
        "resultado liquido do exercicio",
        "resultado liquido",
        "resultado do exercicio",
    ]),
    # Balanço Patrimonial
    ("ativo_total", [
        "total do ativo",
        "ativo total",
        "total ativo",
    ]),
    ("passivo_total", [
        "total do passivo",
        "passivo total",
        "total passivo",
    ]),
    ("patrimonio_liq", [
        "patrimonio liquido total",
        "total patrimonio liquido",
        "patrimonio liquido",
        "capital social",
    ]),
]


def extract_with_regex(text: str) -> dict:
    """
    Extract financial indicators from DRE/Balance Sheet text.

    Handles multiple formats:
    - Simple: "Receita Bruta: R$ 1.234.567,89"
    - Tabular: "Receita Bruta    194.398    207.629    627.169"
    - With deductions: "(-) Custos    (500.000)"

    Uses standard Brazilian accounting terminology.
    """
    indicators = {}

    # Normalize full text for comparison
    text_normalized = normalize_text(text)
    lines = text.split('\n')

    # Track which lines have been matched to avoid duplicates
    matched_lines = set()

    for indicator_type, keywords in DRE_KEYWORDS:
        if indicator_type in indicators:
            continue

        for keyword in keywords:
            keyword_norm = normalize_text(keyword)

            # Search each line
            for i, line in enumerate(lines):
                if i in matched_lines:
                    continue

                line_norm = normalize_text(line)

                if keyword_norm in line_norm:
                    # Find all numbers in the original line
                    # Pattern: digits with optional thousand sep (.) and decimal (,)
                    # Also captures numbers in parentheses (negative)
                    numbers = re.findall(r'\(?([\d]+(?:[.,][\d]+)*)\)?', line)

                    if numbers:
                        # Get LAST number (accumulated/total in tabular format)
                        last_number = numbers[-1]

                        # Check if negative (in parentheses or preceded by -)
                        is_negative = (
                            f"({last_number})" in line or
                            f"( {last_number})" in line or
                            f"({last_number} )" in line or
                            re.search(rf'-\s*{re.escape(last_number)}', line)
                        )

                        value = parse_value(last_number)
                        if value is not None and value != 0:
                            if is_negative:
                                value = -abs(value)
                            indicators[indicator_type] = value
                            matched_lines.add(i)
                            logger.debug(f"Extracted {indicator_type}: {value} from '{line.strip()[:60]}...'")
                            break

            if indicator_type in indicators:
                break  # Found this indicator, move to next

    logger.info("DRE extraction found %d indicators: %s",
                len(indicators), list(indicators.keys()))
    return indicators


def extract_financial_indicators(text: str, max_chars: int = 4000) -> dict:
    """
    Extract financial indicators from document text.

    Strategy:
    1. First try regex extraction (fast, free, reliable for standard formats)
    2. If regex fails, use Groq API (Llama 3 70B - powerful and free)
    3. If Groq fails, fallback to local Flan-T5

    Args:
        text: The document text to analyze.
        max_chars: Maximum characters to send to AI.

    Returns:
        Dict with indicator_type -> Decimal value mappings.
    """
    if not text or len(text.strip()) < 50:
        logger.info("Text too short for financial extraction")
        return {}

    # 1. First try regex extraction (fast and reliable)
    indicators = extract_with_regex(text)

    # If regex found at least 3 key indicators, use them
    key_indicators = {'receita_bruta', 'receita_liquida', 'lucro_bruto', 'lucro_liquido'}
    found_keys = set(indicators.keys()) & key_indicators

    if len(found_keys) >= 2:
        logger.info("Using regex extraction results: %d indicators", len(indicators))
        margins = calculate_margins(indicators)
        indicators.update(margins)
        return indicators

    # 2. Try Groq API (Llama 3 70B - free tier)
    logger.info("Regex found insufficient indicators, trying Groq API...")
    try:
        from ai.groq_client import extract_with_groq, is_groq_enabled

        if is_groq_enabled():
            groq_result = extract_with_groq(text, max_chars)
            if groq_result:
                # Convert to Decimal
                for key, value in groq_result.items():
                    if key in INDICATOR_MAPPING and value is not None:
                        parsed = parse_value(value)
                        if parsed is not None:
                            indicators[key] = parsed

                if indicators:
                    logger.info("Groq extraction successful: %d indicators", len(indicators))
                    margins = calculate_margins(indicators)
                    indicators.update(margins)
                    return indicators
    except Exception as e:
        logger.warning("Groq extraction failed: %s", e)

    # 3. Fallback to local LLM (Flan-T5)
    logger.info("Falling back to local LLM extraction...")
    truncated_text = text[:max_chars] if len(text) > max_chars else text
    prompt = EXTRACTION_PROMPT.format(text=truncated_text)

    try:
        response = generate_text(prompt, max_new_tokens=300, temperature=0.1)
        logger.debug("LLM response for financial extraction: %s", response)
    except Exception as e:
        logger.exception("LLM call failed for financial extraction: %s", e)
        return indicators  # Return whatever we have from regex

    raw_data = extract_json_from_response(response)

    # Parse and validate values
    for key, indicator_type in INDICATOR_MAPPING.items():
        if key in raw_data and indicator_type not in indicators:
            value = parse_value(raw_data[key])
            if value is not None:
                indicators[indicator_type] = value

    # Calculate margins
    margins = calculate_margins(indicators)
    indicators.update(margins)

    logger.info("Extracted %d financial indicators", len(indicators))
    return indicators
