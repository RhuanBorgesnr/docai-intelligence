from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    """Documents application configuration."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'documents'
    verbose_name = 'Documents'

    def ready(self):
        import documents.signals
