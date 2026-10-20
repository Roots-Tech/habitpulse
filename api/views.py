from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import json

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from habits.models import Habit, HabitCompletion
from habits.services import (
    calculate_completion_rate,
    calculate_streaks,
    calculate_user_pixel_wallet,
)
from habits.validators import HabitCompletionValidationEngine

User = get_user_model()


def _require_auth(request):
    """Returns an error response if request is unauthenticated."""
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Unauthorized", "detail": "Authentication credentials were not provided."},
            status=401,
        )
    return None


@require_GET
def dashboard_api(request):
    """
    GET /api/v1/dashboard/
    Returns live aggregated dashboard metrics, habit cards, pixel wallet status,
    and real-time time window statuses for the active user/tenant.
    Inspectable under DevTools Network > Fetch/XHR.
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    tenant = getattr(request, "tenant", None)
    if not tenant and not request.user.is_super_admin:
        return JsonResponse({"error": "Forbidden", "detail": "No active workspace assigned."}, status=403)

    scope = request.GET.get("scope", "all" if request.user.is_super_admin else "my")
    today = timezone.localdate()

    if request.user.is_super_admin and scope != "my":
        habits_qs = Habit.objects.filter(is_template=False).select_related("tenant", "category_ref", "rule_strategy_ref")
        today_completed_habit_ids = set(
            HabitCompletion.objects.filter(completion_date=today).values_list("habit_id", flat=True)
        )
    else:
        habits_qs = Habit.objects.filter(tenant=tenant, is_template=False).select_related("tenant", "category_ref", "rule_strategy_ref")
        today_completed_habit_ids = set(
            HabitCompletion.objects.filter(tenant=tenant, completion_date=today).values_list("habit_id", flat=True)
        )

    active_habits = habits_qs.filter(is_active=True).order_by("name")

    habit_cards = []
    scheduled_count = 0
    completed_count = 0

    for habit in active_habits:
        is_scheduled = habit.is_scheduled_for_date(today)
        is_completed = habit.id in today_completed_habit_ids
        streaks = calculate_streaks(habit, today)
        rate_7d = calculate_completion_rate(habit, today - timedelta(days=6), today, today)
        time_allowed, time_status = habit.is_time_window_active()

        if is_scheduled:
            scheduled_count += 1
            if is_completed:
                completed_count += 1

        cat_name = habit.category_ref.name if habit.category_ref else (habit.category or "")
        habit_cards.append({
            "id": habit.id,
            "name": habit.name,
            "description": habit.description,
            "category": cat_name,
            "habit_type": habit.habit_type,
            "pixel_score": habit.pixel_score,
            "frequency": habit.frequency,
            "is_scheduled_today": is_scheduled,
            "is_completed_today": is_completed,
            "current_streak": streaks["current_streak"],
            "longest_streak": streaks["longest_streak"],
            "rate_7d": rate_7d["rate"],
            "has_time_window": habit.has_time_window,
            "window_start": habit.window_start_time.strftime("%H:%M:%S") if habit.window_start_time else None,
            "window_end": habit.window_end_time.strftime("%H:%M:%S") if habit.window_end_time else None,
            "window_start_display": habit.window_start_time.strftime("%I:%M %p") if habit.window_start_time else "",
            "window_end_display": habit.window_end_time.strftime("%I:%M %p") if habit.window_end_time else "",
            "time_allowed": time_allowed,
            "time_status": time_status,
            "requires_modal": habit.requires_modal,
            "requires_evidence": habit.requires_evidence,
            "requires_numeric": habit.requires_numeric,
            "target_value": float(habit.target_value) if habit.target_value is not None else None,
            "unit_label": habit.unit_label,
        })

    wallet_data = calculate_user_pixel_wallet(request.user, tenant=tenant, today=today)

    return JsonResponse({
        "status": "success",
        "date": str(today),
        "scope": scope,
        "summary": {
            "scheduled_today_count": scheduled_count,
            "completed_today_count": completed_count,
            "all_completed_today": (scheduled_count > 0 and scheduled_count == completed_count),
            "total_active_habits": len(habit_cards),
        },
        "wallet": {
            "allocated_pixels": wallet_data.get("allocated_pixels", 0),
            "lost_pixels": wallet_data.get("lost_pixels", 0),
            "current_balance": wallet_data.get("current_balance", 0),
            "health_percent": wallet_data.get("health_percent", 100.0),
            "today_scheduled_pixels": wallet_data.get("today_scheduled_pixels", 0),
            "today_completed_pixels": wallet_data.get("today_completed_pixels", 0),
            "today_pending_pixels": wallet_data.get("today_pending_pixels", 0),
            "projected_balance_if_failed": wallet_data.get("projected_balance_if_failed", 0),
            "daily_outcome_text": wallet_data.get("daily_outcome_text", ""),
        },
        "habits": habit_cards,
    })


@require_POST
def habit_complete_api(request, pk):
    """
    POST /api/v1/habits/<pk>/complete/
    Marks a habit as completed for today (or specified date).
    Enforces time-window constraints, proof uploads, and numeric metrics.
    Returns JSON status and updated wallet metrics.
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    tenant = getattr(request, "tenant", None)
    if not tenant and not request.user.is_super_admin:
        return JsonResponse({"error": "Forbidden", "detail": "No active workspace assigned."}, status=403)

    if request.user.is_super_admin:
        habit = get_object_or_404(Habit, pk=pk)
    else:
        habit = get_object_or_404(Habit, pk=pk, tenant=tenant)

    today = timezone.localdate()
    date_str = request.POST.get("date")
    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = today
    else:
        target_date = today

    if target_date > today:
        return JsonResponse({"success": False, "error": "Cannot complete habits for future dates."}, status=400)

    if target_date < habit.start_date:
        return JsonResponse({"success": False, "error": "Cannot complete habits before their start date."}, status=400)

    if not habit.is_scheduled_for_date(target_date):
        return JsonResponse({"success": False, "error": "Habit is not scheduled for this date."}, status=400)

    engine = HabitCompletionValidationEngine()
    validation_errors = engine.validate(habit, request.POST, request.FILES)
    if validation_errors:
        return JsonResponse(
            {"success": False, "error": validation_errors[0], "errors": validation_errors},
            status=400,
        )

    logged_val = request.POST.get("logged_value")
    if logged_val:
        try:
            logged_val = Decimal(str(logged_val).strip())
        except (InvalidOperation, ValueError, TypeError):
            logged_val = None
    else:
        logged_val = None

    notes = request.POST.get("notes", "").strip()
    evidence_file = request.FILES.get("evidence_file")

    with transaction.atomic():
        HabitCompletion.objects.create(
            tenant=habit.tenant,
            habit=habit,
            completion_date=target_date,
            logged_value=logged_val,
            evidence_file=evidence_file,
            notes=notes,
        )

    streaks = calculate_streaks(habit, today)
    rate_7d = calculate_completion_rate(habit, today - timedelta(days=6), today, today)
    wallet_data = calculate_user_pixel_wallet(request.user, tenant=habit.tenant, today=today)

    return JsonResponse({
        "success": True,
        "message": f"Habit '{habit.name}' completed successfully!",
        "habit_id": habit.id,
        "completion_date": str(target_date),
        "is_completed_today": True,
        "streaks": {
            "current_streak": streaks["current_streak"],
            "longest_streak": streaks["longest_streak"],
        },
        "rate_7d": rate_7d["rate"],
        "wallet": {
            "current_balance": wallet_data.get("current_balance", 0),
            "health_percent": wallet_data.get("health_percent", 100.0),
            "today_pending_pixels": wallet_data.get("today_pending_pixels", 0),
            "projected_balance_if_failed": wallet_data.get("projected_balance_if_failed", 0),
            "daily_outcome_text": wallet_data.get("daily_outcome_text", ""),
        },
    }, status=200)


@require_POST
def habit_undo_api(request, pk):
    """
    POST /api/v1/habits/<pk>/undo/
    Reverts completion for today (or specified date).
    Returns JSON status and updated wallet metrics.
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    tenant = getattr(request, "tenant", None)
    if not tenant and not request.user.is_super_admin:
        return JsonResponse({"error": "Forbidden", "detail": "No active workspace assigned."}, status=403)

    if request.user.is_super_admin:
        habit = get_object_or_404(Habit, pk=pk)
    else:
        habit = get_object_or_404(Habit, pk=pk, tenant=tenant)

    today = timezone.localdate()
    date_str = request.POST.get("date")
    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = today
    else:
        target_date = today

    HabitCompletion.objects.filter(
        habit=habit,
        completion_date=target_date,
    ).delete()

    streaks = calculate_streaks(habit, today)
    rate_7d = calculate_completion_rate(habit, today - timedelta(days=6), today, today)
    wallet_data = calculate_user_pixel_wallet(request.user, tenant=habit.tenant, today=today)

    return JsonResponse({
        "success": True,
        "message": f"Habit '{habit.name}' completion undone.",
        "habit_id": habit.id,
        "completion_date": str(target_date),
        "is_completed_today": False,
        "streaks": {
            "current_streak": streaks["current_streak"],
            "longest_streak": streaks["longest_streak"],
        },
        "rate_7d": rate_7d["rate"],
        "wallet": {
            "current_balance": wallet_data.get("current_balance", 0),
            "health_percent": wallet_data.get("health_percent", 100.0),
            "today_pending_pixels": wallet_data.get("today_pending_pixels", 0),
            "projected_balance_if_failed": wallet_data.get("projected_balance_if_failed", 0),
            "daily_outcome_text": wallet_data.get("daily_outcome_text", ""),
        },
    }, status=200)


@require_GET
def users_list_api(request):
    """
    GET /api/v1/users/
    Returns user directory with real-time pixel scores, access roles, and metadata.
    Scoped by tenant or platform-wide for super admins.
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    tenant = getattr(request, "tenant", None)
    today = timezone.localdate()

    if request.user.is_super_admin:
        users_qs = User.objects.all().order_by("-is_superuser", "username")
    elif tenant:
        users_qs = User.objects.filter(memberships__tenant=tenant, memberships__status="ACTIVE").distinct().order_by("username")
    else:
        users_qs = User.objects.filter(pk=request.user.pk)

    results = []
    for u in users_qs:
        # Determine access role
        if getattr(u, "is_super_admin", False) or u.is_superuser:
            role_label = "System Super Admin"
        elif u.is_staff:
            role_label = "System Staff"
        else:
            role_label = "Tenant Member"

        # Compute user's pixel score
        u_wallet = calculate_user_pixel_wallet(u, tenant=tenant, today=today)
        score = u_wallet.get("current_balance", 0)

        full_name = f"{u.first_name} {u.last_name}".strip()
        display_name = full_name if full_name else u.username

        results.append({
            "id": u.id,
            "username": u.username,
            "name": display_name,
            "email": u.email,
            "role": role_label,
            "pixel_score": score,
            "is_active": u.is_active,
        })

    return JsonResponse({
        "status": "success",
        "total_count": len(results),
        "users": results,
    })


@require_GET
def habit_status_api(request, pk):
    """
    GET /api/v1/habits/<pk>/status/
    Returns real-time status of a habit (time window lock state, today completion status, streaks).
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    tenant = getattr(request, "tenant", None)
    if request.user.is_super_admin:
        habit = get_object_or_404(Habit, pk=pk)
    else:
        habit = get_object_or_404(Habit, pk=pk, tenant=tenant)

    today = timezone.localdate()
    is_scheduled = habit.is_scheduled_for_date(today)
    is_completed = HabitCompletion.objects.filter(habit=habit, completion_date=today).exists()
    time_allowed, time_status = habit.is_time_window_active()
    streaks = calculate_streaks(habit, today)

    return JsonResponse({
        "id": habit.id,
        "name": habit.name,
        "is_scheduled_today": is_scheduled,
        "is_completed_today": is_completed,
        "time_allowed": time_allowed,
        "time_status": time_status,
        "current_streak": streaks["current_streak"],
        "longest_streak": streaks["longest_streak"],
    })
