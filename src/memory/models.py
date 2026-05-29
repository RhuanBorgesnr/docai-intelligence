"""Shared memory snapshots for workflows."""
from django.db import models


class MemorySnapshot(models.Model):
    """Stores workflow context snapshots after important transitions."""

    case = models.ForeignKey("orchestrator.Case", on_delete=models.CASCADE, related_name="memory_snapshots")
    state = models.CharField(max_length=50)
    summary = models.TextField(blank=True)
    facts = models.JSONField(default=list, blank=True)
    open_questions = models.JSONField(default=list, blank=True)
    pending_approvals = models.JSONField(default=list, blank=True)
    snapshot_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["case", "created_at"])]

    def __str__(self) -> str:
        return f"MemorySnapshot {self.id} case={self.case_id}"
