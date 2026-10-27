from datetime import datetime, date, time, timedelta
from django.utils import timezone


def habit_notifications(request):
    """
    Context processor that supplies active habit alarm notifications for the authenticated user,
    reminding the user when to log in, what actions to confirm, and the consequences of missing
    time windows or daily commitments on their pixel wallet balance and consistency streak.

    - Completed habits for today are automatically removed from the notification panel.
    - At the start of the next day (00:00:00 midnight), scheduled habits appear fresh as pending alarms.
    - Notifications are strictly ordered by how and when they can be marked completed:
      1. Open right now (earliest closing deadline first - most urgent)
      2. All-day habits available right now (highest pixel stake first)
      3. Upcoming time windows (opening chronologically earliest first)
      4. Missed windows
    """
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {
            "habit_notifications": [],
            "unread_alarms_count": 0,
            "has_urgent_alarms": False,
            "open_alarms_count": 0,
            "upcoming_alarms_count": 0,
            "completed_today_count": 0,
        }

    tenant = getattr(request, "tenant", None)
    if not tenant and hasattr(request.user, "memberships"):
        membership = request.user.memberships.select_related("tenant").filter(status="ACTIVE").first()
        tenant = membership.tenant if membership else None

    today = timezone.localdate()
    now_dt = timezone.localtime()
    now_time = now_dt.time()

    from habits.models import Habit, HabitCompletion

    if tenant:
        habits_qs = Habit.objects.filter(
            tenant=tenant,
            is_template=False,
            is_active=True,
        ).select_related("category_ref", "rule_strategy_ref")
    else:
        habits_qs = Habit.objects.filter(
            created_by=request.user,
            is_template=False,
            is_active=True,
        ).select_related("category_ref", "rule_strategy_ref")

    completed_habit_ids = set(
        HabitCompletion.objects.filter(
            habit__in=habits_qs,
            completion_date=today,
        ).values_list("habit_id", flat=True)
    )

    notifications = []
    has_urgent_alarms = False
    today_formatted = today.strftime("%A, %B %d, %Y")

    for habit in habits_qs:
        if not habit.is_scheduled_for_date(today):
            continue

        is_completed = habit.id in completed_habit_ids
        # Requirement: Once a habit is marked complete for today, remove it from the notification panel.
        if is_completed:
            continue

        has_tw = bool(habit.window_start_time and habit.window_end_time)
        pixel_score = habit.pixel_score or (2 if habit.is_general else (5 if habit.is_predefined_purpose else 10))

        if has_tw:
            start_t = habit.window_start_time
            end_t = habit.window_end_time
            start_str = start_t.strftime("%I:%M %p")
            end_str = end_t.strftime("%I:%M %p")

            # 5 minutes before window_start_time
            start_dt = datetime.combine(today, start_t)
            prep_dt = start_dt - timedelta(minutes=5)
            prep_str = prep_dt.strftime("%I:%M %p")

            if now_time < start_t:
                status = "upcoming"
                badge_text = f"Locked until {start_str}"
                badge_class = "badge-warning"
                headline = f"Upcoming Window Alarm: {habit.name}"
                message = (
                    f"To ensure you preserve {pixel_score} pixels allowed for {habit.name} habit on {today_formatted}, "
                    f"you should login 5 mins before {start_str} (by {prep_str}) and confirm if completed necessary action "
                    f"to maintain the consistency streak of a progressive habit!!"
                )
                consequence = (
                    f"If you fail to complete the assignment completion before {end_str}, your consistency to habit "
                    f"will be marked as not completed for the day and your {pixel_score} pixel goes off your wallet."
                )
                action_required = True
                can_complete_now = False
            elif start_t <= now_time <= end_t:
                status = "open"
                badge_text = f"Open Now: Closes at {end_str}"
                badge_class = "badge-danger"
                headline = f"CRITICAL ACTION REQUIRED: {habit.name}"
                message = (
                    f"Your completion window for {habit.name} is OPEN NOW until {end_str} on {today_formatted}! "
                    f"Confirm if you have completed the necessary action to maintain the consistency streak of a progressive habit!!"
                )
                consequence = (
                    f"If you fail to complete the assignment completion before {end_str}, your consistency to habit "
                    f"will be marked as not completed for the day and your {pixel_score} pixel goes off your wallet."
                )
                action_required = True
                has_urgent_alarms = True
                can_complete_now = True
            else:
                status = "missed"
                badge_text = f"Window Closed at {end_str}"
                badge_class = "badge-secondary"
                headline = f"Window Closed: {habit.name}"
                message = (
                    f"The time window ({start_str} - {end_str}) for {habit.name} on {today_formatted} has closed without confirmed action."
                )
                consequence = (
                    f"Marked as not completed for the day and {pixel_score} pixels deducted from your wallet."
                )
                action_required = False
                can_complete_now = False

            notifications.append({
                "habit": habit,
                "habit_id": habit.id,
                "habit_name": habit.name,
                "pixel_score": pixel_score,
                "status": status,
                "badge_text": badge_text,
                "badge_class": badge_class,
                "headline": headline,
                "message": message,
                "consequence": consequence,
                "action_required": action_required,
                "can_complete_now": can_complete_now,
                "start_time_str": start_str,
                "end_time_str": end_str,
                "prep_time_str": prep_str,
                "today_formatted": today_formatted,
                "has_time_window": True,
            })
        else:
            notifications.append({
                "habit": habit,
                "habit_id": habit.id,
                "habit_name": habit.name,
                "pixel_score": pixel_score,
                "status": "due_today",
                "badge_text": "Due Today by 11:59 PM",
                "badge_class": "badge-warning",
                "headline": f"Daily Action Due: {habit.name}",
                "message": (
                    f"To ensure you preserve {pixel_score} pixels allowed for {habit.name} habit on {today_formatted}, "
                    f"you should complete and confirm the necessary action to maintain the consistency streak of a progressive habit!!"
                ) if habit.name else "Complete your daily habit action.",
                "consequence": (
                    f"If you fail to complete the assignment completion before 11:59 PM, your consistency to habit "
                    f"will be marked as not completed for the day and your {pixel_score} pixel goes off your wallet."
                ),
                "action_required": True,
                "can_complete_now": True,
                "start_time_str": None,
                "end_time_str": "11:59 PM",
                "prep_time_str": None,
                "today_formatted": today_formatted,
                "has_time_window": False,
            })

    def notification_sort_key(n):
        """
        Sort order strictly by how habits can be marked completed:
        1. Open right now (earliest closing deadline first - highest priority)
        2. All-day / Due today (available to complete now - highest pixel reward first)
        3. Upcoming windows (opening chronologically earliest first)
        4. Missed / closed
        """
        status = n["status"]
        if status == "open":
            end_t = n["habit"].window_end_time or time(23, 59, 59)
            return (0, end_t, -n["pixel_score"], n["habit_name"])
        elif status == "due_today":
            return (1, time(23, 59, 59), -n["pixel_score"], n["habit_name"])
        elif status == "upcoming":
            start_t = n["habit"].window_start_time or time(23, 59, 59)
            return (2, start_t, -n["pixel_score"], n["habit_name"])
        elif status == "missed":
            end_t = n["habit"].window_end_time or time(23, 59, 59)
            return (3, end_t, -n["pixel_score"], n["habit_name"])
        return (4, time(23, 59, 59), 0, n["habit_name"])

    notifications.sort(key=notification_sort_key)

    open_alarms_count = sum(1 for n in notifications if n["status"] in ("open", "due_today"))
    upcoming_alarms_count = sum(1 for n in notifications if n["status"] == "upcoming")

    return {
        "habit_notifications": notifications,
        "unread_alarms_count": len(notifications),
        "has_urgent_alarms": has_urgent_alarms,
        "open_alarms_count": open_alarms_count,
        "upcoming_alarms_count": upcoming_alarms_count,
        "completed_today_count": len(completed_habit_ids),
    }
