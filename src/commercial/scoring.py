"""
Lead scoring (Sprint 4 / B1.3).

Heuristic, deterministic scoring used by the SDR Agent and as a fast pre-score
on lead ingestion. Designed to be cheap (no LLM call), explainable and easy to
unit-test. The SDR Agent can later override the score based on richer context.

Score is in the range [0, 100].
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from commercial.enums import LeadSource


# ── ICP definition (kept here so it lives in code review until promoted to DB) ─
ICP_TARGET_INDUSTRIES: tuple[str, ...] = (
    "financial services", "fintech", "banking", "insurance",
    "accounting", "legal", "advisory", "audit",
    "manufacturing", "retail",
)

ICP_TARGET_COUNTRIES: tuple[str, ...] = ("BR", "PT")

# Company size buckets and their score contribution.
ICP_SIZE_SCORES: dict[str, int] = {
    "1-10": 5,
    "11-50": 15,
    "51-200": 25,
    "201-1000": 30,
    "1000+": 25,
}

# Source quality (warmer sources score higher up-front).
SOURCE_SCORES: dict[str, int] = {
    LeadSource.REFERRAL: 25,
    LeadSource.PARTNER: 20,
    LeadSource.LANDING_PAGE: 15,
    LeadSource.INBOUND_FORM: 15,
    LeadSource.EVENT: 12,
    LeadSource.LINKEDIN: 10,
    LeadSource.OUTBOUND: 8,
    LeadSource.META_ADS: 6,
    LeadSource.GOOGLE_ADS: 6,
    LeadSource.MANUAL: 5,
    LeadSource.IMPORT: 3,
    LeadSource.OTHER: 0,
}


@dataclass
class ScoreBreakdown:
    """Explainable score with per-component contribution."""
    total: int
    components: dict[str, int]
    icp_fit: dict[str, bool]

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "components": self.components,
            "icp_fit": self.icp_fit,
        }


def _normalise(text: str) -> str:
    return (text or "").strip().lower()


def _has_any(value: str, targets: Iterable[str]) -> bool:
    v = _normalise(value)
    return any(t in v for t in targets)


def compute_lead_score(
    *,
    source: str = "",
    industry: str = "",
    company_size: str = "",
    country: str = "BR",
    contact_email: str = "",
    company_name: str = "",
    consent_given: bool = False,
    payload: dict | None = None,
) -> ScoreBreakdown:
    """Compute a deterministic 0–100 lead score with explainable breakdown."""
    payload = payload or {}
    components: dict[str, int] = {}
    icp_fit: dict[str, bool] = {}

    # Source
    components["source"] = SOURCE_SCORES.get(source, 0)

    # Industry ICP
    industry_match = _has_any(industry, ICP_TARGET_INDUSTRIES)
    icp_fit["industry"] = industry_match
    components["industry"] = 20 if industry_match else 0

    # Country ICP
    country_match = _normalise(country).upper() in ICP_TARGET_COUNTRIES
    icp_fit["country"] = country_match
    components["country"] = 10 if country_match else 0

    # Company size
    size_score = ICP_SIZE_SCORES.get(_normalise(company_size), 0)
    icp_fit["size"] = size_score >= 15
    components["size"] = size_score

    # Contact completeness — concrete contact data is a strong signal.
    has_email = "@" in (contact_email or "")
    has_company = bool(company_name and company_name.strip())
    completeness = 0
    if has_email:
        completeness += 8
    if has_company:
        completeness += 5
    components["completeness"] = completeness
    icp_fit["contactable"] = has_email

    # Intent keywords in payload (e.g. message body / form notes).
    intent_terms = ("demo", "trial", "proposta", "comprar", "preço", "pricing", "orçamento")
    notes = " ".join(
        str(v) for v in payload.values() if isinstance(v, (str, int, float))
    )
    intent_hits = sum(1 for term in intent_terms if term in _normalise(notes))
    components["intent"] = min(15, intent_hits * 5)
    icp_fit["intent_signal"] = intent_hits > 0

    # Consent (LGPD) — small bonus + unblocks outbound automation downstream.
    components["consent"] = 5 if consent_given else 0

    total = sum(components.values())
    total = max(0, min(100, total))
    return ScoreBreakdown(total=total, components=components, icp_fit=icp_fit)
