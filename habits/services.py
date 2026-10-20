import calendar
from collections import defaultdict
from datetime import date, timedelta
from django.utils import timezone
from config.performance import profile_function
from .models import Habit, HabitCompletion


def daterange(start_date, end_date):
    """
    Generator yielding dates from start_date up to end_date inclusive.
    """
    curr = start_date
    while curr <= end_date:
        yield curr
        curr += timedelta(days=1)


def get_eligible_scheduled_dates(habit, start_date, end_date):
    """
    Returns a list of eligible scheduled dates for the habit within [start_date, end_date].
    Respects start_date and scheduling frequency.
    """
    effective_start = max(start_date, habit.start_date)
    if effective_start > end_date:
        return []
    return [d for d in daterange(effective_start, end_date) if habit.is_scheduled_for_date(d)]


@profile_function("habits.services.calculate_completion_rate")
def calculate_completion_rate(habit, start_date, end_date, today=None, completed_dates=None):
    """
    Calculates completion rate for a given window [start_date, end_date].
    Formula: completed eligible scheduled days / total eligible scheduled days * 100.
    
    Rules:
    - Excludes future dates.
    - Excludes unscheduled days and dates before habit.start_date.
    - If total eligible days is 0, returns None for rate to avoid division by zero.
    - Optional completed_dates set enables batch prefetching with zero DB queries.
    """
    if today is None:
        today = timezone.localdate()

    # Never count future dates
    effective_end = min(end_date, today)
    effective_start = max(start_date, habit.start_date)

    if effective_start > effective_end:
        return {
            "completed": 0,
            "eligible": 0,
            "rate": None,
        }

    eligible_dates = [d for d in daterange(effective_start, effective_end) if habit.is_scheduled_for_date(d)]
    total_eligible = len(eligible_dates)

    if total_eligible == 0:
        return {
            "completed": 0,
            "eligible": 0,
            "rate": None,
        }

    if completed_dates is not None:
        completed_count = sum(1 for d in eligible_dates if d in completed_dates)
    else:
        completed_count = HabitCompletion.objects.filter(
            habit=habit,
            completion_date__in=eligible_dates,
        ).count()

    rate = round((completed_count / total_eligible) * 100, 1)

    return {
        "completed": completed_count,
        "eligible": total_eligible,
        "rate": rate,
    }


@profile_function("habits.services.calculate_streaks")
def calculate_streaks(habit, today=None, completed_dates=None):
    """
    Calculates the current streak and longest streak according to the habit's schedule.
    
    Current streak rules:
    - Consecutive completed eligible scheduled days up to today.
    - If today is an eligible day and is completed, it counts in the streak.
    - If today is an eligible day and not yet completed, the streak from yesterday remains intact.
    - If today is unscheduled, the streak from the most recent eligible day remains intact.
    - A missed scheduled day in the past breaks the streak.
    
    Longest streak rules:
    - Maximum consecutive completed eligible scheduled days in the habit's entire history.
    - Optional completed_dates set enables batch prefetching with zero DB queries.
    """
    if today is None:
        today = timezone.localdate()

    if today < habit.start_date:
        return {
            "current_streak": 0,
            "longest_streak": 0,
        }

    # Fetch all completed dates if not passed in
    if completed_dates is None:
        completed_dates = set(
            HabitCompletion.objects.filter(
                habit=habit,
                completion_date__gte=habit.start_date,
                completion_date__lte=today,
            ).values_list("completion_date", flat=True)
        )

    # All eligible dates up to today in chronological order
    eligible_dates = [
        d for d in daterange(habit.start_date, today)
        if habit.is_scheduled_for_date(d)
    ]

    if not eligible_dates:
        return {
            "current_streak": 0,
            "longest_streak": 0,
        }

    # Calculate longest streak across history
    longest_streak = 0
    current_run = 0
    for d in eligible_dates:
        if d in completed_dates:
            current_run += 1
            if current_run > longest_streak:
                longest_streak = current_run
        else:
            current_run = 0

    # Calculate current streak walking backward
    reversed_eligible = list(reversed(eligible_dates))
    current_streak = 0

    if not reversed_eligible:
        return {
            "current_streak": 0,
            "longest_streak": longest_streak,
        }

    # Check the most recent eligible day
    most_recent_eligible = reversed_eligible[0]

    if most_recent_eligible == today:
        if today in completed_dates:
            # Completed today: streak includes today and continues backward
            for d in reversed_eligible:
                if d in completed_dates:
                    current_streak += 1
                else:
                    break
        else:
            # Scheduled today but not yet completed: evaluate from previous eligible day
            for d in reversed_eligible[1:]:
                if d in completed_dates:
                    current_streak += 1
                else:
                    break
    else:
        # Today is unscheduled: evaluate from most recent eligible day backward
        for d in reversed_eligible:
            if d in completed_dates:
                current_streak += 1
            else:
                break

    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
    }


def get_habit_statistics(habit, today=None):
    """
    Aggregates comprehensive statistics for a single habit.
    """
    if today is None:
        today = timezone.localdate()

    streaks = calculate_streaks(habit, today)
    rate_7d = calculate_completion_rate(habit, today - timedelta(days=6), today, today)
    rate_30d = calculate_completion_rate(habit, today - timedelta(days=29), today, today)
    all_time = calculate_completion_rate(habit, habit.start_date, today, today)
    total_completed = HabitCompletion.objects.filter(habit=habit).count()

    is_scheduled_today = habit.is_scheduled_for_date(today)
    is_completed_today = HabitCompletion.objects.filter(habit=habit, completion_date=today).exists()

    return {
        "habit": habit,
        "total_completed": total_completed,
        "current_streak": streaks["current_streak"],
        "longest_streak": streaks["longest_streak"],
        "rate_7d": rate_7d,
        "rate_30d": rate_30d,
        "all_time": all_time,
        "is_scheduled_today": is_scheduled_today,
        "is_completed_today": is_completed_today,
    }


def generate_monthly_calendar_data(habit, year, month, today=None):
    """
    Generates structured monthly calendar grid for habit progress.
    Each day contains status:
    - completed: scheduled and completed
    - missed: scheduled, date < today, not completed, date >= start_date
    - pending_today: scheduled, today, not yet completed
    - unscheduled: not scheduled or before start_date
    - future: date > today
    """
    if today is None:
        today = timezone.localdate()

    cal = calendar.Calendar(firstweekday=0) # Monday first
    month_days = cal.monthdatescalendar(year, month)

    # Determine date range for month completions query
    first_date = month_days[0][0]
    last_date = month_days[-1][-1]

    completed_dates = set(
        HabitCompletion.objects.filter(
            habit=habit,
            completion_date__gte=first_date,
            completion_date__lte=last_date,
        ).values_list("completion_date", flat=True)
    )

    weeks_data = []
    month_eligible_count = 0
    month_completed_count = 0

    for week in month_days:
        week_days = []
        for d in week:
            in_current_month = (d.month == month)
            is_today = (d == today)
            is_future = (d > today)
            is_prior_to_start = (d < habit.start_date)
            is_scheduled = habit.is_scheduled_for_date(d)
            is_completed = (d in completed_dates)

            # Determine visual status
            if is_future:
                status = "future"
            elif is_prior_to_start or not is_scheduled:
                status = "unscheduled"
            elif is_completed:
                status = "completed"
            elif is_today:
                status = "pending_today"
            else:
                status = "missed"

            # Count monthly stats for days in the target month up to today
            if in_current_month and not is_future and is_scheduled and not is_prior_to_start:
                month_eligible_count += 1
                if is_completed:
                    month_completed_count += 1

            week_days.append({
                "date": d,
                "day_number": d.day,
                "in_current_month": in_current_month,
                "is_today": is_today,
                "is_future": is_future,
                "is_scheduled": is_scheduled,
                "is_completed": is_completed,
                "status": status,
            })
        weeks_data.append(week_days)

    # Calculate month rate
    month_rate = None
    if month_eligible_count > 0:
        month_rate = round((month_completed_count / month_eligible_count) * 100, 1)

    # Navigation months
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    month_name = calendar.month_name[month]

    return {
        "habit": habit,
        "year": year,
        "month": month,
        "month_name": month_name,
        "weeks": weeks_data,
        "month_eligible_count": month_eligible_count,
        "month_completed_count": month_completed_count,
        "month_rate": month_rate,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
    }


def get_pending_days_in_month(habit=None, today=None):
    """
    Calculates the pending number of days remaining in the current month
    for habit pixel allocation.
    - If today is the 1st of any month: 30 days pending (e.g., 2 * 30 = 60 pixels)
    - If today is the 18th of the month: 12 days to go (e.g., 2 * 12 = 24 + 5 * 12 = 60 -> 84 pixels)
    - Generally: calculates pending days in standard 30-day month cycle or remaining calendar days.
    """
    if today is None:
        today = timezone.localdate()

    start_day = today.day
    if habit and habit.start_date and habit.start_date.month == today.month and habit.start_date.year == today.year:
        if habit.start_date > today:
            start_day = habit.start_date.day

    total_days = calendar.monthrange(today.year, today.month)[1]

    if start_day == 18:
        return 12
    if start_day == 1:
        return 30

    if start_day < 30:
        return max(0, 30 - start_day)
    return max(0, total_days - start_day)


@profile_function("habits.services.calculate_user_pixel_wallet")
def calculate_user_pixel_wallet(user, tenant=None, today=None, completions_by_habit=None, habits_qs=None):
    """
    Computes the user's Pixel Wallet status:
    1. Allocated Pixels: Credited for the month as Daily Score * Pending Days in Month.
    2. Lost Pixels: Deducted for each scheduled day missed prior to today.
    3. Current Balance: Allocated Pixels - Lost Pixels (energized balance).
    4. Health Percent: (Current Balance / Allocated Pixels) * 100.
    Optional completions_by_habit dict enables batch prefetching with zero DB queries.
    Optional habits_qs avoids redundant habit fetching.
    """
    if today is None:
        today = timezone.localdate()

    if tenant is None and user and hasattr(user, "memberships"):
        membership = user.memberships.select_related("tenant").filter(status="ACTIVE").first()
        tenant = membership.tenant if membership else None

    from .models import Habit, HabitCompletion, PixelWallet

    if habits_qs is None:
        if tenant:
            habits_qs = list(Habit.objects.filter(tenant=tenant, is_template=False, is_active=True).select_related("category_ref", "rule_strategy_ref").order_by("-is_active", "name"))
        elif user and hasattr(user, "pk") and user.pk:
            habits_qs = list(Habit.objects.filter(created_by=user, is_template=False, is_active=True).select_related("category_ref", "rule_strategy_ref").order_by("-is_active", "name"))
        else:
            habits_qs = []

    pending_days = get_pending_days_in_month(None, today)
    habits_breakdown = []
    total_allocated = 0
    total_lost = 0

    month_start = date(today.year, today.month, 1)

    # Batch prefetch all habit completions in one query if not passed
    if completions_by_habit is None and habits_qs:
        completions_by_habit = defaultdict(set)
        h_ids = [h.id for h in habits_qs]
        all_comp = HabitCompletion.objects.filter(
            habit_id__in=h_ids,
            completion_date__gte=month_start,
            completion_date__lte=today,
        ).values_list("habit_id", "completion_date")
        for hid, cdate in all_comp:
            completions_by_habit[hid].add(cdate)

    for h in habits_qs:
        daily_score = h.pixel_score or (2 if h.is_general else (5 if h.is_predefined_purpose else 10))
        h_pending_days = get_pending_days_in_month(h, today)
        h_allocated = daily_score * h_pending_days

        habit_active_start = max(month_start, h.start_date)

        if completions_by_habit is not None:
            all_h_completed = completions_by_habit.get(h.id, set())
            completed_dates = {d for d in all_h_completed if habit_active_start <= d < today}
            is_completed_today = (today in all_h_completed)
        else:
            completed_dates = set(
                HabitCompletion.objects.filter(
                    habit=h,
                    completion_date__gte=habit_active_start,
                    completion_date__lt=today,
                ).values_list("completion_date", flat=True)
            )
            is_completed_today = HabitCompletion.objects.filter(habit=h, completion_date=today).exists()

        missed_days = 0
        curr_d = habit_active_start
        while curr_d < today:
            if h.is_scheduled_for_date(curr_d):
                if curr_d not in completed_dates:
                    missed_days += 1
            curr_d += timedelta(days=1)

        h_lost = missed_days * daily_score
        h_retained = max(0, h_allocated - h_lost)

        is_scheduled_today = h.is_scheduled_for_date(today)

        total_allocated += h_allocated
        total_lost += h_lost

        habits_breakdown.append({
            "habit": h,
            "daily_score": daily_score,
            "pending_days": h_pending_days,
            "allocated_pixels": h_allocated,
            "missed_days": missed_days,
            "lost_pixels": h_lost,
            "retained_pixels": h_retained,
            "is_scheduled_today": is_scheduled_today,
            "is_completed_today": is_completed_today,
        })

    current_balance = max(0, total_allocated - total_lost)
    health_percent = round((current_balance / total_allocated * 100), 1) if total_allocated > 0 else 100.0

    total_habit_pixels = sum(item["daily_score"] for item in habits_breakdown)
    today_scheduled_pixels = sum(item["daily_score"] for item in habits_breakdown if item["is_scheduled_today"])
    today_completed_pixels = sum(item["daily_score"] for item in habits_breakdown if item["is_scheduled_today"] and item["is_completed_today"])
    today_pending_pixels = max(0, today_scheduled_pixels - today_completed_pixels)
    projected_balance_if_failed = max(0, current_balance - today_pending_pixels)

    if today_scheduled_pixels > 0:
        if today_pending_pixels == 0:
            daily_outcome_text = (
                f"All {today_scheduled_pixels} pixels secured for today! "
                f"Your wallet is protected at {current_balance} pixels with 100% solid energy."
            )
        elif today_completed_pixels > 0:
            daily_outcome_text = (
                f"Out of total {today_scheduled_pixels} pixels to achieve from the day you only did {today_completed_pixels}, "
                f"please commit yourself to earn the remaining {today_pending_pixels}."
            )
        else:
            daily_outcome_text = (
                f"Currently the wallet has {current_balance} pixels in your account, "
                f"but if you fail to accomplish your pending habit task your wallet will end up losing your valuable pixels and settle {today_pending_pixels} pixels lower to {projected_balance_if_failed}."
            )
    else:
        daily_outcome_text = (
            f"Rest day today! No scheduled pixels at risk. Your wallet is safe at {current_balance} pixels."
        )

    wallet_obj = None
    if tenant and user and hasattr(user, "pk") and user.pk:
        wallet_obj, _ = PixelWallet.objects.get_or_create(
            tenant=tenant,
            user=user,
            year=today.year,
            month=today.month,
            defaults={
                "allocated_pixels": total_allocated,
                "lost_pixels": total_lost,
                "current_balance": current_balance,
            }
        )
        if (wallet_obj.allocated_pixels != total_allocated or 
            wallet_obj.lost_pixels != total_lost or 
            wallet_obj.current_balance != current_balance):
            wallet_obj.allocated_pixels = total_allocated
            wallet_obj.lost_pixels = total_lost
            wallet_obj.current_balance = current_balance
            wallet_obj.save(update_fields=["allocated_pixels", "lost_pixels", "current_balance", "updated_at"])

    return {
        "wallet": wallet_obj,
        "allocated_pixels": total_allocated,
        "lost_pixels": total_lost,
        "current_balance": current_balance,
        "health_percent": health_percent,
        "pending_days": pending_days,
        "month_name": today.strftime("%B %Y"),
        "today": today,
        "habits_breakdown": habits_breakdown,
        "habits_count": len(habits_breakdown),
        "total_missed_days": sum(h["missed_days"] for h in habits_breakdown),
        "total_pixels": total_habit_pixels,
        "total_habit_pixels": total_habit_pixels,
        "today_scheduled_pixels": today_scheduled_pixels,
        "today_completed_pixels": today_completed_pixels,
        "today_pending_pixels": today_pending_pixels,
        "projected_balance_if_failed": projected_balance_if_failed,
        "daily_outcome_text": daily_outcome_text,
    }
