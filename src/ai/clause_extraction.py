"""
Contract clause extraction using AI.
"""
import re
import json
import logging
from typing import List, Dict, Optional

from ai.llm import generate_text

logger = logging.getLogger(__name__)

CLAUSE_EXTRACTION_PROMPT = """
Analise o contrato abaixo e identifique as cláusulas importantes.
Para cada cláusula encontrada, retorne um JSON com:
- type: tipo da cláusula (multa, reajuste, rescisao, vigencia, renovacao, confidencialidade, garantia, pagamento, responsabilidade, foro, outro)
- title: título ou número da cláusula
- content: texto resumido da cláusula (máximo 200 caracteres)
- value: valor específico extraído (ex: "2% ao mês", "30 dias", "R$ 1.000,00")
- risk: nível de risco (low, medium, high)

Retorne APENAS um JSON array válido. Exemplo:
[{{"type": "multa", "title": "Cláusula 8", "content": "Multa de 2% ao mês...", "value": "2% ao mês", "risk": "high"}}]

CONTRATO:
{text}

JSON:
"""

CLAUSE_TYPE_MAPPING = {
    "multa": "multa",
    "penalidade": "multa",
    "reajuste": "reajuste",
    "correcao": "reajuste",
    "correção": "reajuste",
    "rescisao": "rescisao",
    "rescisão": "rescisao",
    "vigencia": "vigencia",
    "vigência": "vigencia",
    "prazo": "vigencia",
    "renovacao": "renovacao",
    "renovação": "renovacao",
    "confidencialidade": "confidencialidade",
    "sigilo": "confidencialidade",
    "garantia": "garantia",
    "pagamento": "pagamento",
    "responsabilidade": "responsabilidade",
    "obrigacao": "responsabilidade",
    "obrigações": "responsabilidade",
    "foro": "foro",
    "jurisdicao": "foro",
    "jurisdição": "foro",
}

RISK_KEYWORDS = {
    "high": ["multa", "penalidade", "rescisão imediata", "indenização", "perda", "exclusividade"],
    "medium": ["reajuste", "renovação automática", "prazo", "garantia"],
    "low": ["confidencialidade", "foro", "comunicação"]
}


def normalize_clause_type(clause_type: str) -> str:
    """Normalize clause type to valid choice."""
    if not clause_type:
        return "outro"

    normalized = clause_type.lower().strip()

    # Direct mapping
    if normalized in CLAUSE_TYPE_MAPPING:
        return CLAUSE_TYPE_MAPPING[normalized]

    # Partial match
    for key, value in CLAUSE_TYPE_MAPPING.items():
        if key in normalized:
            return value

    return "outro"


def estimate_risk_level(clause_type: str, content: str) -> str:
    """Estimate risk level based on clause type and content."""
    content_lower = content.lower() if content else ""

    for level, keywords in RISK_KEYWORDS.items():
        for keyword in keywords:
            if keyword in content_lower or keyword in clause_type.lower():
                return level

    return "medium"


def extract_json_from_response(response: str) -> List[Dict]:
    """Extract JSON array from LLM response."""
    # Try direct parse
    try:
        result = json.loads(response)
        if isinstance(result, list):
            return result
        return [result]
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in response
    array_match = re.search(r'\[[\s\S]*?\]', response)
    if array_match:
        try:
            result = json.loads(array_match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # Try to find single JSON object
    obj_match = re.search(r'\{[\s\S]*?\}', response)
    if obj_match:
        try:
            result = json.loads(obj_match.group())
            return [result]
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from response: %s", response[:200])
    return []


def extract_contract_clauses(text: str, max_chars: int = 4000) -> List[Dict]:
    """
    Extract important clauses from contract text using AI.

    Args:
        text: The contract text to analyze.
        max_chars: Maximum characters to send to LLM.

    Returns:
        List of dicts with clause information.
    """
    if not text or len(text.strip()) < 100:
        logger.info("Text too short for clause extraction")
        return []

    # Truncate text if needed
    truncated_text = text[:max_chars] if len(text) > max_chars else text

    prompt = CLAUSE_EXTRACTION_PROMPT.format(text=truncated_text)

    try:
        response = generate_text(prompt, max_new_tokens=500, temperature=0.2)
        logger.debug("LLM response for clause extraction: %s", response)
    except Exception as e:
        logger.exception("LLM call failed for clause extraction: %s", e)
        return []

    raw_clauses = extract_json_from_response(response)

    # Validate and normalize clauses
    clauses = []
    for raw in raw_clauses:
        if not isinstance(raw, dict):
            continue

        clause_type = normalize_clause_type(raw.get("type", ""))
        content = raw.get("content", "")[:500]  # Limit content length

        # Estimate risk if not provided
        risk = raw.get("risk", "").lower()
        if risk not in ["low", "medium", "high"]:
            risk = estimate_risk_level(clause_type, content)

        clause = {
            "clause_type": clause_type,
            "title": raw.get("title", "Cláusula")[:255],
            "content": content,
            "summary": raw.get("summary", "")[:500],
            "extracted_value": raw.get("value", "")[:255],
            "risk_level": risk
        }
        clauses.append(clause)

    logger.info("Extracted %d contract clauses", len(clauses))
    return clauses


def extract_clauses_with_regex(text: str) -> List[Dict]:
    """
    Fallback: Extract clauses using regex patterns.
    """
    clauses = []

    patterns = [
        (r'(?:cláusula|artigo)\s*(?:\d+|[ivxlcdm]+)[º°]?\s*[-–:.]?\s*(?:da\s+)?multa[^.]*\.', 'multa'),
        (r'(?:cláusula|artigo)\s*(?:\d+|[ivxlcdm]+)[º°]?\s*[-–:.]?\s*(?:do\s+)?reajuste[^.]*\.', 'reajuste'),
        (r'(?:cláusula|artigo)\s*(?:\d+|[ivxlcdm]+)[º°]?\s*[-–:.]?\s*(?:da\s+)?rescis[ãa]o[^.]*\.', 'rescisao'),
        (r'(?:cláusula|artigo)\s*(?:\d+|[ivxlcdm]+)[º°]?\s*[-–:.]?\s*(?:do\s+)?prazo[^.]*\.', 'vigencia'),
        (r'(?:cláusula|artigo)\s*(?:\d+|[ivxlcdm]+)[º°]?\s*[-–:.]?\s*(?:da\s+)?vigência[^.]*\.', 'vigencia'),
        (r'(?:cláusula|artigo)\s*(?:\d+|[ivxlcdm]+)[º°]?\s*[-–:.]?\s*(?:da\s+)?renova[çc][ãa]o[^.]*\.', 'renovacao'),
        (r'(?:cláusula|artigo)\s*(?:\d+|[ivxlcdm]+)[º°]?\s*[-–:.]?\s*(?:do\s+)?foro[^.]*\.', 'foro'),
    ]

    text_lower = text.lower()

    for pattern, clause_type in patterns:
        matches = re.findall(pattern, text_lower, re.IGNORECASE)
        for match in matches[:2]:  # Limit to 2 matches per type
            clauses.append({
                "clause_type": clause_type,
                "title": f"Cláusula de {clause_type.title()}",
                "content": match[:300],
                "summary": "",
                "extracted_value": "",
                "risk_level": estimate_risk_level(clause_type, match)
            })

    return clauses
