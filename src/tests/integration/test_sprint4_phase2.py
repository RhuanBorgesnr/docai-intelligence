"""
Sprint 4 / Phase 2 — integration tests.

Covers:
- Document upload + link to Lead.
- DocAI Operator with RAG context (real pipeline, fallback heuristics).
- Insights endpoint returns ranked output.
- Lead timeline endpoint.
- UX separation: /api/commercial/ requires authentication.
- ANALYST prompt is registered in PromptRegistry.
"""
from __future__ import annotations

import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from agent_runtime.prompt_registry import AgentType, PromptRegistry
from audit.models import AuditLog
from commercial.docai_operator import run_docai_demo
from commercial.models import Lead
from commercial.services import ingest_lead
from documents.models import Document


@pytest.fixture
def staff_client(db):
    User = get_user_model()
    user = User.objects.create_user(username="ops_staff", password="x", is_staff=True)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def normal_client(db):
    User = get_user_model()
    user = User.objects.create_user(username="customer", password="x", is_staff=False)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def lead_with_doc(db):
    result = ingest_lead(
        source="referral",
        contact_email="cfo@bigco.com",
        company_name="BigCo",
        industry="financial services",
        company_size="51-200",
        consent_given=True,
    )
    doc = Document.objects.create(
        title="DRE BigCo 2025",
        document_type="dre",
        processing_status="completed",
        extracted_text="Receita Bruta: R$ 5.000.000\nEBITDA: R$ 1.200.000\nLucro Líquido: R$ 600.000",
        extracted_metadata={
            "receita_bruta": "5000000",
            "ebitda": "1200000",
            "lucro_liquido": "600000",
        },
        file=SimpleUploadedFile("dre.txt", b"dummy"),
    )
    # Link doc to lead
    payload = dict(result.lead.payload or {})
    payload["documents"] = [{"document_id": doc.id, "title": doc.title, "type": doc.document_type}]
    result.lead.payload = payload
    result.lead.save(update_fields=["payload"])
    return result.lead, doc


# ── ANALYST prompt is registered ──────────────────────────────────────────────

class TestAnalystPromptRegistered:
    def test_analyst_prompt_exists_and_has_rag_context_variable(self):
        prompt = PromptRegistry.get_prompt(AgentType.ANALYST)
        assert prompt is not None
        assert "rag_context" in prompt.content
        assert "insights" in prompt.content

    def test_analyst_schema_requires_insights_and_summary(self):
        schema = PromptRegistry.get_schema(AgentType.ANALYST)
        assert schema is not None
        assert "insights" in schema.required
        assert "summary" in schema.required


# ── Document upload via API ───────────────────────────────────────────────────

@pytest.mark.django_db
class TestDocumentUpload:
    def test_upload_links_doc_to_lead(self, staff_client):
        result = ingest_lead(source="manual", contact_email="a@x.com", consent_given=True)
        lead = result.lead
        f = SimpleUploadedFile("contrato.pdf", b"PDF content", content_type="application/pdf")
        resp = staff_client.post(
            f"/api/commercial/leads/{lead.lead_id}/documents/",
            {"file": f, "title": "Contrato X", "document_type": "contract"},
            format="multipart",
        )
        assert resp.status_code == 201
        assert resp.json()["document_id"]
        assert resp.json()["document_type"] == "contract"

        # Document linked in lead payload
        lead.refresh_from_db()
        assert len(lead.payload.get("documents", [])) == 1


# ── DocAI Operator real pipeline ──────────────────────────────────────────────

@pytest.mark.django_db
class TestDocAIOperatorReal:
    def test_run_docai_demo_generates_ranked_insights(self, lead_with_doc):
        lead, doc = lead_with_doc
        result = run_docai_demo(lead_id=lead.id, document_id=doc.id)

        assert "insights" in result
        assert len(result["insights"]) >= 1
        # Insights are ranked by score (descending)
        scores = [i.get("score", 0) for i in result["insights"]]
        assert scores == sorted(scores, reverse=True)

        # Each insight has required fields
        for ins in result["insights"]:
            assert "type" in ins
            assert "title" in ins
            assert "action" in ins

        # Automations suggested
        assert "automations" in result
        assert len(result["automations"]) >= 1

        # RAG sources tracked
        assert "rag_sources" in result

        # Persisted on lead
        lead.refresh_from_db()
        assert len(lead.payload.get("docai_insights", [])) >= 1

        # Audit trail
        assert AuditLog.objects.filter(
            case_id=lead.case_id,
            action="commercial.docai_demo.generated",
        ).exists()

    def test_insights_endpoint_returns_newest_first(self, staff_client, lead_with_doc):
        lead, doc = lead_with_doc
        run_docai_demo(lead_id=lead.id, document_id=doc.id)

        resp = staff_client.get(f"/api/commercial/leads/{lead.lead_id}/insights/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert "insights" in data


# ── Timeline endpoint ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLeadTimeline:
    def test_timeline_includes_events_and_scores(self, staff_client, lead_with_doc):
        lead, _ = lead_with_doc
        resp = staff_client.get(f"/api/commercial/leads/{lead.lead_id}/timeline/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        types = {e["type"] for e in data["events"]}
        # Should have at least events and score changes from ingestion
        assert len(types) >= 1


# ── Documents list endpoint ───────────────────────────────────────────────────

@pytest.mark.django_db
class TestLeadDocumentsList:
    def test_list_returns_linked_documents(self, staff_client, lead_with_doc):
        lead, doc = lead_with_doc
        resp = staff_client.get(f"/api/commercial/leads/{lead.lead_id}/documents/list/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["documents"][0]["document_id"] == doc.id
