"""Enums for the commercial domain (Sprint 4 / B1)."""
from __future__ import annotations

from django.db import models


class LeadSource(models.TextChoices):
    LANDING_PAGE = "landing_page", "Landing Page"
    INBOUND_FORM = "inbound_form", "Inbound Form"
    OUTBOUND = "outbound", "Outbound"
    REFERRAL = "referral", "Referral"
    EVENT = "event", "Event"
    LINKEDIN = "linkedin", "LinkedIn"
    META_ADS = "meta_ads", "Meta Ads"
    GOOGLE_ADS = "google_ads", "Google Ads"
    PARTNER = "partner", "Partner"
    MANUAL = "manual", "Manual"
    IMPORT = "import", "CSV Import"
    OTHER = "other", "Other"


class LeadStatus(models.TextChoices):
    NEW = "new", "New"
    QUALIFYING = "qualifying", "Qualifying"
    QUALIFIED = "qualified", "Qualified"
    DISQUALIFIED = "disqualified", "Disqualified"
    NURTURING = "nurturing", "Nurturing"
    CONVERTED = "converted", "Converted (Opportunity)"


class OpportunityStage(models.TextChoices):
    NEW = "new", "New"
    QUALIFIED = "qualified", "Qualified"
    DEMO_SCHEDULED = "demo_scheduled", "Demo Scheduled"
    DEMO_DONE = "demo_done", "Demo Done"
    PROPOSAL_SENT = "proposal_sent", "Proposal Sent"
    NEGOTIATION = "negotiation", "Negotiation"
    WON = "won", "Won"
    LOST = "lost", "Lost"


#: Stages considered "active" (still in pipeline).
ACTIVE_OPPORTUNITY_STAGES: tuple[str, ...] = (
    OpportunityStage.NEW,
    OpportunityStage.QUALIFIED,
    OpportunityStage.DEMO_SCHEDULED,
    OpportunityStage.DEMO_DONE,
    OpportunityStage.PROPOSAL_SENT,
    OpportunityStage.NEGOTIATION,
)
