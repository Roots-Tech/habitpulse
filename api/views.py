from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import json

from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
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
from config.performance import performance_tracker

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
        habits_qs = Habit.objects.filter(is_template=False).select_related("created_by", "tenant", "category_ref", "rule_strategy_ref")
    else:
        habits_qs = Habit.objects.filter(tenant=tenant, is_template=False).select_related("created_by", "tenant", "category_ref", "rule_strategy_ref")

    active_habits = list(habits_qs.filter(is_active=True).order_by("name"))
    active_habit_ids = [h.id for h in active_habits]

    # Batch-prefetch all completions in a single database query
    completions_by_habit = defaultdict(set)
    if active_habit_ids:
        all_comp_qs = HabitCompletion.objects.filter(
            habit_id__in=active_habit_ids,
        ).values_list("habit_id", "completion_date")
        for hid, cdate in all_comp_qs:
            completions_by_habit[hid].add(cdate)

    habit_cards = []
    scheduled_count = 0
    completed_count = 0

    for habit in active_habits:
        habit_comp_dates = completions_by_habit.get(habit.id, set())
        is_scheduled = habit.is_scheduled_for_date(today)
        is_completed = today in habit_comp_dates
        streaks = calculate_streaks(habit, today, completed_dates=habit_comp_dates)
        rate_7d = calculate_completion_rate(habit, today - timedelta(days=6), today, today, completed_dates=habit_comp_dates)
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
            "is_location_restricted": habit.is_location_restricted,
            "location_name": habit.location_name,
            "target_latitude": float(habit.target_latitude) if habit.target_latitude is not None else None,
            "target_longitude": float(habit.target_longitude) if habit.target_longitude is not None else None,
            "allowed_radius_meters": habit.allowed_radius_meters,
            "target_value": float(habit.target_value) if habit.target_value is not None else None,
            "unit_label": habit.unit_label,
        })

    wallet_data = calculate_user_pixel_wallet(request.user, tenant=tenant, today=today, completions_by_habit=completions_by_habit, habits_qs=active_habits)

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

    raw_lat = request.POST.get("latitude")
    raw_lng = request.POST.get("longitude")
    comp_lat = None
    comp_lng = None
    comp_dist = None
    if raw_lat is not None and raw_lng is not None and str(raw_lat).strip() and str(raw_lng).strip():
        try:
            comp_lat = Decimal(str(raw_lat).strip())
            comp_lng = Decimal(str(raw_lng).strip())
            if habit.target_latitude is not None and habit.target_longitude is not None:
                from habits.validators import haversine_distance_meters
                comp_dist = int(round(haversine_distance_meters(
                    float(comp_lat), float(comp_lng), float(habit.target_latitude), float(habit.target_longitude)
                )))
        except (InvalidOperation, ValueError, TypeError):
            pass

    notes = request.POST.get("notes", "").strip()
    evidence_file = request.FILES.get("evidence_file")

    raw_dur = request.POST.get("duration_minutes") or request.POST.get("logged_duration_minutes") or request.POST.get("logged_duration")
    logged_dur = None
    if raw_dur:
        try:
            logged_dur = int(float(str(raw_dur).strip()))
        except (ValueError, TypeError):
            logged_dur = None

    ai_status = "SKIPPED"
    ai_reason = ""
    ai_confidence = None
    if evidence_file and getattr(habit, "enable_ai_proof_verification", True):
        from habits.services import verify_proof_relevance
        ai_res = verify_proof_relevance(habit, evidence_file)
        ai_status = ai_res.get("status", "APPROVED")
        ai_reason = ai_res.get("reason", "")
        ai_confidence = ai_res.get("confidence")

    is_idempotent_duplicate = False
    try:
        with transaction.atomic():
            HabitCompletion.objects.create(
                tenant=habit.tenant,
                habit=habit,
                completion_date=target_date,
                logged_value=logged_val,
                logged_duration_minutes=logged_dur,
                ai_verification_status=ai_status,
                ai_verification_reason=ai_reason,
                ai_confidence_score=ai_confidence,
                evidence_file=evidence_file,
                notes=notes,
                completion_latitude=comp_lat,
                completion_longitude=comp_lng,
                completion_distance_meters=comp_dist,
            )
    except IntegrityError:
        # Idempotent response for duplicate submissions / mobile double-clicks (API-01)
        is_idempotent_duplicate = True

    streaks = calculate_streaks(habit, today)
    rate_7d = calculate_completion_rate(habit, today - timedelta(days=6), today, today)
    wallet_data = calculate_user_pixel_wallet(request.user, tenant=habit.tenant, today=today)

    success_msg = f"Habit '{habit.name}' was already completed for {target_date}." if is_idempotent_duplicate else f"Habit '{habit.name}' completed successfully!"
    return JsonResponse({
        "success": True,
        "message": success_msg,
        "idempotent": is_idempotent_duplicate,
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


@require_GET
def admin_performance_api(request):
    """
    GET /api/v1/admin/performance/
    Returns live APM metrics, endpoint latencies, SQL timings, function timings, and memory footprint.
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    if not (request.user.is_super_admin or getattr(request.user, "can_manage_users", False) or request.user.is_staff):
        return JsonResponse({"error": "Forbidden", "detail": "Administrative privileges required."}, status=403)

    metrics = performance_tracker.get_metrics()
    return JsonResponse({"status": "success", "data": metrics})


@require_POST
def admin_performance_reset_api(request):
    """
    POST /api/v1/admin/performance/reset/
    Flushes all in-memory performance metrics to restart a fresh profiling benchmark.
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    if not (request.user.is_super_admin or getattr(request.user, "can_manage_users", False) or request.user.is_staff):
        return JsonResponse({"error": "Forbidden", "detail": "Administrative privileges required."}, status=403)

    performance_tracker.reset()
    return JsonResponse({"status": "success", "message": "Performance metrics reset successfully."})



def resolve_map_url_api(request):
    """
    GET or POST /api/v1/resolve-map-url/?url=...
    Extracts geographic coordinates and place name from Google Maps URLs or coordinate strings.
    """
    url = request.GET.get("url") or request.POST.get("url")
    if not url:
        return JsonResponse({"success": False, "error": "URL or coordinates parameter is required."}, status=400)

    from habits.services import parse_google_maps_url_or_coords
    result = parse_google_maps_url_or_coords(url)
    status_code = 200 if result.get("success") else 400
    return JsonResponse(result, status=status_code)


@require_http_methods(["GET", "POST"])
def habit_reminder_api(request, pk):
    """
    GET /api/habits/<pk>/reminder/
    POST /api/habits/<pk>/reminder/
    Configures or retrieves personal habit alarm settings.
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    tenant = getattr(request, "tenant", None)
    habit = get_object_or_404(Habit, pk=pk)

    # Permission check: ensure user owns the habit or is super admin
    if not request.user.is_super_admin:
        if tenant and habit.tenant != tenant:
            return JsonResponse({"error": "Forbidden", "detail": "You do not have access to this habit."}, status=403)
        if not tenant and habit.created_by != request.user:
            return JsonResponse({"error": "Forbidden", "detail": "You do not have access to this habit."}, status=403)

    if request.method == "GET":
        return JsonResponse({
            "success": True,
            "habit_id": habit.pk,
            "habit_name": habit.name,
            "reminder_enabled": habit.reminder_enabled,
            "reminder_time": habit.reminder_time.strftime("%H:%M") if habit.reminder_time else "",
            "reminder_snooze_interval": habit.reminder_snooze_interval,
            "reminder_display": habit.reminder_display or "Off",
            "snoozed_until": habit.snoozed_until.isoformat() if habit.snoozed_until else None,
        })

    # POST
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else request.POST
    except Exception:
        data = request.POST

    reminder_enabled = bool(data.get("reminder_enabled") in [True, "true", "1", 1, "on"])
    reminder_time_raw = data.get("reminder_time")
    try:
        snooze_interval = int(data.get("reminder_snooze_interval", 0))
    except (ValueError, TypeError):
        snooze_interval = 0

    from datetime import datetime, time
    parsed_time = None
    if reminder_time_raw:
        if isinstance(reminder_time_raw, str):
            clean_time = reminder_time_raw.strip()
            for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
                try:
                    parsed_time = datetime.strptime(clean_time, fmt).time()
                    break
                except ValueError:
                    continue
        elif isinstance(reminder_time_raw, time):
            parsed_time = reminder_time_raw

    habit.reminder_enabled = reminder_enabled
    if reminder_enabled and parsed_time:
        habit.reminder_time = parsed_time
    habit.reminder_snooze_interval = snooze_interval
    habit.snoozed_until = None
    habit.save(update_fields=["reminder_enabled", "reminder_time", "reminder_snooze_interval", "snoozed_until", "updated_at"])

    return JsonResponse({
        "success": True,
        "habit_id": habit.pk,
        "habit_name": habit.name,
        "reminder_enabled": habit.reminder_enabled,
        "reminder_time": habit.reminder_time.strftime("%H:%M") if habit.reminder_time else "",
        "reminder_display": habit.reminder_display or "Off",
        "message": f"Alarm for '{habit.name}' updated successfully.",
    })


@require_POST
def habit_reminder_snooze_api(request, pk):
    """
    POST /api/habits/<pk>/reminder/snooze/
    Snoozes an active habit alarm intimation by N minutes (default 60).
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    tenant = getattr(request, "tenant", None)
    habit = get_object_or_404(Habit, pk=pk)

    if not request.user.is_super_admin:
        if tenant and habit.tenant != tenant:
            return JsonResponse({"error": "Forbidden", "detail": "You do not have access to this habit."}, status=403)
        if not tenant and habit.created_by != request.user:
            return JsonResponse({"error": "Forbidden", "detail": "You do not have access to this habit."}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else request.POST
    except Exception:
        data = request.POST

    try:
        minutes = int(data.get("minutes", 60))
    except (ValueError, TypeError):
        minutes = 60

    habit.snoozed_until = timezone.now() + timedelta(minutes=minutes)
    habit.save(update_fields=["snoozed_until", "updated_at"])

    return JsonResponse({
        "success": True,
        "habit_id": habit.pk,
        "snoozed_until": habit.snoozed_until.isoformat(),
        "minutes": minutes,
        "message": f"Habit alarm snoozed for {minutes} minutes.",
    })


@require_GET
def active_reminders_api(request):
    """
    GET /api/habits/reminders/active/
    Returns all active habit alarms for today for the logged-in user,
    used by the client-side Web Audio + Notification scheduler.
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    tenant = getattr(request, "tenant", None)
    today = timezone.localdate()
    now_dt = timezone.localtime()

    if tenant:
        habits_qs = Habit.objects.filter(tenant=tenant, is_template=False, is_active=True)
    else:
        habits_qs = Habit.objects.filter(created_by=request.user, is_template=False, is_active=True)

    completed_ids = set(
        HabitCompletion.objects.filter(
            habit__in=habits_qs,
            completion_date=today,
        ).values_list("habit_id", flat=True)
    )

    items = []
    for habit in habits_qs:
        if not habit.is_scheduled_for_date(today):
            continue
        is_completed = habit.id in completed_ids

        # If already completed today, suppress the alarm
        if is_completed:
            continue

        alarm_time_str = None
        if habit.reminder_enabled and habit.reminder_time:
            alarm_time_str = habit.reminder_time.strftime("%H:%M")
        elif habit.window_start_time:
            alarm_time_str = habit.window_start_time.strftime("%H:%M")

        if not alarm_time_str:
            continue

        items.append({
            "id": habit.id,
            "name": habit.name,
            "reminder_enabled": habit.reminder_enabled,
            "reminder_time": alarm_time_str,
            "reminder_display": habit.reminder_display or alarm_time_str,
            "reminder_snooze_interval": habit.reminder_snooze_interval,
            "snoozed_until": habit.snoozed_until.isoformat() if habit.snoozed_until else None,
            "pixel_score": habit.pixel_score or 0,
            "is_completed_today": is_completed,
        })

    return JsonResponse({
        "success": True,
        "server_time": now_dt.strftime("%H:%M:%S"),
        "server_date": today.isoformat(),
        "reminders": items,
    })


@require_http_methods(["POST", "DELETE"])
def push_subscribe_api(request):
    """
    POST /api/push/subscribe/
    Registers or updates a browser PushSubscription for free Web Push alerts.
    DELETE /api/push/subscribe/
    Removes the subscription.
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    from habits.models import PushSubscription

    if request.method == "DELETE":
        try:
            data = json.loads(request.body.decode("utf-8")) if request.body else {}
            endpoint = data.get("endpoint")
            if endpoint:
                PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
            else:
                PushSubscription.objects.filter(user=request.user).delete()
        except Exception:
            PushSubscription.objects.filter(user=request.user).delete()
        return JsonResponse({"success": True, "message": "Push subscription removed."})

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else request.POST
    except Exception:
        data = request.POST

    endpoint = data.get("endpoint")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh") or data.get("p256dh", "")
    auth = keys.get("auth") or data.get("auth", "")

    if not endpoint or not p256dh or not auth:
        return JsonResponse({"error": "Bad Request", "detail": "Missing endpoint, p256dh or auth keys."}, status=400)

    user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]

    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": request.user,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": user_agent,
        },
    )

    return JsonResponse({"success": True, "message": "Push subscription registered successfully."})
