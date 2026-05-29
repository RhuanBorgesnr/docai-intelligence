"""
Sprint 2.5 — durable notification pipeline.

Changes:
- Notification: add fallback_channel, idempotency_key, leased_until, is_dead,
  priority, updated_at; make notification_id non-nullable; add indexes.
- New: NotificationDeliveryAttempt (delivery audit trail)
- New: NotificationProviderHealth (channel circuit-breaker state)
"""
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0002_distributed_hardening"),
    ]

    operations = [
        # ── Notification: add missing durable fields ──────────────────────────
        migrations.AddField(
            model_name="notification",
            name="fallback_channel",
            field=models.CharField(blank=True, max_length=20, default=""),
        ),
        # Fill in any NULL notification_id values before making the column non-nullable.
        # Uses portable SQL (works on both PostgreSQL and SQLite).
        migrations.RunSQL(
            sql="UPDATE notifications_notification SET notification_id = 'auto-' || CAST(id AS TEXT) WHERE notification_id IS NULL",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name="notification",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=128, default="", db_index=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="leased_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="is_dead",
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="priority",
            field=models.CharField(
                choices=[
                    ("critical", "Critical"),
                    ("high", "High"),
                    ("normal", "Normal"),
                    ("low", "Low"),
                ],
                default="normal",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        # Add webhook / log to channel choices (AlterField for completeness)
        migrations.AlterField(
            model_name="notification",
            name="channel",
            field=models.CharField(
                choices=[
                    ("whatsapp", "WhatsApp"),
                    ("telegram", "Telegram"),
                    ("email", "Email"),
                    ("webhook", "Webhook"),
                    ("panel", "Panel"),
                    ("log", "Log"),
                ],
                max_length=20,
            ),
        ),
        # Make notification_id non-nullable with unique constraint preserved
        migrations.AlterField(
            model_name="notification",
            name="notification_id",
            field=models.CharField(max_length=128, unique=True),
        ),
        # Extra indexes
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["is_dead", "status"], name="notif_dead_status_idx"),
        ),
        # ── NotificationDeliveryAttempt ───────────────────────────────────────
        migrations.CreateModel(
            name="NotificationDeliveryAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                (
                    "notification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="delivery_attempts",
                        to="notifications.notification",
                    ),
                ),
                ("attempt_number", models.PositiveIntegerField()),
                ("channel", models.CharField(max_length=20)),
                ("recipient", models.CharField(max_length=255)),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("success", "Success"),
                            ("failure", "Failure"),
                            ("fallback_success", "Fallback Success"),
                        ],
                        max_length=20,
                    ),
                ),
                ("error", models.TextField(blank=True)),
                ("provider_response", models.JSONField(default=dict, blank=True)),
                ("duration_ms", models.FloatField(default=0.0)),
                ("started_at", models.DateTimeField()),
                ("finished_at", models.DateTimeField()),
            ],
            options={"indexes": [models.Index(fields=["notification", "attempt_number"], name="notif_attempt_idx")]},
        ),
        # ── NotificationProviderHealth ────────────────────────────────────────
        migrations.CreateModel(
            name="NotificationProviderHealth",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("channel", models.CharField(max_length=20, unique=True)),
                ("is_open", models.BooleanField(default=False)),
                ("failure_count", models.PositiveIntegerField(default=0)),
                ("success_count", models.PositiveIntegerField(default=0)),
                ("last_failure_at", models.DateTimeField(blank=True, null=True)),
                ("last_success_at", models.DateTimeField(blank=True, null=True)),
                ("opened_at", models.DateTimeField(blank=True, null=True)),
                ("reset_after_seconds", models.PositiveIntegerField(default=60)),
                ("failure_threshold", models.PositiveIntegerField(default=5)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"indexes": [models.Index(fields=["channel", "is_open"], name="provider_health_idx")]},
        ),
    ]
