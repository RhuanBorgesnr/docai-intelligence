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
    # Send expiration notifications every day at 8:00 AM
    'send-expiration-notifications-daily': {
        'task': 'documents.tasks.send_expiration_notifications',
        'schedule': crontab(hour=8, minute=0),
        'args': (7,),  # Check documents expiring in next 7 days
    },
}