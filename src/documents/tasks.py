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
from documents.models import Document, DocumentChunk, FinancialIndicator, ContractClause

logger = logging.getLogger(__name__)

# Document types that should trigger financial extraction
FINANCIAL_DOC_TYPES = {Document.DocumentType.DRE, Document.DocumentType.BALANCE}
# Document types that should trigger clause extraction
CONTRACT_DOC_TYPES = {Document.DocumentType.CONTRACT}


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

    try:
        document.processing_status = Document.ProcessingStatus.PROCESSING
        document.save(update_fields=["processing_status"])

        extracted_text = extract_text_from_pdf(document.file.path)
        document.extracted_text = extracted_text
        document.save(update_fields=["extracted_text"])

        chunks = chunk_text(extracted_text)
        total_tokens = sum(c.token_count for c in chunks)

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
            logger.info("Extracting financial indicators for document %s", document_id)
            extract_and_save_indicators.delay(document_id)

        # Extract clauses for Contract documents
        if document.document_type in CONTRACT_DOC_TYPES:
            logger.info("Extracting contract clauses for document %s", document_id)
            extract_and_save_clauses.delay(document_id)

        document.total_tokens = total_tokens
        document.processing_status = Document.ProcessingStatus.COMPLETED
        document.save(update_fields=["total_tokens", "processing_status"])

    except Exception:
        logger.exception("Document processing failed: document_id=%s", document_id)
        document.processing_status = Document.ProcessingStatus.FAILED
        document.save(update_fields=["processing_status"])


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
