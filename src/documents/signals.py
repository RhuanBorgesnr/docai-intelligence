"""
Document app signals.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Document
from .tasks import process_document


@receiver(post_save, sender=Document)
def trigger_document_processing(sender, instance, created, **kwargs):
    """Start async processing when a new document is saved with a file."""
    if created and instance.file:
        process_document.delay(instance.pk)
