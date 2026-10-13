from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from habits.models import Habit, HabitCompletion
from habits.services import calculate_completion_rate, calculate_streaks


@login_required
def dashboard_view(request):
    """
    Main dashboard aggregating today's scheduled habits, streaks, and completion rates.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    all_habits_count = Habit.objects.filter(tenant=tenant).count()
    if all_habits_count == 0:
        return redirect("onboarding")

    today = timezone.localdate()
    active_habits = Habit.objects.filter(tenant=tenant, is_active=True).order_by("name")

    today_habit_cards = []
    scheduled_today_count = 0
    completed_today_count = 0

    # Prefetch today's completions for efficiency
    today_completed_habit_ids = set(
        HabitCompletion.objects.filter(
            tenant=tenant,
            completion_date=today,
        ).values_list("habit_id", flat=True)
    )

    for habit in active_habits:
        is_scheduled = habit.is_scheduled_for_date(today)
        is_completed = habit.id in today_completed_habit_ids
        streaks = calculate_streaks(habit, today)
        rate_7d = calculate_completion_rate(habit, today - timedelta(days=6), today, today)

        if is_scheduled:
            scheduled_today_count += 1
            if is_completed:
                completed_today_count += 1

        time_allowed, time_status = habit.is_time_window_active()

        today_habit_cards.append({
            "habit": habit,
            "is_scheduled_today": is_scheduled,
            "is_completed_today": is_completed,
            "current_streak": streaks["current_streak"],
            "longest_streak": streaks["longest_streak"],
            "rate_7d": rate_7d["rate"],
            "eligible_7d": rate_7d["eligible"],
            "completed_7d": rate_7d["completed"],
            "time_allowed": time_allowed,
            "time_status": time_status,
        })

    all_completed_today = (scheduled_today_count > 0 and scheduled_today_count == completed_today_count)

    context = {
        "today": today,
        "habit_cards": today_habit_cards,
        "scheduled_today_count": scheduled_today_count,
        "completed_today_count": completed_today_count,
        "all_completed_today": all_completed_today,
        "total_active_habits": len(today_habit_cards),
    }

    return render(request, "dashboard/dashboard.html", context)
