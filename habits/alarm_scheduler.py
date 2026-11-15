import logging
import threading
from django.utils import timezone

logger = logging.getLogger(__name__)

_scheduler_started = False
_scheduler_lock = threading.Lock()


def dispatch_due_habit_alarms():
    """
    Scans all active habits across the database with reminder_enabled=True.
    Dispatches free Web Push notifications to user devices (phone/desktop)
    when habits are due, open for completion, and not yet completed today.
    """
    from habits.models import Habit, HabitCompletion
    from habits.services import send_habit_web_push

    today = timezone.localdate()
    now_dt = timezone.localtime()
    now_time = now_dt.time()
    now_total_mins = now_time.hour * 60 + now_time.minute

    due_habits = Habit.objects.filter(
        is_active=True,
        is_template=False,
        reminder_enabled=True,
        reminder_time__isnull=False,
    ).select_related("tenant", "created_by")

    dispatched_count = 0

    for habit in due_habits:
        try:
            # 1. Scheduled for today?
            if not habit.is_scheduled_for_date(today):
                continue

            # 2. Already completed today?
            if HabitCompletion.objects.filter(habit=habit, completion_date=today).exists():
                continue

            # 3. Open for completion right now?
            time_allowed, _ = habit.is_time_window_active(now_time)
            if not time_allowed:
                continue

            # 4. Configured reminder time reached?
            rem_t = habit.reminder_time
            rem_total_mins = rem_t.hour * 60 + rem_t.minute
            if now_total_mins < rem_total_mins:
                continue

            # 5. Currently snoozed?
            if habit.snoozed_until and habit.snoozed_until > now_dt:
                continue

            # 6. Check last reminded timestamp today to avoid duplicate alerts within snooze interval
            should_dispatch = False
            if not habit.last_reminded_at or habit.last_reminded_at.date() < today:
                should_dispatch = True
            elif habit.reminder_snooze_interval and habit.reminder_snooze_interval > 0:
                elapsed_seconds = (now_dt - habit.last_reminded_at).total_seconds()
                if elapsed_seconds >= (habit.reminder_snooze_interval * 60):
                    should_dispatch = True

            if should_dispatch and habit.created_by:
                sent = send_habit_web_push(
                    user=habit.created_by,
                    title=f"⏰ Habit Reminder: {habit.name}",
                    body=f"Time to complete '{habit.name}'! Protect your streak and earn {habit.pixel_score or 2} pixels.",
                    habit_id=habit.id,
                    url="/habits/",
                )
                habit.last_reminded_at = now_dt
                habit.save(update_fields=["last_reminded_at"])
                if sent > 0:
                    dispatched_count += sent
                    logger.info("Dispatched habit push alarm to %s for %s", habit.created_by.username, habit.name)
        except Exception as e:
            logger.warning("Error in habit alarm dispatcher for habit %s: %s", habit.id, e)

    return dispatched_count


class HabitAlarmSchedulerThread(threading.Thread):
    def __init__(self, interval_seconds=30):
        super().__init__(name="HabitAlarmSchedulerThread", daemon=True)
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()

    def run(self):
        logger.info("Habit alarm background scheduler thread started.")
        while not self._stop_event.is_set():
            try:
                dispatch_due_habit_alarms()
            except Exception as e:
                logger.warning("Error in habit alarm scheduler loop: %s", e)
            self._stop_event.wait(self.interval_seconds)

    def stop(self):
        self._stop_event.set()


def start_alarm_scheduler():
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
        thread = HabitAlarmSchedulerThread(interval_seconds=30)
        thread.start()
