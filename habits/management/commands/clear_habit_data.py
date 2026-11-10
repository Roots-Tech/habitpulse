from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Neutralized command: habit and completion table deletion is strictly disabled under the Zero Data Loss policy."

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.ERROR(
                "ACTION BLOCKED: Mass habit and completion data purging is strictly prohibited "
                "under the HabitPulse Zero Data Loss Policy (SEC-06 / AGENTS.md). "
                "No database records were modified."
            )
        )
