from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("orchestrator", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EventInbox",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("consumer", models.CharField(max_length=120)),
                ("event_id", models.CharField(max_length=128)),
                ("event_type", models.CharField(max_length=120)),
                ("tenant_id", models.CharField(default="default", max_length=100)),
                ("correlation_id", models.CharField(blank=True, max_length=100)),
                ("trace_id", models.CharField(blank=True, max_length=100)),
                ("payload_hash", models.CharField(blank=True, max_length=64)),
                ("processed_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["tenant_id", "processed_at"], name="orch_evtin_tenant_processed_idx"),
                    models.Index(fields=["event_type"], name="orch_evtin_event_type_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("consumer", "event_id"), name="uniq_event_inbox_consumer_event"),
                ],
            },
        ),
        migrations.CreateModel(
            name="EventOutbox",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.CharField(max_length=128, unique=True)),
                ("event_type", models.CharField(max_length=120)),
                ("event_version", models.CharField(default="1.0", max_length=20)),
                ("source", models.CharField(max_length=120)),
                ("tenant_id", models.CharField(default="default", max_length=100)),
                ("correlation_id", models.CharField(db_index=True, max_length=100)),
                ("trace_id", models.CharField(blank=True, max_length=100)),
                ("causation_id", models.CharField(blank=True, max_length=128)),
                ("payload", models.JSONField(default=dict)),
                ("meta", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("published", "Published"), ("failed", "Failed"), ("dead", "Dead")], default="pending", max_length=20)),
                ("available_at", models.DateTimeField(auto_now_add=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("case", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="outbox_events", to="orchestrator.case")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["status", "available_at"], name="orch_outbox_status_available_idx"),
                    models.Index(fields=["tenant_id", "status"], name="orch_outbox_tenant_status_idx"),
                    models.Index(fields=["correlation_id"], name="orch_outbox_correlation_idx"),
                ],
            },
        ),
    ]
