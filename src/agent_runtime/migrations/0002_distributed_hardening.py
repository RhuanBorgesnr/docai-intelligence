from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orchestrator", "0002_distributed_hardening"),
        ("agent_runtime", "0001_initial"),
    ]

    operations = [
        migrations.AddField(model_name="agentcommand", name="available_at", field=models.DateTimeField(auto_now_add=True), preserve_default=False),
        migrations.AddField(model_name="agentcommand", name="causation_id", field=models.CharField(blank=True, max_length=128)),
        migrations.AddField(model_name="agentcommand", name="completed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="agentcommand", name="contract_version", field=models.CharField(default="1.0", max_length=20)),
        migrations.AddField(model_name="agentcommand", name="hop_count", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="agentcommand", name="idempotency_key", field=models.CharField(blank=True, db_index=True, max_length=128)),
        migrations.AddField(model_name="agentcommand", name="last_error", field=models.TextField(blank=True)),
        migrations.AddField(model_name="agentcommand", name="leased_until", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="agentcommand", name="loop_signature", field=models.CharField(blank=True, db_index=True, max_length=128)),
        migrations.AddField(model_name="agentcommand", name="max_retries", field=models.PositiveIntegerField(default=3)),
        migrations.AddField(model_name="agentcommand", name="priority", field=models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")], default="medium", max_length=20)),
        migrations.AddField(model_name="agentcommand", name="retry_count", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="agentcommand", name="source_agent", field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name="agentcommand", name="started_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="agentcommand", name="timeout_seconds", field=models.PositiveIntegerField(default=30)),
        migrations.AlterField(model_name="agentcommand", name="status", field=models.CharField(choices=[("pending", "Pending"), ("dispatched", "Dispatched"), ("running", "Running"), ("succeeded", "Succeeded"), ("timed_out", "Timed Out"), ("failed", "Failed"), ("cancelled", "Cancelled")], default="pending", max_length=20)),
        migrations.AddIndex(model_name="agentcommand", index=models.Index(fields=["status", "available_at"], name="agent_cmd_status_available_idx")),
        migrations.AddIndex(model_name="agentcommand", index=models.Index(fields=["target_agent", "status"], name="agent_cmd_target_status_idx")),
        migrations.AddIndex(model_name="agentcommand", index=models.Index(fields=["case", "status"], name="agent_cmd_case_status_idx")),
        migrations.AddIndex(model_name="agentcommand", index=models.Index(fields=["loop_signature"], name="agent_cmd_loop_signature_idx")),
        migrations.AddField(model_name="agentresponse", name="model_name", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="agentresponse", name="policy_version", field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name="agentresponse", name="prompt_version", field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name="agentresponse", name="provider", field=models.CharField(blank=True, max_length=50)),
        migrations.AddField(model_name="agentresponse", name="schema_version", field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name="agentresponse", name="trace_id", field=models.CharField(blank=True, max_length=100)),
        migrations.AlterField(model_name="agentresponse", name="status", field=models.CharField(choices=[("pending", "Pending"), ("dispatched", "Dispatched"), ("running", "Running"), ("succeeded", "Succeeded"), ("timed_out", "Timed Out"), ("failed", "Failed"), ("cancelled", "Cancelled")], max_length=20)),
        migrations.CreateModel(
            name="PromptDefinition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("agent_type", models.CharField(max_length=100)),
                ("tenant_id", models.CharField(default="default", max_length=100)),
                ("version", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("draft", "Draft"), ("active", "Active"), ("deprecated", "Deprecated"), ("rolled_back", "Rolled Back")], default="draft", max_length=20)),
                ("description", models.TextField(blank=True)),
                ("content", models.TextField()),
                ("variables", models.JSONField(blank=True, default=dict)),
                ("output_schema", models.JSONField(blank=True, default=dict)),
                ("policy", models.JSONField(blank=True, default=dict)),
                ("content_hash", models.CharField(db_index=True, max_length=64)),
                ("created_by", models.CharField(blank=True, max_length=120)),
                ("rollback_from_version", models.PositiveIntegerField(blank=True, null=True)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["agent_type", "tenant_id", "status"], name="prompt_def_agent_tenant_status_idx"),
                    models.Index(fields=["content_hash"], name="prompt_def_content_hash_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("agent_type", "tenant_id", "version"), name="uniq_prompt_definition_version"),
                ],
            },
        ),
    ]
