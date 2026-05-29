from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("approvals", "0001_initial"),
    ]

    operations = [
        migrations.AddField(model_name="approval", name="approval_fields", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="approval", name="approvers", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="approval", name="causation_id", field=models.CharField(blank=True, max_length=128)),
        migrations.AddField(model_name="approval", name="correlation_id", field=models.CharField(blank=True, db_index=True, max_length=100)),
        migrations.AddField(model_name="approval", name="decision_comment", field=models.TextField(blank=True)),
        migrations.AddField(model_name="approval", name="escalated_to", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="approval", name="escalation_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="approval", name="escalation_reason", field=models.TextField(blank=True)),
        migrations.AddField(model_name="approval", name="lease_expires_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="approval", name="policy_snapshot", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="approval", name="tenant_id", field=models.CharField(default="default", max_length=100)),
        migrations.AddField(model_name="approval", name="trace_id", field=models.CharField(blank=True, max_length=100)),
        migrations.AlterField(model_name="approval", name="status", field=models.CharField(choices=[("pending", "Pending"), ("escalated", "Escalated"), ("approved", "Approved"), ("rejected", "Rejected"), ("changes_requested", "Changes Requested"), ("expired", "Expired"), ("cancelled", "Cancelled")], default="pending", max_length=20)),
        migrations.AddIndex(model_name="approval", index=models.Index(fields=["status", "deadline_at"], name="approval_status_deadline_idx")),
        migrations.AddIndex(model_name="approval", index=models.Index(fields=["tenant_id", "status"], name="approval_tenant_status_idx")),
        migrations.AddIndex(model_name="approval", index=models.Index(fields=["correlation_id"], name="approval_correlation_idx")),
    ]
