"""
Sprint 4 — seed demo data for the commercial dashboard.

Usage:
    python manage.py seed_commercial_demo            # adds ~12 leads + opportunities
    python manage.py seed_commercial_demo --reset    # wipes existing demo data first
"""
from __future__ import annotations

import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from commercial.enums import OpportunityStage
from commercial.models import FollowUpDraft, Lead, LeadScoreEvent, Opportunity
from commercial.services import create_opportunity, ingest_lead

DEMO_LEADS = [
    # (source, email, company, industry, size, country, message)
    ("referral",     "cfo@bancoalfa.com.br",   "Banco Alfa",        "banking",            "201-1000", "BR", "Quero proposta urgente para automatizar leitura de contratos."),
    ("landing_page", "ana@fintechbeta.com",    "Fintech Beta",      "fintech",            "51-200",   "BR", "Pedido de demo do DocAI."),
    ("inbound_form", "joao@auditgama.com.br",  "Audit Gama",        "audit",              "11-50",    "BR", "Avaliar pricing e trial."),
    ("partner",      "compras@delta.com.br",   "Delta Indústrias",  "manufacturing",      "1000+",    "BR", "Comparativo com solução atual."),
    ("linkedin",     "marina@epsilonseg.com",  "Epsilon Seguros",   "insurance",          "201-1000", "BR", "Reduzir tempo de onboarding de apólices."),
    ("outbound",     "ricardo@zetalegal.com",  "Zeta Legal",        "legal",              "11-50",    "BR", ""),
    ("event",        "contato@etacontab.com",  "Eta Contabilidade", "accounting",         "11-50",    "BR", "Avaliar demo após evento."),
    ("manual",       "buyer@thetacorp.com",    "Theta Corp",        "retail",             "51-200",   "BR", "Interesse inicial."),
    ("referral",     "cto@iotaadvisory.com",   "Iota Advisory",     "advisory",           "1-10",     "BR", "Pedido de orçamento."),
    ("landing_page", "pedro@kappabank.com",    "Kappa Bank",        "banking",            "1000+",    "PT", "Quero comprar agora."),
    ("inbound_form", "nubia@lambdafs.com",     "Lambda FS",         "financial services", "51-200",   "BR", "Demo + pricing."),
    ("other",        "noreply@mu-test.com",    "Mu Test",           "",                   "1-10",     "US", "spam?"),
]


class Command(BaseCommand):
    help = "Seed the commercial dashboard with realistic demo leads, opportunities, and follow-ups."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Wipe demo Leads/Opps first.")

    def handle(self, *args, **opts):
        if opts["reset"]:
            FollowUpDraft.objects.all().delete()
            LeadScoreEvent.objects.all().delete()
            Opportunity.objects.all().delete()
            Lead.objects.all().delete()
            self.stdout.write(self.style.WARNING("Demo data wiped."))

        created_leads = 0
        created_opps = 0

        for source, email, company, industry, size, country, msg in DEMO_LEADS:
            result = ingest_lead(
                source=source,
                contact_email=email,
                company_name=company,
                industry=industry,
                company_size=size,
                country=country,
                consent_given=True,
                payload={"message": msg} if msg else {},
            )
            lead = result.lead
            if result.created:
                created_leads += 1

            # For high-score leads, force-create an Opportunity in a random active stage
            # so the kanban has visible cards without depending on the LLM.
            if lead.score >= 60 and not Opportunity.objects.filter(lead=lead).exists():
                stage = random.choice([
                    OpportunityStage.QUALIFIED,
                    OpportunityStage.DEMO_SCHEDULED,
                    OpportunityStage.DEMO_DONE,
                    OpportunityStage.PROPOSAL_SENT,
                    OpportunityStage.NEGOTIATION,
                ])
                opp = create_opportunity(
                    lead,
                    estimated_value=Decimal(random.choice([15000, 30000, 60000, 120000, 250000])),
                )
                opp.win_probability = round(random.uniform(0.3, 0.85), 2)
                # Move to the chosen stage if not already QUALIFIED
                if stage != OpportunityStage.QUALIFIED:
                    opp.stage = stage
                opp.save(update_fields=["stage", "win_probability", "updated_at"])
                created_opps += 1

        # Add a couple of WON / LOST for KPI variety
        sample = list(Opportunity.objects.all()[:2])
        if len(sample) >= 2:
            sample[0].stage = OpportunityStage.WON
            sample[0].closed_at = timezone.now()
            sample[0].estimated_value = Decimal("180000")
            sample[0].save()
            sample[1].stage = OpportunityStage.LOST
            sample[1].closed_at = timezone.now()
            sample[1].save()

        self.stdout.write(self.style.SUCCESS(
            f"Seed complete: {created_leads} new leads, {created_opps} opportunities. "
            f"(Total leads: {Lead.objects.count()}, opps: {Opportunity.objects.count()})"
        ))
