from django.conf import settings
from django.db import models

from companies.models import Company


class UserProfile(models.Model):
    class NotificationPreference(models.TextChoices):
        EMAIL = "email", "Apenas Email"
        WHATSAPP = "whatsapp", "Apenas WhatsApp"
        BOTH = "both", "Email e WhatsApp"
        NONE = "none", "Nenhum"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True)

    # Contact info
    phone = models.CharField(
        max_length=20, blank=True,
        help_text="Telefone para WhatsApp (com DDD)"
    )

    # Notification preferences
    notification_preference = models.CharField(
        max_length=10,
        choices=NotificationPreference.choices,
        default=NotificationPreference.EMAIL
    )
    notify_expiration_days = models.PositiveIntegerField(
        default=7,
        help_text="Dias antes do vencimento para notificar"
    )

    def __str__(self):
        return f"Profile for {self.user.username}"

    @property
    def should_notify_email(self):
        return self.notification_preference in [
            self.NotificationPreference.EMAIL,
            self.NotificationPreference.BOTH
        ]

    @property
    def should_notify_whatsapp(self):
        return self.notification_preference in [
            self.NotificationPreference.WHATSAPP,
            self.NotificationPreference.BOTH
        ] and self.phone
