import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'swift_django.settings')

app = Celery('swift_django')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

from celery.signals import after_setup_task_logger
import logging

def configure_task_logging(**kwargs):
    logger = logging.getLogger('app.tasks')
    if not logger.handlers:  # Check if the logger already has handlers
        handler = logging.FileHandler('logs/tasks.log')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False

after_setup_task_logger.connect(configure_task_logging)