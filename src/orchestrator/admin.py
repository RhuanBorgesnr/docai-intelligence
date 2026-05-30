"""
Admin — Orquestrador (Cases, Eventos, Tarefas, Outbox/Inbox, DLQ).
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import Case, CaseEvent, CaseTask, DLQEvent, EventInbox, EventOutbox


class CaseEventInline(admin.TabularInline):
    model = CaseEvent
    extra = 0
    readonly_fields = ("event_id", "event_type", "source", "priority", "occurred_at", "created_at")
    fields = ("event_type", "source", "priority", "occurred_at")
    can_delete = False
    max_num = 20
    ordering = ("-occurred_at",)


class CaseTaskInline(admin.TabularInline):
    model = CaseTask
    extra = 0
    fields = ("title", "assignee_agent", "is_completed", "due_at")


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "estado", "workflow_badge", "prioridade", "tenant_id", "created_at")
    list_filter = ("state", "workflow_status", "priority", "tenant_id")
    search_fields = ("title", "external_ref", "correlation_id", "trace_id")
    readonly_fields = ("correlation_id", "trace_id", "created_at", "updated_at")
    inlines = [CaseTaskInline, CaseEventInline]
    date_hierarchy = "created_at"

    @admin.display(description="Estado")
    def estado(self, obj):
        return obj.get_state_display()

    @admin.display(description="Workflow")
    def workflow_badge(self, obj):
        colors = {"active": "green", "paused": "orange", "completed": "blue", "cancelled": "red"}
        color = colors.get(obj.workflow_status, "gray")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_workflow_status_display())

    @admin.display(description="Prioridade")
    def prioridade(self, obj):
        colors = {"critical": "red", "high": "orange", "medium": "blue", "low": "gray"}
        color = colors.get(obj.priority, "gray")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_priority_display())


@admin.register(CaseEvent)
class CaseEventAdmin(admin.ModelAdmin):
    list_display = ("event_id_short", "case", "event_type", "source", "priority", "occurred_at")
    list_filter = ("event_type", "priority", "source")
    search_fields = ("event_id", "case__title", "correlation_id", "trace_id")
    readonly_fields = ("event_id", "payload", "meta", "created_at")
    raw_id_fields = ("case",)
    date_hierarchy = "occurred_at"

    @admin.display(description="Evento")
    def event_id_short(self, obj):
        return obj.event_id[:12] + "..." if len(obj.event_id) > 12 else obj.event_id


@admin.register(CaseTask)
class CaseTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "case", "assignee_agent", "concluida", "due_at", "created_at")
    list_filter = ("is_completed", "assignee_agent")
    search_fields = ("title", "case__title")
    raw_id_fields = ("case",)

    @admin.display(description="Concluída", boolean=True)
    def concluida(self, obj):
        return obj.is_completed


@admin.register(DLQEvent)
class DLQEventAdmin(admin.ModelAdmin):
    list_display = ("case", "reason_code", "attempts", "replayable", "created_at")
    list_filter = ("reason_code", "replayable")
    search_fields = ("error_message", "trace_id", "case__title")
    readonly_fields = ("payload", "created_at")
    raw_id_fields = ("case", "original_event")


@admin.register(EventOutbox)
class EventOutboxAdmin(admin.ModelAdmin):
    list_display = ("event_id_short", "event_type", "status_badge", "tenant_id", "attempts", "created_at")
    list_filter = ("status", "event_type", "tenant_id")
    search_fields = ("event_id", "correlation_id", "trace_id")
    readonly_fields = ("payload", "meta", "created_at", "updated_at", "published_at")
    date_hierarchy = "created_at"

    @admin.display(description="ID")
    def event_id_short(self, obj):
        return obj.event_id[:12] + "..."

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {"pending": "orange", "published": "green", "failed": "red"}
        color = colors.get(obj.status, "gray")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_status_display())


@admin.register(EventInbox)
class EventInboxAdmin(admin.ModelAdmin):
    list_display = ("consumer", "event_id_short", "event_type", "tenant_id", "processed_at")
    list_filter = ("consumer", "event_type", "tenant_id")
    search_fields = ("event_id", "correlation_id", "trace_id")
    readonly_fields = ("processed_at",)

    @admin.display(description="Evento")
    def event_id_short(self, obj):
        return obj.event_id[:12] + "..."
