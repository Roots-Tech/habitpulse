from datetime import date
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import HabitForm, HabitCompletionSubmissionForm
from .models import Habit, HabitCompletion
from .services import (
    calculate_completion_rate,
    calculate_streaks,
    generate_monthly_calendar_data,
    get_habit_statistics,
)
from .validators import HabitCompletionValidationEngine


@login_required
def onboarding_view(request):
    """
    Welcoming onboarding page for users with zero habits.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    if Habit.objects.filter(tenant=tenant).exists():
        return redirect("dashboard")

    return render(request, "habits/onboarding.html")


@login_required
def habit_list_view(request):
    """
    Lists all habits within the user's current tenant workspace.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    habits = Habit.objects.filter(tenant=tenant).order_by("-is_active", "name")
    return render(request, "habits/habit_list.html", {"habits": habits})


@login_required
def habit_create_view(request):
    """
    Creates a new habit in the active tenant.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    if request.method == "POST":
        form = HabitForm(request.POST)
        if form.is_valid():
            habit = form.save(commit=False)
            habit.tenant = tenant
            habit.created_by = request.user
            habit.save()
            messages.success(request, f'Habit "{habit.name}" created successfully!')
            return redirect("dashboard")
        else:
            messages.error(request, "Please fix the errors in the habit form.")
    else:
        form = HabitForm()

    return render(request, "habits/habit_form.html", {
        "form": form,
        "action_title": "Create a New Habit",
        "submit_label": "Create Habit",
    })


@login_required
def habit_update_view(request, pk):
    """
    Updates an existing habit. Strictly tenant-scoped.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    habit = get_object_or_404(Habit, pk=pk, tenant=tenant)

    if request.method == "POST":
        form = HabitForm(request.POST, instance=habit)
        if form.is_valid():
            form.save()
            messages.success(request, f'Habit "{habit.name}" updated successfully!')
            return redirect("dashboard")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = HabitForm(instance=habit)

    return render(request, "habits/habit_form.html", {
        "form": form,
        "habit": habit,
        "action_title": f'Edit "{habit.name}"',
        "submit_label": "Save Changes",
    })


@login_required
@require_POST
def habit_toggle_active_view(request, pk):
    """
    Toggles the active status of a habit. Strictly tenant-scoped.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    habit = get_object_or_404(Habit, pk=pk, tenant=tenant)
    habit.is_active = not habit.is_active
    habit.save(update_fields=["is_active", "updated_at"])

    status_str = "activated" if habit.is_active else "deactivated"
    messages.success(request, f'Habit "{habit.name}" was {status_str}.')
    return redirect("habit_list")


@login_required
@require_POST
def habit_complete_view(request, pk):
    """
    Marks a habit completed for today (or specified date).
    Enforces tenant match, schedule rules, and prevents duplicates.
    Supports both HTMX/JSON and standard form submission.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

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

    # Validate not future
    if target_date > today:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"error": "Cannot complete habits for future dates."}, status=400)
        messages.error(request, "Cannot complete habits for future dates.")
        return redirect("dashboard")

    # Validate habit start date
    if target_date < habit.start_date:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"error": "Cannot complete habits before their start date."}, status=400)
        messages.error(request, "Cannot complete habits before their start date.")
        return redirect("dashboard")

    # Validate schedule
    if not habit.is_scheduled_for_date(target_date):
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"error": "Habit is not scheduled for this day."}, status=400)
        messages.warning(request, "This habit is not scheduled for today.")
        return redirect("dashboard")

    # Habit validation engine (time window, proof upload, numeric target)
    engine = HabitCompletionValidationEngine()
    validation_errors = engine.validate(habit, request.POST, request.FILES)
    if validation_errors:
        err_msg = validation_errors[0]
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"error": err_msg, "errors": validation_errors}, status=400)
        messages.error(request, err_msg)
        next_url = request.POST.get("next") or "dashboard"
        return redirect(next_url)

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

    try:
        with transaction.atomic():
            HabitCompletion.objects.create(
                tenant=tenant,
                habit=habit,
                completion_date=target_date,
                evidence_file=evidence_file,
                logged_value=logged_val,
                notes=notes,
            )
        messages.success(request, f'Nice job! "{habit.name}" verified and completed successfully.')
    except IntegrityError:
        # Already completed - idempotent handling
        pass

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        stats = get_habit_statistics(habit, today)
        return JsonResponse({
            "status": "completed",
            "current_streak": stats["current_streak"],
            "rate_7d": stats["rate_7d"]["rate"],
        })

    next_url = request.POST.get("next") or request.GET.get("next") or "dashboard"
    return redirect(next_url)


@login_required
@require_POST
def habit_undo_complete_view(request, pk):
    """
    Undoes completion for today (or specified date). Strictly tenant-scoped.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

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

    with transaction.atomic():
        deleted_count, _ = HabitCompletion.objects.filter(
            tenant=tenant,
            habit=habit,
            completion_date=target_date,
        ).delete()

    if deleted_count > 0:
        messages.info(request, f'Completion for "{habit.name}" was undone.')

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        stats = get_habit_statistics(habit, today)
        return JsonResponse({
            "status": "uncompleted",
            "current_streak": stats["current_streak"],
            "rate_7d": stats["rate_7d"]["rate"],
        })

    next_url = request.POST.get("next") or request.GET.get("next") or "dashboard"
    return redirect(next_url)


@login_required
def habit_calendar_view(request, pk):
    """
    Monthly calendar view for a single habit.
    Supports month/year navigation and displays visual states.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    habit = get_object_or_404(Habit, pk=pk, tenant=tenant)
    today = timezone.localdate()

    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        if month < 1 or month > 12:
            year, month = today.year, today.month
    except (ValueError, TypeError):
        year, month = today.year, today.month

    calendar_data = generate_monthly_calendar_data(habit, year, month, today)
    stats = get_habit_statistics(habit, today)
    recent_completions = HabitCompletion.objects.filter(
        tenant=tenant,
        habit=habit,
    ).order_by("-completion_date")[:15]

    return render(request, "habits/habit_calendar.html", {
        "habit": habit,
        "cal": calendar_data,
        "stats": stats,
        "today": today,
        "recent_completions": recent_completions,
    })


@login_required
def habit_stats_view(request, pk):
    """
    In-depth statistics page for a single habit.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    habit = get_object_or_404(Habit, pk=pk, tenant=tenant)
    today = timezone.localdate()
    stats = get_habit_statistics(habit, today)

    return render(request, "habits/habit_stats.html", {
        "habit": habit,
        "stats": stats,
        "today": today,
    })
