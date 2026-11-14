from datetime import time, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from habits.models import Habit, HabitCompletion
from habits.services import send_habit_web_push


class Command(BaseCommand):
    help = "Dispatches habit alarm intimations via free Web Push to subscribed users for due habits."

    def handle(self, *args, **options):
        today = timezone.localdate()
        now = timezone.localtime()
        current_time = now.time()

        # Find habits scheduled for today with reminder_enabled=True
        habits = Habit.objects.filter(
            is_active=True,
            is_template=False,
            reminder_enabled=True,
            reminder_time__isnull=False,
        ).select_related("tenant", "created_by")

        dispatched_count = 0
        for habit in habits:
            if not habit.is_scheduled_for_date(today):
                continue

            # Check if already completed today
            if HabitCompletion.objects.filter(habit=habit, completion_date=today).exists():
                continue

            # Check if snoozed
            if habit.snoozed_until and habit.snoozed_until > now:
                continue

            # Compare reminder time: if within past 15 mins or matches
            rem_t = habit.reminder_time
            now_mins = current_time.hour * 60 + current_time.minute
            rem_mins = rem_t.hour * 60 + rem_t.minute
            diff = now_mins - rem_mins

            # Fire if within 15 minutes of reminder_time, or if snooze expired within 15 mins
            should_fire = False
            if 0 <= diff <= 15:
                should_fire = True
            elif habit.snoozed_until and (now - habit.snoozed_until).total_seconds() < 900:
                should_fire = True

            if should_fire:
                user = habit.created_by
                if user:
                    sent = send_habit_web_push(
                        user=user,
                        title=f"⏰ Habit Alarm: {habit.name}",
                        body=f"Time to complete '{habit.name}'! Earn {habit.pixel_score or 2} pixels on HabitPulse.",
                        habit_id=habit.id,
                        url="/habits/",
                    )
                    if sent > 0:
                        dispatched_count += sent
                        self.stdout.write(self.style.SUCCESS(f"Sent alarm to {user.username} for {habit.name}"))

        self.stdout.write(self.style.SUCCESS(f"Total habit alarms dispatched: {dispatched_count}"))
