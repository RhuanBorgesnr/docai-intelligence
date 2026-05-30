"""
Celery application configuration.
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

from celery import Celery
from celery.schedules import crontab

app = Celery("core")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Scheduled tasks (Celery Beat)
app.conf.beat_schedule = {
    'send-expiration-notifications-daily': {
        'task': 'documents.tasks.send_expiration_notifications',
        'schedule': crontab(hour=8, minute=0),
        'args': (7,),
    },
    'publish-durable-outbox-every-10s': {
        'task': 'orchestrator.tasks.publish_pending_outbox',
        'schedule': 10.0,
        'args': (),
    },
    'scan-pending-approvals-every-minute': {
        'task': 'approvals.tasks.scan_pending_approvals',
        'schedule': 60.0,
        'args': (),
    },
    'process-agent-intake-batch': {
        'task': 'agent_runtime.tasks.process_agent_command_batch',
        'schedule': 15.0,
        'args': ('intake', 5),
    },
    'process-agent-sdr-batch': {
        'task': 'agent_runtime.tasks.process_agent_command_batch',
        'schedule': 15.0,
        'args': ('sdr', 5),
    },
    'process-agent-sales-batch': {
        'task': 'agent_runtime.tasks.process_agent_command_batch',
        'schedule': 15.0,
        'args': ('sales', 5),
    },
    'process-agent-docai-batch': {
        'task': 'agent_runtime.tasks.process_agent_command_batch',
        'schedule': 15.0,
        'args': ('docai_operator', 3),
    },
    # Sprint 2.5 — durable notification retry sweep every 30 s
    'retry-pending-notifications-every-30s': {
        'task': 'notifications.tasks.retry_pending_notifications',
        'schedule': 30.0,
        'args': (50,),
    },
    # Sprint 3 — Jarvis executive briefing daily at 07:00
    'jarvis-executive-briefing-daily': {
        'task': 'orchestrator.jarvis_briefing',
        'schedule': crontab(hour=7, minute=0),
        'args': (),
    },

    # ── Sprint 4 / Phase 3 — Agent Team Routines ─────────────────────────
    # SDR
    'sdr-stale-lead-check': {
        'task': 'agent_runtime.routines.sdr_stale_lead_check',
        'schedule': crontab(minute=0, hour='*/4'),
    },
    # Sales
    'sales-followup-check': {
        'task': 'agent_runtime.routines.sales_followup_check',
        'schedule': crontab(minute=30, hour='*/4'),
    },
    'sales-pipeline-stale-check': {
        'task': 'agent_runtime.routines.sales_pipeline_stale_check',
        'schedule': crontab(minute=0, hour=8),
    },
    # DocAI Operator
    'docai-pending-demo-check': {
        'task': 'agent_runtime.routines.docai_pending_demo_check',
        'schedule': crontab(minute=15, hour='*/4'),
    },
    # Theo
    'theo-daily-briefing': {
        'task': 'agent_runtime.routines.theo_daily_briefing',
        'schedule': crontab(minute=0, hour=7),
    },
    'theo-agent-health-check': {
        'task': 'agent_runtime.routines.theo_agent_health_check',
        'schedule': crontab(minute=45),
    },
    'theo-escalation-sweep': {
        'task': 'agent_runtime.routines.theo_escalation_sweep',
        'schedule': crontab(minute='*/30'),
    },
    # Intake
    'intake-webhook-health': {
        'task': 'agent_runtime.routines.intake_webhook_health',
        'schedule': crontab(minute=0, hour='*/4'),
    },
    # Analyst
    'analyst-daily-metrics': {
        'task': 'agent_runtime.routines.analyst_daily_metrics',
        'schedule': crontab(minute=0, hour=23),
    },
    'analyst-weekly-funnel': {
        'task': 'agent_runtime.routines.analyst_weekly_funnel',
        'schedule': crontab(minute=0, hour=8, day_of_week=1),
    },

    # ── Infrastructure — Automated Database Backup ────────────────────────
    'database-backup-daily': {
        'task': 'core.tasks.backup_database',
        'schedule': crontab(minute=0, hour=3),  # Daily at 3am
    },
}