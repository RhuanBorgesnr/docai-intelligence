"""
Generic Webhook Handler — the Intake agent's primary tool.

Receives leads from any external source (landing page, Typeform, HubSpot,
RD Station, Google Forms, Meta Lead Ads, etc.) and normalizes them into
the Lead model.

Each source can have a different payload format. The handler:
1. Validates HMAC signature (when configured)
2. Normalizes the payload to a standard schema
3. Creates the lead via ingest_lead()
4. Triggers SDR qualification
5. Notifies Theo if lead is hot

Sprint 4 / Phase 3 — Quick Win D1.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from agent_runtime.prompt_registry import AgentType

logger = logging.getLogger(__name__)


# ── Source-specific normalizers ───────────────────────────────────────────────

def _normalize_typeform(payload: dict) -> dict:
    """Normalize Typeform webhook payload."""
    answers = {
        a.get("field", {}).get("ref", ""): a.get("text") or a.get("email") or a.get("choice", {}).get("label", "")
        for a in payload.get("form_response", {}).get("answers", [])
    }
    return {
        "contact_name": answers.get("name", answers.get("nome", "")),
        "contact_email": answers.get("email", ""),
        "company_name": answers.get("company", answers.get("empresa", "")),
        "industry": answers.get("industry", answers.get("setor", "")),
        "company_size": answers.get("company_size", answers.get("porte", "")),
        "contact_phone": answers.get("phone", answers.get("telefone", "")),
    }


def _normalize_hubspot(payload: dict) -> dict:
    """Normalize HubSpot webhook payload."""
    props = payload.get("properties", {})
    return {
        "contact_name": f"{props.get('firstname', {}).get('value', '')} {props.get('lastname', {}).get('value', '')}".strip(),
        "contact_email": props.get("email", {}).get("value", ""),
        "company_name": props.get("company", {}).get("value", ""),
        "industry": props.get("industry", {}).get("value", ""),
        "contact_phone": props.get("phone", {}).get("value", ""),
    }


def _normalize_rdstation(payload: dict) -> dict:
    """Normalize RD Station webhook payload."""
    leads = payload.get("leads", [{}])
    lead = leads[0] if leads else {}
    return {
        "contact_name": lead.get("name", ""),
        "contact_email": lead.get("email", ""),
        "company_name": lead.get("company", ""),
        "industry": lead.get("tags", [""])[0] if lead.get("tags") else "",
        "contact_phone": lead.get("personal_phone", ""),
    }


def _normalize_meta_ads(payload: dict) -> dict:
    """Normalize Meta Lead Ads webhook payload."""
    field_data = {
        f.get("name", ""): f.get("values", [""])[0]
        for f in payload.get("field_data", [])
    }
    return {
        "contact_name": field_data.get("full_name", ""),
        "contact_email": field_data.get("email", ""),
        "company_name": field_data.get("company_name", ""),
        "contact_phone": field_data.get("phone_number", ""),
    }


def _normalize_google_forms(payload: dict) -> dict:
    """Normalize Google Forms webhook (via Zapier/Make)."""
    return {
        "contact_name": payload.get("name", payload.get("nome", "")),
        "contact_email": payload.get("email", ""),
        "company_name": payload.get("company", payload.get("empresa", "")),
        "industry": payload.get("industry", payload.get("setor", "")),
        "contact_phone": payload.get("phone", payload.get("telefone", "")),
    }


def _normalize_generic(payload: dict) -> dict:
    """Fallback: try common field names in both EN and PT."""
    return {
        "contact_name": (
            payload.get("name") or payload.get("nome") or
            payload.get("contact_name") or ""
        ),
        "contact_email": (
            payload.get("email") or payload.get("contact_email") or ""
        ),
        "company_name": (
            payload.get("company") or payload.get("empresa") or
            payload.get("company_name") or ""
        ),
        "industry": (
            payload.get("industry") or payload.get("setor") or
            payload.get("segment") or ""
        ),
        "company_size": (
            payload.get("company_size") or payload.get("porte") or ""
        ),
        "contact_phone": (
            payload.get("phone") or payload.get("telefone") or
            payload.get("contact_phone") or ""
        ),
    }


NORMALIZERS: dict[str, callable] = {
    "typeform": _normalize_typeform,
    "hubspot": _normalize_hubspot,
    "rdstation": _normalize_rdstation,
    "rd_station": _normalize_rdstation,
    "meta_ads": _normalize_meta_ads,
    "meta": _normalize_meta_ads,
    "google_forms": _normalize_google_forms,
    "google": _normalize_google_forms,
    "landing_page": _normalize_generic,
    "landing": _normalize_generic,
    "manual": _normalize_generic,
    "generic": _normalize_generic,
}


# ── HMAC Verification ────────────────────────────────────────────────────────

def verify_hmac(payload_bytes: bytes, signature: str, secret: str, algo: str = "sha256") -> bool:
    """
    Verify HMAC signature from webhook source.
    Returns True if valid or if no secret is configured (dev mode).
    """
    if not secret:
        return True  # No secret configured → skip verification (dev mode)

    computed = hmac.new(
        secret.encode(),
        payload_bytes,
        getattr(hashlib, algo, hashlib.sha256),
    ).hexdigest()

    return hmac.compare_digest(computed, signature)


# ── Main Handler ──────────────────────────────────────────────────────────────

def handle_webhook(source: str, payload: dict, raw_body: bytes | None = None,
                   signature: str | None = None, hmac_secret: str | None = None) -> dict[str, Any]:
    """
    Process an incoming webhook from any source.

    This is the Intake agent's core function:
    1. Verify HMAC if configured
    2. Normalize payload based on source
    3. Create lead via ingest_lead
    4. Return result

    Args:
        source: webhook source identifier (typeform, hubspot, etc.)
        payload: parsed JSON body
        raw_body: raw bytes for HMAC verification
        signature: HMAC signature from source header
        hmac_secret: secret for HMAC verification (None = skip)

    Returns:
        dict with created, lead_id, score, source, normalized_fields
    """
    # 1. HMAC verification
    if hmac_secret and raw_body:
        sig = signature or ""
        if not verify_hmac(raw_body, sig, hmac_secret):
            logger.warning("[INTAKE] HMAC verification failed for source=%s", source)
            return {"error": "HMAC verification failed", "source": source}

    # 2. Normalize
    normalizer = NORMALIZERS.get(source, _normalize_generic)
    normalized = normalizer(payload)

    # Strip empty values
    normalized = {k: v for k, v in normalized.items() if v}

    if not normalized.get("contact_email") and not normalized.get("contact_name"):
        logger.warning("[INTAKE] Webhook from %s has no identifiable contact", source)
        return {"error": "No contact info", "source": source}

    logger.info("[INTAKE] Processing webhook from %s: %s", source, normalized.get("contact_email", "unknown"))

    # 3. Create lead
    from commercial.services import ingest_lead

    result = ingest_lead(
        source=source,
        contact_email=normalized.get("contact_email", ""),
        contact_name=normalized.get("contact_name", ""),
        company_name=normalized.get("company_name", ""),
        industry=normalized.get("industry", ""),
        payload={**payload, "_normalized": normalized, "_source": source},
        consent_given=bool(payload.get("consent_given", payload.get("lgpd", True))),
    )

    return {
        "created": result.created,
        "lead_id": result.lead.lead_id,
        "score": result.lead.score,
        "source": source,
        "normalized_fields": list(normalized.keys()),
        "agent": AgentType.INTAKE.value,
    }
