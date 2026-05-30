"""
Admin — Notificações e Saúde dos Providers.
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import Notification, NotificationDeliveryAttempt, NotificationProviderHealth


class DeliveryAttemptInline(admin.TabularInline):
    model = NotificationDeliveryAttempt
    extra = 0
    readonly_fields = ("attempt_number", "channel", "recipient", "outcome", "error", "duration_ms", "started_at", "finished_at")
    can_delete = False
    ordering = ("attempt_number",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("notification_id_short", "canal", "recipient_short", "status_badge", "prioridade", "tentativas", "created_at")
    list_filter = ("status", "channel", "priority", "is_dead", "tenant_id")
    search_fields = ("notification_id", "recipient", "subject", "correlation_id", "trace_id")
    readonly_fields = (
        "notification_id", "context", "provider_response",
        "created_at", "sent_at", "updated_at"
    )
    raw_id_fields = ("case",)
    date_hierarchy = "created_at"
    inlines = [DeliveryAttemptInline]

    @admin.display(description="ID")
    def notification_id_short(self, obj):
        return obj.notification_id[:12] + "..."

    @admin.display(description="Canal")
    def canal(self, obj):
        return obj.get_channel_display()

    @admin.display(description="Destinatário")
    def recipient_short(self, obj):
        return obj.recipient[:30] + "..." if len(obj.recipient) > 30 else obj.recipient

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {"pending": "orange", "sending": "blue", "sent": "green", "delivered": "green", "failed": "red", "dead": "darkred"}
        color = colors.get(obj.status, "gray")
        label = "☠️ Dead" if obj.is_dead else obj.get_status_display()
        return format_html('<span style="color: {};">{}</span>', color, label)

    @admin.display(description="Prioridade")
    def prioridade(self, obj):
        return obj.get_priority_display()

    @admin.display(description="Tentativas")
    def tentativas(self, obj):
        return f"{obj.attempts}/{obj.max_retries}"


@admin.register(NotificationDeliveryAttempt)
class NotificationDeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = ("notification", "attempt_number", "channel", "resultado", "duration_ms", "started_at")
    list_filter = ("outcome", "channel")
    search_fields = ("notification__notification_id",)
    readonly_fields = ("provider_response", "started_at", "finished_at")

    @admin.display(description="Resultado")
    def resultado(self, obj):
        colors = {"success": "green", "failed": "red", "timeout": "orange"}
        color = colors.get(obj.outcome, "gray")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_outcome_display())


@admin.register(NotificationProviderHealth)
class NotificationProviderHealthAdmin(admin.ModelAdmin):
    list_display = ("channel", "status_circuito", "failure_count", "success_count", "last_failure_at", "last_success_at")
    list_filter = ("is_open", "channel")
    readonly_fields = ("updated_at",)

    @admin.display(description="Circuit Breaker")
    def status_circuito(self, obj):
        if obj.is_open:
            return format_html('<span style="color: red; font-weight: bold;">⚠️ ABERTO</span>')
        return format_html('<span style="color: green;">✓ Fechado</span>')
