from datetime import date
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from accounts.decorators import (
    category_permission_required,
    rule_strategy_permission_required,
    technical_or_admin_required,
)

from .forms import (
    HabitCategoryForm,
    HabitCompletionSubmissionForm,
    HabitForm,
    RuleStrategyForm,
)
from .models import (
    Habit,
    HabitCategory,
    HabitCompletion,
    RuleStrategy,
    seed_default_master_data_for_tenant,
)
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
        form = HabitForm(request.POST, tenant=tenant)
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
        form = HabitForm(tenant=tenant)

    available_rule_strategies = RuleStrategy.objects.filter(tenant=tenant, is_active=True)

    return render(request, "habits/habit_form.html", {
        "form": form,
        "available_rule_strategies": available_rule_strategies,
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
        form = HabitForm(request.POST, instance=habit, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Habit "{habit.name}" updated successfully!')
            return redirect("dashboard")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = HabitForm(instance=habit, tenant=tenant)

    available_rule_strategies = RuleStrategy.objects.filter(tenant=tenant, is_active=True)

    return render(request, "habits/habit_form.html", {
        "form": form,
        "habit": habit,
        "available_rule_strategies": available_rule_strategies,
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


# ==============================================================================
# MASTER DATA: HABIT CATEGORIES CRUD
# ==============================================================================

@category_permission_required
def category_list_view(request):
    """
    Master Data: Lists all Habit Categories in the user's active workspace.
    Supports search query (?q=).
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    if not HabitCategory.objects.filter(tenant=tenant).exists():
        seed_default_master_data_for_tenant(tenant)

    q = request.GET.get("q", "").strip()
    categories = HabitCategory.objects.filter(tenant=tenant).annotate(
        total_habits=Count("habits")
    )
    if q:
        categories = categories.filter(
            Q(name__icontains=q) | Q(description__icontains=q)
        )

    categories = categories.order_by("name")

    return render(request, "habits/category_list.html", {
        "categories": categories,
        "search_query": q,
    })


@category_permission_required
def category_create_view(request):
    """
    Master Data: Create a new Habit Category for the active tenant.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    if request.method == "POST":
        form = HabitCategoryForm(request.POST, tenant=tenant)
        if form.is_valid():
            category = form.save(commit=False)
            category.tenant = tenant
            category.save()
            messages.success(request, f'Category "{category.name}" created successfully!')
            return redirect("category_list")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = HabitCategoryForm(tenant=tenant)

    return render(request, "habits/category_form.html", {
        "form": form,
        "action_title": "Create Habit Category",
        "submit_label": "Create Category",
    })


@category_permission_required
def category_update_view(request, pk):
    """
    Master Data: Edit an existing Habit Category. Strictly tenant-scoped.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    category = get_object_or_404(HabitCategory, pk=pk, tenant=tenant)

    if request.method == "POST":
        form = HabitCategoryForm(request.POST, instance=category, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Category "{category.name}" updated successfully!')
            return redirect("category_list")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = HabitCategoryForm(instance=category, tenant=tenant)

    return render(request, "habits/category_form.html", {
        "form": form,
        "category": category,
        "action_title": f'Edit Category: "{category.name}"',
        "submit_label": "Save Changes",
    })


@category_permission_required
def category_delete_view(request, pk):
    """
    Master Data: Delete a Habit Category. Strictly tenant-scoped.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    category = get_object_or_404(HabitCategory, pk=pk, tenant=tenant)
    habits_count = category.habits.count()

    if request.method == "POST":
        category_name = category.name
        category.delete()
        messages.success(request, f'Category "{category_name}" was deleted successfully.')
        return redirect("category_list")

    return render(request, "habits/category_confirm_delete.html", {
        "category": category,
        "habits_count": habits_count,
    })


# ==============================================================================
# MASTER DATA: RULE STRATEGIES CRUD
# ==============================================================================

@rule_strategy_permission_required
def rule_strategy_list_view(request):
    """
    Master Data: Lists all Rule Strategies in the user's active workspace.
    Supports search query (?q=).
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    if not RuleStrategy.objects.filter(tenant=tenant).exists():
        seed_default_master_data_for_tenant(tenant)

    q = request.GET.get("q", "").strip()
    strategies = RuleStrategy.objects.filter(tenant=tenant).annotate(
        total_habits=Count("habits")
    )
    if q:
        strategies = strategies.filter(
            Q(name__icontains=q) | Q(description__icontains=q) | Q(engine_type__icontains=q)
        )

    strategies = strategies.order_by("name")

    return render(request, "habits/rule_strategy_list.html", {
        "strategies": strategies,
        "search_query": q,
    })


@rule_strategy_permission_required
def rule_strategy_create_view(request):
    """
    Master Data: Create a new Rule Strategy for the active tenant.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    if request.method == "POST":
        form = RuleStrategyForm(request.POST, tenant=tenant)
        if form.is_valid():
            strategy = form.save(commit=False)
            strategy.tenant = tenant
            strategy.save()
            messages.success(request, f'Rule Strategy "{strategy.name}" created successfully!')
            return redirect("rule_strategy_list")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = RuleStrategyForm(tenant=tenant)

    return render(request, "habits/rule_strategy_form.html", {
        "form": form,
        "action_title": "Create Rule Strategy",
        "submit_label": "Create Strategy",
    })


@rule_strategy_permission_required
def rule_strategy_update_view(request, pk):
    """
    Master Data: Edit an existing Rule Strategy. Strictly tenant-scoped.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    strategy = get_object_or_404(RuleStrategy, pk=pk, tenant=tenant)

    if request.method == "POST":
        form = RuleStrategyForm(request.POST, instance=strategy, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Rule Strategy "{strategy.name}" updated successfully!')
            return redirect("rule_strategy_list")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = RuleStrategyForm(instance=strategy, tenant=tenant)

    return render(request, "habits/rule_strategy_form.html", {
        "form": form,
        "strategy": strategy,
        "action_title": f'Edit Rule Strategy: "{strategy.name}"',
        "submit_label": "Save Changes",
    })


@rule_strategy_permission_required
def rule_strategy_delete_view(request, pk):
    """
    Master Data: Delete a Rule Strategy. Strictly tenant-scoped.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    strategy = get_object_or_404(RuleStrategy, pk=pk, tenant=tenant)
    habits_count = strategy.habits.count()

    if request.method == "POST":
        strategy_name = strategy.name
        strategy.delete()
        messages.success(request, f'Rule Strategy "{strategy_name}" was deleted successfully.')
        return redirect("rule_strategy_list")

    return render(request, "habits/rule_strategy_confirm_delete.html", {
        "strategy": strategy,
        "habits_count": habits_count,
    })

