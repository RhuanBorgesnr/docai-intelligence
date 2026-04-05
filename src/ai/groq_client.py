"""
Groq API client for financial document analysis.
Uses Llama 3 70B for intelligent text extraction.
"""
import json
import logging
import requests
from typing import Optional
from django.conf import settings

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Prompt otimizado para extração de DRE
EXTRACTION_PROMPT = """Você é um especialista em contabilidade brasileira. Analise o texto de uma DRE (Demonstração do Resultado do Exercício) e extraia os indicadores financeiros.

IMPORTANTE:
- Retorne APENAS um JSON válido, sem explicações
- Use números puros (sem R$, sem pontos de milhar)
- Use ponto como separador decimal (ex: 1234567.89)
- Para valores negativos, use sinal negativo (ex: -50000)
- Use null para valores não encontrados
- Se houver múltiplas colunas (meses), pegue o valor ACUMULADO ou TOTAL
- Valores em "R$ mil" ou "em milhares" devem ser multiplicados por 1000

Indicadores a extrair (retorne este JSON preenchido):
- receita_bruta
- receita_liquida
- custo (custo dos produtos/serviços vendidos)
- lucro_bruto
- despesas_op
- ebitda
- lucro_op
- lucro_liquido
- ativo_total
- passivo_total
- patrimonio_liq

TEXTO DA DRE:
{text}

Responda APENAS com o JSON:"""


def is_groq_enabled() -> bool:
    """Check if Groq API is configured."""
    api_key = getattr(settings, 'GROQ_API_KEY', '')
    return bool(api_key)


def _call_groq(messages: list, temperature: float = 0.3, max_tokens: int = 1000, json_mode: bool = False) -> Optional[str]:
    """
    Internal function to call Groq API.

    Args:
        messages: List of message dicts with 'role' and 'content'
        temperature: Creativity level (0-1)
        max_tokens: Max response length
        json_mode: If True, forces JSON response

    Returns:
        Response text or None if failed
    """
    api_key = getattr(settings, 'GROQ_API_KEY', '')
    if not api_key:
        logger.warning("Groq API key not configured")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = requests.post(
            GROQ_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content']

    except requests.exceptions.Timeout:
        logger.error("Groq API timeout")
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Groq API request failed: %s", e)
        return None
    except Exception as e:
        logger.exception("Unexpected error calling Groq: %s", e)
        return None


def chat_with_groq(context: str, question: str, max_context: int = 4000) -> Optional[str]:
    """
    Chat with documents using Groq's Llama 3.

    Args:
        context: Document context/chunks
        question: User's question
        max_context: Max chars for context

    Returns:
        Answer string or None if failed
    """
    if not is_groq_enabled():
        return None

    # Truncate context if needed
    if len(context) > max_context:
        context = context[:max_context]

    system_prompt = """Você é um assistente especializado em analisar documentos empresariais e financeiros.
Responda de forma clara, objetiva e em português brasileiro.
Use APENAS as informações do contexto fornecido.
Se a informação não estiver no contexto, diga claramente que não encontrou."""

    user_prompt = f"""CONTEXTO DOS DOCUMENTOS:
{context}

PERGUNTA DO USUÁRIO:
{question}

RESPOSTA:"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    logger.info("Calling Groq for chat...")
    response = _call_groq(messages, temperature=0.3, max_tokens=1000)

    if response:
        logger.info("Groq chat successful")
    return response


def extract_with_groq(text: str, max_chars: int = 4000) -> Optional[dict]:
    """
    Extract financial indicators using Groq's Llama 3.

    Args:
        text: Document text to analyze
        max_chars: Maximum characters to send

    Returns:
        Dict with extracted indicators or None if failed
    """
    if not is_groq_enabled():
        return None

    # Truncate text if needed
    truncated_text = text[:max_chars] if len(text) > max_chars else text

    prompt = EXTRACTION_PROMPT.format(text=truncated_text)

    messages = [{"role": "user", "content": prompt}]

    logger.info("Calling Groq API for financial extraction...")
    content = _call_groq(messages, temperature=0.1, max_tokens=500, json_mode=True)

    if not content:
        return None

    try:
        result = json.loads(content)

        # Filter out null values and validate
        indicators = {}
        for key, value in result.items():
            if value is not None:
                try:
                    indicators[key] = float(value)
                except (ValueError, TypeError):
                    continue

        logger.info("Groq extracted %d indicators: %s",
                    len(indicators), list(indicators.keys()))
        return indicators

    except json.JSONDecodeError as e:
        logger.error("Failed to parse Groq response: %s", e)
        return None
