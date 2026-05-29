"""
Sprint 2.5 — runtime protection models.

New models:
- CircuitBreakerState
- RateLimitBucket
- InFlightRecord
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agent_runtime", "0002_distributed_hardening"),
    ]

    operations = [
        # ── CircuitBreakerState ───────────────────────────────────────────────
        migrations.CreateModel(
            name="CircuitBreakerState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("resource_key", models.CharField(max_length=200, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("closed", "Closed"),
                            ("open", "Open"),
                            ("half_open", "Half-Open"),
                        ],
                        default="closed",
                        max_length=20,
                    ),
                ),
                ("failure_count", models.PositiveIntegerField(default=0)),
                ("success_count", models.PositiveIntegerField(default=0)),
                ("failure_threshold", models.PositiveIntegerField(default=5)),
                ("success_threshold", models.PositiveIntegerField(default=2)),
                ("last_failure_at", models.DateTimeField(blank=True, null=True)),
                ("opened_at", models.DateTimeField(blank=True, null=True)),
                ("reset_timeout_seconds", models.PositiveIntegerField(default=60)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"app_label": "agent_runtime"},
        ),
        # ── RateLimitBucket ───────────────────────────────────────────────────
        migrations.CreateModel(
            name="RateLimitBucket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("resource_key", models.CharField(max_length=200)),
                ("window_start", models.DateTimeField()),
                ("window_seconds", models.PositiveIntegerField(default=60)),
                ("capacity", models.PositiveIntegerField(default=100)),
                ("tokens_used", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"app_label": "agent_runtime"},
        ),
        migrations.AddConstraint(
            model_name="ratelimitbucket",
            constraint=models.UniqueConstraint(
                fields=["resource_key", "window_start"], name="uniq_rate_limit_bucket"
            ),
        ),
        migrations.AddIndex(
            model_name="ratelimitbucket",
            index=models.Index(
                fields=["resource_key", "window_start"], name="rate_limit_window_idx"
            ),
        ),
        # ── InFlightRecord ────────────────────────────────────────────────────
        migrations.CreateModel(
            name="InFlightRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("resource_key", models.CharField(max_length=200, db_index=True)),
                ("item_id", models.CharField(max_length=200)),
                ("leased_until", models.DateTimeField()),
                ("worker_id", models.CharField(blank=True, max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"app_label": "agent_runtime"},
        ),
        migrations.AddConstraint(
            model_name="inflightrecord",
            constraint=models.UniqueConstraint(
                fields=["resource_key", "item_id"], name="uniq_inflight"
            ),
        ),
        migrations.AddIndex(
            model_name="inflightrecord",
            index=models.Index(
                fields=["resource_key", "leased_until"], name="inflight_lease_idx"
            ),
        ),
    ]
