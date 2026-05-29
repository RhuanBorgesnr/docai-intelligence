"""Audit log models."""
from django.db import models


class AuditLog(models.Model):
    """Append-only audit trail for orchestration actions."""

    case = models.ForeignKey(
        "orchestrator.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=120)
    actor_type = models.CharField(max_length=50, default="system")
    actor_id = models.CharField(max_length=120, blank=True)
    trace_id = models.CharField(max_length=100, blank=True)
    correlation_id = models.CharField(max_length=100, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["case", "created_at"]),
            models.Index(fields=["trace_id"]),
        ]
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("AuditLog is append-only and cannot be updated")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"AuditLog {self.action}"
