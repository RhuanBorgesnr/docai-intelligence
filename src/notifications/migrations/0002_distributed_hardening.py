from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.AddField(model_name="notification", name="notification_id", field=models.CharField(blank=True, max_length=128, null=True, unique=True)),
        migrations.AddField(model_name="notification", name="tenant_id", field=models.CharField(default="default", max_length=100)),
        migrations.AddField(model_name="notification", name="subject", field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name="notification", name="correlation_id", field=models.CharField(blank=True, db_index=True, max_length=100)),
        migrations.AddField(model_name="notification", name="trace_id", field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name="notification", name="causation_id", field=models.CharField(blank=True, max_length=128)),
        migrations.AddField(model_name="notification", name="template_name", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="notification", name="context", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="notification", name="max_retries", field=models.PositiveIntegerField(default=3)),
        migrations.AddField(model_name="notification", name="next_attempt_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="notification", name="provider_response", field=models.JSONField(blank=True, default=dict)),
        migrations.AlterField(model_name="notification", name="status", field=models.CharField(choices=[("pending", "Pending"), ("dispatching", "Dispatching"), ("sent", "Sent"), ("failed", "Failed"), ("failed_fallback", "Failed Fallback")], default="pending", max_length=20)),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["status", "next_attempt_at"], name="notification_status_next_attempt_idx")),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["tenant_id", "status"], name="notification_tenant_status_idx")),
    ]
