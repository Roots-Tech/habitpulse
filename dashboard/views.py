from collections import defaultdict
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from habits.models import Habit, HabitCompletion
from habits.services import calculate_completion_rate, calculate_streaks, calculate_user_pixel_wallet


@login_required
def dashboard_view(request):
    """
    Main dashboard aggregating today's scheduled habits, streaks, and completion rates.
    Super Admins have unrestricted visibility across all users' habits, with optional personal filter.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    scope = request.GET.get("scope", "all" if request.user.is_super_admin else "my")

    if request.user.is_super_admin and scope != "my":
        habits_qs = Habit.objects.filter(is_template=False).select_related("created_by", "tenant", "category_ref", "rule_strategy_ref")
        all_habits = list(habits_qs.order_by("name"))
        all_users_habits_count = len(all_habits)
        my_habits_count = Habit.objects.filter(tenant=tenant, is_template=False).count()
    else:
        habits_qs = Habit.objects.filter(tenant=tenant, is_template=False).select_related("created_by", "tenant", "category_ref", "rule_strategy_ref")
        all_habits = list(habits_qs.order_by("name"))
        my_habits_count = len(all_habits)
        all_users_habits_count = Habit.objects.filter(is_template=False).count() if request.user.is_super_admin else 0

    if not all_habits:
        if request.user.is_super_admin and all_users_habits_count > 0:
            return redirect(f"{reverse('dashboard')}?scope=all")
        return redirect("onboarding")

    today = timezone.localdate()
    active_habits = [h for h in all_habits if h.is_active]
    active_habit_ids = [h.id for h in active_habits]

    # Batch-prefetch all completions in a single database query
    completions_by_habit = defaultdict(set)
    if active_habit_ids:
        all_comp_qs = HabitCompletion.objects.filter(
            habit_id__in=active_habit_ids,
        ).values_list("habit_id", "completion_date")
        for hid, cdate in all_comp_qs:
            completions_by_habit[hid].add(cdate)

    today_habit_cards = []
    scheduled_today_count = 0
    completed_today_count = 0

    for habit in active_habits:
        habit_comp_dates = completions_by_habit.get(habit.id, set())
        is_scheduled = habit.is_scheduled_for_date(today)
        is_completed = today in habit_comp_dates
        streaks = calculate_streaks(habit, today, completed_dates=habit_comp_dates)
        rate_7d = calculate_completion_rate(habit, today - timedelta(days=6), today, today, completed_dates=habit_comp_dates)

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
    wallet_data = calculate_user_pixel_wallet(request.user, tenant=tenant, today=today, completions_by_habit=completions_by_habit, habits_qs=active_habits)

    context = {
        "today": today,
        "habit_cards": today_habit_cards,
        "scheduled_today_count": scheduled_today_count,
        "completed_today_count": completed_today_count,
        "all_completed_today": all_completed_today,
        "total_active_habits": len(today_habit_cards),
        "scope": scope,
        "all_users_habits_count": all_users_habits_count,
        "my_habits_count": my_habits_count,
        "wallet_data": wallet_data,
    }

    return render(request, "dashboard/dashboard.html", context)
