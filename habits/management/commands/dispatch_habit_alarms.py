from django.core.management.base import BaseCommand
from habits.alarm_scheduler import dispatch_due_habit_alarms


class Command(BaseCommand):
    help = "Dispatches habit alarm intimations via free Web Push to subscribed users for due habits."

    def handle(self, *args, **options):
        count = dispatch_due_habit_alarms()
        self.stdout.write(self.style.SUCCESS(f"Total habit alarms dispatched: {count}"))
