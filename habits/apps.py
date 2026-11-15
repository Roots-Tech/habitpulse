import os
import sys
from django.apps import AppConfig


class HabitsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "habits"

    def ready(self):
        # Start background alarm dispatcher only in main process / runserver worker
        if os.environ.get("RUN_MAIN") == "true" or ("runserver" in sys.argv and "--noreload" in sys.argv):
            from .alarm_scheduler import start_alarm_scheduler
            start_alarm_scheduler()
