"""
Asynchronous document processing pipeline tasks.
"""
import logging

from celery import shared_task
from django.db import transaction

from ai.chunking import chunk_text
from ai.embeddings import generate_embedding
from ai.extraction import extract_text_from_pdf
from ai.financial_extraction import extract_financial_indicators
from ai.clause_extraction import extract_contract_clauses
from ai.extraction import extract_document_data
from documents.models import Document, DocumentChunk, FinancialIndicator, ContractClause

logger = logging.getLogger(__name__)

# Document types that should trigger financial extraction
FINANCIAL_DOC_TYPES = {Document.DocumentType.DRE, Document.DocumentType.BALANCE}
# Document types that should trigger clause extraction
CONTRACT_DOC_TYPES = {Document.DocumentType.CONTRACT}
# Document types that should trigger metadata extraction
METADATA_DOC_TYPES = {
    Document.DocumentType.INVOICE,
    Document.DocumentType.CERTIFICATE,
    Document.DocumentType.REPORT,
    Document.DocumentType.BALANCE,  # Balance also extracts specific metadata
}


@shared_task
def process_document(document_id: int) -> None:
    """
    Process document asynchronously: extract PDF text, chunk, generate embeddings.
    For financial documents (DRE, Balance), also extract financial indicators.
    For contracts, extract important clauses.

    Args:
        document_id: Primary key of the Document to process.
    """
    document = Document.objects.get(pk=document_id)
    company_id = document.company_id

    def _broadcast(status, detail=None):
        """Broadcast processing status via WebSocket."""
        try:
            from orchestrator.ws_broadcasts import sync_broadcast_document_status
            if company_id:
                sync_broadcast_document_status(company_id, document_id, status, detail)
        except Exception:
            pass  # Non-critical, don't fail processing

    try:
        document.processing_status = Document.ProcessingStatus.PROCESSING
        document.save(update_fields=["processing_status"])
        _broadcast("extracting_text", {"step": 1, "total_steps": 4, "message": "Extraindo texto do documento..."})

        extracted_text = extract_text_from_pdf(document.file.path)
        document.extracted_text = extracted_text
        document.save(update_fields=["extracted_text"])
        _broadcast("chunking", {"step": 2, "total_steps": 4, "message": "Segmentando conteúdo..."})

        chunks = chunk_text(extracted_text)
        total_tokens = sum(c.token_count for c in chunks)
        _broadcast("embedding", {"step": 3, "total_steps": 4, "message": "Gerando embeddings para busca semântica...", "chunks": len(chunks)})

        with transaction.atomic():
            DocumentChunk.objects.filter(document=document).delete()

            for chunk in chunks:
                embedding = generate_embedding(chunk.content)
                DocumentChunk.objects.create(
                    document=document,
                    content=chunk.content,
                    embedding=embedding,
                    chunk_index=chunk.chunk_index,
                    token_count=chunk.token_count,
                )

        # Extract financial indicators for DRE/Balance documents
        if document.document_type in FINANCIAL_DOC_TYPES:
            _broadcast("analyzing_financial", {"step": 4, "total_steps": 4, "message": "Extraindo indicadores financeiros com IA..."})
            extract_and_save_indicators.delay(document_id)

        # Extract clauses for Contract documents
        if document.document_type in CONTRACT_DOC_TYPES:
            _broadcast("analyzing_clauses", {"step": 4, "total_steps": 4, "message": "Identificando cláusulas e riscos..."})
            extract_and_save_clauses.delay(document_id)

        # Extract metadata for Invoice, Certificate, Report documents
        if document.document_type in METADATA_DOC_TYPES:
            _broadcast("extracting_metadata", {"step": 4, "total_steps": 4, "message": "Extraindo metadados..."})
            extract_and_save_metadata.delay(document_id)

        document.total_tokens = total_tokens
        document.processing_status = Document.ProcessingStatus.COMPLETED
        document.save(update_fields=["total_tokens", "processing_status"])
        _broadcast("completed", {"message": "Documento processado com sucesso!", "tokens": total_tokens, "chunks": len(chunks)})

    except Exception:
        logger.exception("Document processing failed: document_id=%s", document_id)
        document.processing_status = Document.ProcessingStatus.FAILED
        document.save(update_fields=["processing_status"])
        _broadcast("failed", {"message": "Falha no processamento. Tente novamente."})


@shared_task
def extract_and_save_indicators(document_id: int) -> dict:
    """
    Extract financial indicators from a document and save to database.

    Args:
        document_id: Primary key of the Document to process.

    Returns:
        Dict with extraction results.
    """
    document = Document.objects.get(pk=document_id)

    if not document.extracted_text:
        logger.warning("Document %s has no extracted text", document_id)
        return {"status": "error", "message": "No extracted text"}

    indicators = extract_financial_indicators(document.extracted_text)

    if not indicators:
        logger.info("No financial indicators found in document %s", document_id)
        return {"status": "ok", "indicators_count": 0}

    # Save indicators to database
    period = document.reference_date

    with transaction.atomic():
        # Remove old indicators for this document/period
        FinancialIndicator.objects.filter(document=document, period=period).delete()

        for indicator_type, value in indicators.items():
            FinancialIndicator.objects.create(
                document=document,
                indicator_type=indicator_type,
                value=value,
                period=period
            )

    logger.info("Saved %d financial indicators for document %s", len(indicators), document_id)
    return {"status": "ok", "indicators_count": len(indicators), "indicators": list(indicators.keys())}


@shared_task
def check_expiring_documents(days_ahead: int = 7) -> dict:
    """
    Check for documents expiring within the next N days.

    Args:
        days_ahead: Number of days to look ahead for expiring documents.

    Returns:
        Dict with count and list of expiring document IDs per company.
    """
    from datetime import date, timedelta

    today = date.today()
    expiration_threshold = today + timedelta(days=days_ahead)

    expiring_docs = Document.objects.filter(
        expiration_date__isnull=False,
        expiration_date__lte=expiration_threshold,
        expiration_date__gte=today
    ).select_related('company')

    results = {}
    for doc in expiring_docs:
        company_name = doc.company.name if doc.company else "Sem empresa"
        if company_name not in results:
            results[company_name] = []

        days_left = (doc.expiration_date - today).days
        results[company_name].append({
            "document_id": doc.id,
            "title": doc.title or doc.file.name,
            "expiration_date": str(doc.expiration_date),
            "days_left": days_left,
        })

    total_count = sum(len(docs) for docs in results.values())
    logger.info("Found %d documents expiring within %d days", total_count, days_ahead)

    return {
        "total_count": total_count,
        "by_company": results
    }


@shared_task
def send_expiration_notifications(days_ahead: int = 7) -> dict:
    """
    Send email and WhatsApp notifications for documents expiring within the next N days.

    Groups documents by company and sends notifications based on user preferences.

    Args:
        days_ahead: Number of days to look ahead for expiring documents.

    Returns:
        Dict with notification results.
    """
    from datetime import date, timedelta
    from collections import defaultdict
    from accounts.models import UserProfile
    from documents.notifications import send_expiration_email, send_batch_expiration_email
    from documents.whatsapp import (
        send_expiration_whatsapp, send_batch_expiration_whatsapp, is_whatsapp_enabled
    )

    today = date.today()
    expiration_threshold = today + timedelta(days=days_ahead)

    # Get expiring documents
    expiring_docs = Document.objects.filter(
        expiration_date__isnull=False,
        expiration_date__lte=expiration_threshold,
        expiration_date__gte=today - timedelta(days=1)  # Include recently expired
    ).select_related('company').order_by('expiration_date')

    if not expiring_docs.exists():
        logger.info("No expiring documents found")
        return {"status": "ok", "emails_sent": 0, "whatsapp_sent": 0}

    # Group by company
    docs_by_company = defaultdict(list)
    for doc in expiring_docs:
        company_id = doc.company_id if doc.company else None
        docs_by_company[company_id].append(doc)

    emails_sent = 0
    whatsapp_sent = 0
    errors = []

    for company_id, docs in docs_by_company.items():
        if not company_id:
            continue

        # Get company users
        users = UserProfile.objects.filter(
            company_id=company_id
        ).select_related('user', 'company')

        for profile in users:
            email = profile.user.email
            phone = profile.phone
            company_name = profile.company.name if profile.company else ''

            # Send email if enabled
            if profile.should_notify_email and email:
                try:
                    if len(docs) == 1:
                        doc = docs[0]
                        days = (doc.expiration_date - today).days
                        success = send_expiration_email(doc, email, days, company_name)
                    else:
                        success = send_batch_expiration_email(docs, email, company_name)

                    if success:
                        emails_sent += 1
                except Exception as e:
                    logger.exception("Error sending email to %s: %s", email, e)
                    errors.append({"type": "email", "to": email, "error": str(e)})

            # Send WhatsApp if enabled
            if profile.should_notify_whatsapp and phone and is_whatsapp_enabled():
                try:
                    if len(docs) == 1:
                        doc = docs[0]
                        days = (doc.expiration_date - today).days
                        doc_title = doc.title or doc.file.name.split('/')[-1]
                        success = send_expiration_whatsapp(
                            phone, doc_title, days, doc.expiration_date, company_name
                        )
                    else:
                        docs_data = [
                            {
                                "title": d.title or d.file.name.split('/')[-1],
                                "expiration_date": d.expiration_date.strftime('%d/%m/%Y'),
                                "days_left": (d.expiration_date - today).days
                            }
                            for d in docs
                        ]
                        success = send_batch_expiration_whatsapp(phone, docs_data, company_name)

                    if success:
                        whatsapp_sent += 1
                except Exception as e:
                    logger.exception("Error sending WhatsApp to %s: %s", phone, e)
                    errors.append({"type": "whatsapp", "to": phone, "error": str(e)})

    logger.info("Sent %d emails and %d WhatsApp notifications", emails_sent, whatsapp_sent)

    return {
        "status": "ok",
        "emails_sent": emails_sent,
        "whatsapp_sent": whatsapp_sent,
        "documents_checked": expiring_docs.count(),
        "errors": errors if errors else None
    }


@shared_task
def extract_and_save_clauses(document_id: int) -> dict:
    """
    Extract contract clauses from a document and save to database.

    Args:
        document_id: Primary key of the Document to process.

    Returns:
        Dict with extraction results.
    """
    document = Document.objects.get(pk=document_id)

    if not document.extracted_text:
        logger.warning("Document %s has no extracted text", document_id)
        return {"status": "error", "message": "No extracted text"}

    clauses = extract_contract_clauses(document.extracted_text)

    if not clauses:
        logger.info("No contract clauses found in document %s", document_id)
        return {"status": "ok", "clauses_count": 0}

    with transaction.atomic():
        # Remove old clauses for this document
        ContractClause.objects.filter(document=document).delete()

        for clause in clauses:
            ContractClause.objects.create(
                document=document,
                clause_type=clause['clause_type'],
                title=clause['title'],
                content=clause['content'],
                summary=clause.get('summary', ''),
                risk_level=clause['risk_level'],
                extracted_value=clause.get('extracted_value', '')
            )

    logger.info("Saved %d contract clauses for document %s", len(clauses), document_id)
    return {"status": "ok", "clauses_count": len(clauses)}


@shared_task
def extract_and_save_metadata(document_id: int) -> dict:
    """
    Extract metadata from documents (Invoice, Certificate, Report, Balance).
    Saves extracted data to the document's extracted_metadata JSON field.

    Args:
        document_id: Primary key of the Document to process.

    Returns:
        Dict with extraction results.
    """
    document = Document.objects.get(pk=document_id)

    if not document.extracted_text:
        logger.warning("Document %s has no extracted text", document_id)
        return {"status": "error", "message": "No extracted text"}

    # Map document types to extractor names
    type_mapping = {
        Document.DocumentType.INVOICE: "invoice",
        Document.DocumentType.CERTIFICATE: "certificate",
        Document.DocumentType.REPORT: "report",
        Document.DocumentType.BALANCE: "balance",
    }

    extractor_type = type_mapping.get(document.document_type)
    if not extractor_type:
        logger.warning("No extractor for document type %s", document.document_type)
        return {"status": "error", "message": "No extractor for this type"}

    metadata = extract_document_data(document.extracted_text, extractor_type)

    if not metadata:
        logger.info("No metadata extracted from document %s", document_id)
        return {"status": "ok", "fields_count": 0}

    # Convert date objects to strings for JSON serialization
    from decimal import Decimal
    for key, value in metadata.items():
        if hasattr(value, 'isoformat'):
            metadata[key] = value.isoformat()
        elif isinstance(value, Decimal):
            metadata[key] = float(value)
        elif isinstance(value, dict):
            for k, v in value.items():
                if hasattr(v, 'isoformat'):
                    value[k] = v.isoformat()
                elif isinstance(v, Decimal):
                    value[k] = float(v)

    # Save to document
    document.extracted_metadata = metadata

    # Auto-fill expiration date for certificates
    if extractor_type == "certificate" and metadata.get("data_validade"):
        from datetime import datetime
        try:
            if isinstance(metadata["data_validade"], str):
                document.expiration_date = datetime.fromisoformat(metadata["data_validade"]).date()
        except (ValueError, TypeError):
            pass

    document.save(update_fields=["extracted_metadata", "expiration_date"])

    logger.info("Saved metadata with %d fields for document %s", len(metadata), document_id)

    # --- ERP Auto-Sync Hook ---
    # If it's an invoice and the tenant has an active ERP connection with auto_sync,
    # trigger automatic sync to ERP (creates Conta a Pagar)
    if extractor_type == "invoice" and metadata:
        _trigger_erp_sync_if_configured(document, metadata)

    return {"status": "ok", "fields_count": len(metadata), "fields": list(metadata.keys())}


def _trigger_erp_sync_if_configured(document, metadata: dict):
    """
    Check if tenant has an active ERP connection with auto_sync enabled.
    If yes, dispatch async sync task for the extracted invoice.
    """
    try:
        from integrations.models import ERPConnection
        from integrations.tasks import task_sync_conta_pagar

        # Find active connections with auto_sync for this tenant
        tenant_id = getattr(document, 'tenant_id', None) or 'docai_internal'
        connections = ERPConnection.objects.filter(
            is_active=True,
            is_circuit_open=False,
            auto_sync=True,
        )

        if not connections.exists():
            return

        for conn in connections:
            # Dispatch async sync (will go through approval if requires_approval=True)
            extracted_data = {
                'document_id': str(document.pk),
                'numero_nf': metadata.get('numero_nf', ''),
                'cnpj_emitente': metadata.get('cnpj_emitente', ''),
                'razao_social_emitente': metadata.get('razao_social_emitente', ''),
                'data_emissao': metadata.get('data_emissao', ''),
                'data_vencimento': metadata.get('data_vencimento', metadata.get('data_emissao', '')),
                'valor_total': metadata.get('valor_total', 0),
                'descricao': f"NF {metadata.get('numero_nf', '')} - Doc #{document.pk}",
            }
            task_sync_conta_pagar.delay(
                connection_id=str(conn.id),
                extracted_data=extracted_data,
                correlation_id=f"doc_{document.pk}",
            )
            logger.info(
                "ERP sync dispatched: document %s → connection %s",
                document.pk, conn.name,
            )
    except Exception as e:
        # Never break document processing because of ERP sync failure
        logger.warning("ERP auto-sync hook failed (non-critical): %s", str(e))
