import calendar
from datetime import date, timedelta
from django.utils import timezone
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


def calculate_completion_rate(habit, start_date, end_date, today=None):
    """
    Calculates completion rate for a given window [start_date, end_date].
    Formula: completed eligible scheduled days / total eligible scheduled days * 100.
    
    Rules:
    - Excludes future dates.
    - Excludes unscheduled days and dates before habit.start_date.
    - If total eligible days is 0, returns None for rate to avoid division by zero.
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


def calculate_streaks(habit, today=None):
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
    """
    if today is None:
        today = timezone.localdate()

    if today < habit.start_date:
        return {
            "current_streak": 0,
            "longest_streak": 0,
        }

    # Fetch all completed dates
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
