import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
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
    PixelAllocation,
    PixelWallet,
    RuleStrategy,
    seed_default_catalog_habits,
    seed_default_master_data_for_tenant,
)
from .services import (
    calculate_completion_rate,
    calculate_streaks,
    calculate_user_pixel_wallet,
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

    if request.user.is_super_admin:
        if Habit.objects.filter(is_template=False).exists():
            return redirect("dashboard")
    else:
        if Habit.objects.filter(tenant=tenant, is_template=False).exists():
            return redirect("dashboard")

    return render(request, "habits/onboarding.html")


@login_required
def pixel_wallet_view(request):
    """
    Dedicated view for the user's Pixel Wallet and Pixels Plan, featuring 2 sections:
    1. Pixel Wallet:
       - Monthly pixel allocation, current energized balance, and health percentage
       - Daily risk outcome and dynamic outcome projection
       - Habit-by-habit pixel score and cycle breakdown
       - Gamification mechanics and streak preservation guidelines
    2. Pixels Plan:
       - Forward-looking capacity planner & strategic horizon
       - Weekly day-of-week commitment distribution schedule
       - Category allocation & strategic focus distribution
       - Milestone targets & pixel progression ranks
       - Interactive goal calculator & simulator
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        membership = request.user.memberships.select_related("tenant").filter(status="ACTIVE").first()
        tenant = membership.tenant if membership else None

    today = timezone.localdate()

    if tenant:
        user_habits_qs = Habit.objects.filter(tenant=tenant, is_template=False).order_by("-is_active", "name")
    else:
        user_habits_qs = Habit.objects.filter(created_by=request.user, is_template=False).order_by("-is_active", "name")

    habits_count = user_habits_qs.count()
    active_habits = [h for h in user_habits_qs if h.is_active]
    total_pixels = sum(h.pixel_score for h in active_habits)
    wallet_data = calculate_user_pixel_wallet(request.user, tenant=tenant, today=today, habits_qs=user_habits_qs)

    # -------------------------------------------------------------
    # Pixels Plan Data Computations
    # -------------------------------------------------------------
    # 1. Day of Week Planning Distribution (0=Mon, ..., 6=Sun)
    weekday_labels = [
        ("Monday", "Mon", 0),
        ("Tuesday", "Tue", 1),
        ("Wednesday", "Wed", 2),
        ("Thursday", "Thu", 3),
        ("Friday", "Fri", 4),
        ("Saturday", "Sat", 5),
        ("Sunday", "Sun", 6),
    ]
    weekly_plan = []
    for full_name, short_name, day_idx in weekday_labels:
        day_habits = [
            h for h in active_habits
            if (h.frequency == Habit.Frequency.DAILY or 
                (h.frequency == Habit.Frequency.WEEKDAYS and day_idx in (h.selected_weekdays or [])))
        ]
        day_pixels = sum(h.pixel_score for h in day_habits)
        weekly_plan.append({
            "full_name": full_name,
            "short_name": short_name,
            "day_idx": day_idx,
            "habits_count": len(day_habits),
            "pixels": day_pixels,
            "is_today": today.weekday() == day_idx,
            "habits": day_habits,
        })

    # 2. Category Distribution Plan
    category_plan_dict = defaultdict(lambda: {"pixels": 0, "habits_count": 0, "habits": []})
    for h in active_habits:
        cat_name = h.category or (h.category_ref.name if getattr(h, "category_ref", None) else "General")
        category_plan_dict[cat_name]["pixels"] += h.pixel_score
        category_plan_dict[cat_name]["habits_count"] += 1
        category_plan_dict[cat_name]["habits"].append(h)

    category_plan = [
        {
            "name": k,
            "pixels": v["pixels"],
            "habits_count": v["habits_count"],
            "habits": v["habits"],
            "percent": round((v["pixels"] / total_pixels * 100), 1) if total_pixels > 0 else 0,
        }
        for k, v in category_plan_dict.items()
    ]
    category_plan.sort(key=lambda x: x["pixels"], reverse=True)

    # 3. Monthly & Annual Projections for Pixels Plan
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    monthly_plan_capacity = total_pixels * days_in_month
    annual_plan_capacity = total_pixels * 365

    # 4. Next Routined Allocation Date & Projections
    if today.month == 12:
        next_cycle_year = today.year + 1
        next_cycle_month = 1
    else:
        next_cycle_year = today.year
        next_cycle_month = today.month + 1

    next_allocation_date = date(next_cycle_year, next_cycle_month, 1)
    days_until_next_allocation = (next_allocation_date - today).days
    days_in_next_month = calendar.monthrange(next_cycle_year, next_cycle_month)[1]
    supposed_allocation_pixels = total_pixels * days_in_next_month
    current_preserved_pixels = wallet_data.get("current_balance", 0)
    projected_rollover_if_100_percent = wallet_data.get("allocated_pixels", 0) + supposed_allocation_pixels
    projected_rollover_current = current_preserved_pixels + supposed_allocation_pixels

    # 5. Detailed Pixel Allocation Sources Ledger (How, Why & When each pixel was allocated)
    # Note: User is not supposed to know if it was individual admin allocation, just say 'Habit Bonus'
    allocation_sources = []
    for item in wallet_data.get("habits_breakdown", []):
        h = item["habit"]
        cat_name = h.category or (h.category_ref.name if getattr(h, "category_ref", None) else "General")
        allocation_sources.append({
            "source_type": "Habit Allocation",
            "icon": "📋",
            "title": h.name,
            "amount": item["allocated_pixels"],
            "daily_score": item["daily_score"],
            "pending_days": item["pending_days"],
            "how": f"{item['daily_score']} Px/day × {item['pending_days']} cycle days credited at habit registration",
            "why": f"{h.get_habit_type_display()} routine in {cat_name} category",
            "when": getattr(h, "created_at", None),
            "when_date": h.start_date,
            "badge_color": "var(--primary)",
            "status": f"{item['retained_pixels']} Px Retained ({item['missed_days']} missed)",
        })

    # Bonus allocations (abstracted as Habit Bonus)
    admin_alloc_qs = PixelAllocation.objects.filter(recipient_user=request.user)
    if tenant:
        admin_alloc_qs = admin_alloc_qs.filter(tenant=tenant)
    admin_alloc_qs = admin_alloc_qs.order_by("-created_at")

    for alloc in admin_alloc_qs:
        allocation_sources.append({
            "source_type": "Habit Bonus",
            "icon": "✨",
            "title": "Habit Bonus",
            "amount": alloc.amount,
            "daily_score": None,
            "pending_days": None,
            "how": "Bonus pixel allocation credited to your active wallet balance",
            "why": alloc.reason or "Habit achievement & consistency bonus",
            "when": alloc.created_at,
            "when_date": alloc.created_at.date() if alloc.created_at else today,
            "badge_color": "#10b981",
            "status": "Credited to Wallet",
        })

    total_gross_allocated = sum(s["amount"] for s in allocation_sources)

    # 6. Daily Pixel Progress Graph Data
    month_start = date(today.year, today.month, 1)
    month_completions = HabitCompletion.objects.filter(
        habit__in=active_habits,
        completion_date__gte=month_start,
        completion_date__lte=today,
    ).values("habit_id", "completion_date")

    completed_by_date = defaultdict(set)
    for c in month_completions:
        completed_by_date[c["completion_date"]].add(c["habit_id"])

    daily_progress_graph = []
    max_day_pixels = max(total_pixels, 1)
    month_earned_pixels = 0
    month_missed_pixels = 0
    running_earned = 0
    running_scheduled = 0
    running_missed = 0

    for d_num in range(1, days_in_month + 1):
        d = date(today.year, today.month, d_num)
        is_past = d < today
        is_current = d == today
        is_future = d > today

        scheduled_habits = [h for h in active_habits if h.is_scheduled_for_date(d)]
        scheduled_px = sum(h.pixel_score for h in scheduled_habits)
        if scheduled_px > max_day_pixels:
            max_day_pixels = scheduled_px

        running_scheduled += scheduled_px

        if not is_future:
            completed_ids = completed_by_date.get(d, set())
            completed_px = sum(h.pixel_score for h in scheduled_habits if h.id in completed_ids)
            missed_px = max(0, scheduled_px - completed_px)
            month_earned_pixels += completed_px
            month_missed_pixels += missed_px
            running_earned += completed_px
            running_missed += missed_px
            cum_earned = running_earned
            cum_missed = running_missed
        else:
            completed_px = 0
            missed_px = 0
            cum_earned = None
            cum_missed = None

        # Percentage heights for visual stacked bar
        completed_pct = round((completed_px / max_day_pixels * 100), 1) if max_day_pixels > 0 else 0
        missed_pct = round((missed_px / max_day_pixels * 100), 1) if max_day_pixels > 0 else 0
        scheduled_pct = round((scheduled_px / max_day_pixels * 100), 1) if max_day_pixels > 0 else 0

        daily_progress_graph.append({
            "day": d_num,
            "date": d,
            "date_str": d.strftime("%b %d"),
            "weekday_short": d.strftime("%a")[:2],
            "scheduled_px": scheduled_px,
            "completed_px": completed_px,
            "missed_px": missed_px,
            "cum_earned": cum_earned,
            "cum_scheduled": running_scheduled,
            "cum_missed": cum_missed,
            "is_past": is_past,
            "is_today": is_current,
            "is_future": is_future,
            "completed_pct": completed_pct,
            "missed_pct": missed_pct,
            "scheduled_pct": scheduled_pct,
            "status": "completed" if (completed_px == scheduled_px and scheduled_px > 0) else ("partial" if completed_px > 0 else ("missed" if missed_px > 0 else "rest")),
        })

    progress_graph_json = json.dumps([
        {
            "day": item["day"],
            "date_str": item["date_str"],
            "weekday": item["weekday_short"],
            "scheduled_px": item["scheduled_px"],
            "completed_px": item["completed_px"],
            "missed_px": item["missed_px"],
            "cum_earned": item["cum_earned"],
            "cum_scheduled": item["cum_scheduled"],
            "cum_missed": item["cum_missed"],
            "is_past": item["is_past"],
            "is_today": item["is_today"],
            "is_future": item["is_future"],
            "status": item["status"],
        }
        for item in daily_progress_graph
    ])

    # 7. Milestone Ranks
    current_balance = wallet_data.get("current_balance", 0)
    milestones = [
        {"name": "Bronze Pioneer", "target": 100, "icon": "🥉", "desc": "Establish basic habit rhythm"},
        {"name": "Silver Builder", "target": 300, "icon": "🥈", "desc": "Solid monthly consistency"},
        {"name": "Gold Master", "target": 600, "icon": "🥇", "desc": "High energy discipline"},
        {"name": "Diamond Legend", "target": 1200, "icon": "💎", "desc": "Unstoppable habit mastery"},
    ]
    for m in milestones:
        m["completed"] = current_balance >= m["target"]
        m["progress_percent"] = min(100, round((current_balance / m["target"]) * 100, 1)) if m["target"] > 0 else 100

    active_section = request.GET.get("section", "wallet")
    if active_section not in ["wallet", "plan"]:
        active_section = "wallet"

    raw_tab = request.GET.get("tab", "1")
    try:
        active_tab = int(raw_tab)
        if active_tab < 1 or active_tab > 6:
            active_tab = 1
    except (ValueError, TypeError):
        active_tab = 1

    context = {
        "tenant": tenant,
        "habits_count": habits_count,
        "active_habits_count": len(active_habits),
        "total_pixels": total_pixels,
        "user_habits": user_habits_qs,
        "wallet_data": wallet_data,
        "today": today,
        "days_in_month": days_in_month,
        "monthly_plan_capacity": monthly_plan_capacity,
        "annual_plan_capacity": annual_plan_capacity,
        "weekly_plan": weekly_plan,
        "category_plan": category_plan,
        "milestones": milestones,
        "next_allocation_date": next_allocation_date,
        "days_until_next_allocation": days_until_next_allocation,
        "days_in_next_month": days_in_next_month,
        "supposed_allocation_pixels": supposed_allocation_pixels,
        "next_cycle_pixels": supposed_allocation_pixels,
        "current_preserved_pixels": current_preserved_pixels,
        "projected_rollover_if_100_percent": projected_rollover_if_100_percent,
        "projected_rollover_current": projected_rollover_current,
        "projected_rollover_balance": projected_rollover_current,
        "allocation_sources": allocation_sources,
        "total_gross_allocated": total_gross_allocated,
        "daily_progress_graph": daily_progress_graph,
        "progress_graph_json": progress_graph_json,
        "max_day_pixels": max_day_pixels,
        "month_earned_pixels": month_earned_pixels,
        "month_missed_pixels": month_missed_pixels,
        "active_section": active_section,
        "active_tab": active_tab,
    }
    return render(request, "habits/pixel_wallet.html", context)


@login_required
def habit_list_view(request):
    """
    Displays the Habits Hub with 3 separate sections:
    1. My Habit List: Active habits tracked by the user in their workspace (Super Admin sees all habits across all users).
    2. Predefined Purposeful Habits: Curated goal-oriented habits created by super admin or technical users.
    3. Expert Prescribed Habits: Scientifically designed routines created by super admin or technical users.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    scope = request.GET.get("scope", "all" if request.user.is_super_admin else "my")
    all_habits_count = Habit.objects.filter(is_template=False).count()
    my_personal_habits_count = Habit.objects.filter(tenant=tenant, is_template=False).count()

    # 1. My Habit List (non-template habits tracked in user's workspace or system-wide for admin)
    if request.user.is_super_admin and scope != "my":
        my_habits = Habit.objects.filter(is_template=False).select_related("created_by", "tenant").order_by("-is_active", "name")
    else:
        my_habits = Habit.objects.filter(tenant=tenant, is_template=False).order_by("-is_active", "name")

    # Track which catalog templates this user has already added
    adopted_template_ids = set(
        Habit.objects.filter(tenant=tenant, is_template=False, template_source__isnull=False)
        .values_list("template_source_id", flat=True)
    )

    # 2. Predefined Purposeful Habits (catalog templates)
    predefined_habits = Habit.objects.filter(
        is_template=True,
        habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
        is_active=True,
    ).order_by("name")

    # 3. Expert Prescribed Habits (catalog templates)
    expert_habits = Habit.objects.filter(
        is_template=True,
        habit_type=Habit.HabitType.EXPERT_PRESCRIBED,
        is_active=True,
    ).order_by("name")

    can_manage_templates = bool(
        request.user.is_authenticated and (request.user.is_super_admin or request.user.is_technical_user)
    )

    active_tab = request.GET.get("tab", "user_created")
    if active_tab not in ["user_created", "predefined", "expert"]:
        active_tab = "user_created"

    return render(request, "habits/habit_list.html", {
        "my_habits": my_habits,
        "predefined_habits": predefined_habits,
        "expert_habits": expert_habits,
        "adopted_template_ids": adopted_template_ids,
        "can_manage_templates": can_manage_templates,
        "scope": scope,
        "all_habits_count": all_habits_count,
        "my_personal_habits_count": my_personal_habits_count,
        "active_tab": active_tab,
    })


@login_required
def habit_create_view(request):
    """
    Creates a new habit in the active tenant workspace or publishes a catalog template.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    requested_type = request.GET.get("type") or Habit.HabitType.GENERAL
    is_template_req = request.GET.get("template") in ["1", "true", "True"]
    is_admin_or_tech = bool(request.user.is_super_admin or request.user.is_technical_user)

    if not is_admin_or_tech:
        requested_type = Habit.HabitType.GENERAL
        is_template_req = False

    if request.method == "POST":
        idempotency_key = request.POST.get("idempotency_key", "").strip()
        submitted_name = request.POST.get("name", "").strip()

        # 1. Immediate idempotency check by submission key
        if idempotency_key:
            existing_by_key = Habit.objects.filter(idempotency_key=idempotency_key).first()
            if existing_by_key:
                if existing_by_key.is_template:
                    messages.success(request, f'Catalog template "{existing_by_key.name}" published successfully! Users can now add it to their habit list.')
                    return redirect("habit_list")
                else:
                    messages.success(request, f'Habit "{existing_by_key.name}" created successfully!')
                    return redirect("dashboard")

        # 2. Rapid duplicate check (multi-click within last 15 seconds)
        if submitted_name:
            recent_duplicate = Habit.objects.filter(
                tenant=tenant,
                created_by=request.user,
                name__iexact=submitted_name,
                is_active=True,
                created_at__gte=timezone.now() - timezone.timedelta(seconds=15),
            ).first()
            if recent_duplicate:
                if recent_duplicate.is_template:
                    messages.success(request, f'Catalog template "{recent_duplicate.name}" published successfully! Users can now add it to their habit list.')
                    return redirect("habit_list")
                else:
                    messages.success(request, f'Habit "{recent_duplicate.name}" created successfully!')
                    return redirect("dashboard")

        form = HabitForm(
            request.POST,
            tenant=tenant,
            user=request.user,
            habit_type_initial=requested_type,
            is_template_initial=is_template_req,
        )
        if form.is_valid():
            try:
                with transaction.atomic():
                    habit = form.save(commit=False)
                    habit.tenant = tenant
                    habit.created_by = request.user
                    if not is_admin_or_tech:
                        habit.habit_type = Habit.HabitType.GENERAL
                        habit.is_template = False
                    if idempotency_key:
                        habit.idempotency_key = idempotency_key
                    habit.save()
            except IntegrityError:
                # Concurrent submission collision caught by unique idempotency key or database constraint
                existing = None
                if idempotency_key:
                    existing = Habit.objects.filter(idempotency_key=idempotency_key).first()
                if not existing and submitted_name:
                    existing = Habit.objects.filter(tenant=tenant, name__iexact=submitted_name, is_active=True).first()
                if existing:
                    if existing.is_template:
                        messages.success(request, f'Catalog template "{existing.name}" published successfully! Users can now add it to their habit list.')
                        return redirect("habit_list")
                    else:
                        messages.success(request, f'Habit "{existing.name}" created successfully!')
                        return redirect("dashboard")
                raise

            if habit.is_template:
                messages.success(request, f'Catalog template "{habit.name}" published successfully! Users can now add it to their habit list.')
                return redirect("habit_list")
            else:
                messages.success(request, f'Habit "{habit.name}" created successfully!')
                return redirect("dashboard")
        else:
            # Check if validation failed because an identical habit was created concurrently
            existing = None
            if idempotency_key:
                existing = Habit.objects.filter(idempotency_key=idempotency_key).first()
            if not existing and submitted_name:
                existing = Habit.objects.filter(
                    tenant=tenant,
                    created_by=request.user,
                    name__iexact=submitted_name,
                    is_active=True,
                    created_at__gte=timezone.now() - timezone.timedelta(seconds=15),
                ).first()

            if existing:
                if existing.is_template:
                    messages.success(request, f'Catalog template "{existing.name}" published successfully! Users can now add it to their habit list.')
                    return redirect("habit_list")
                else:
                    messages.success(request, f'Habit "{existing.name}" created successfully!')
                    return redirect("dashboard")

            err_list = []
            for f_name, f_errs in form.errors.items():
                field_obj = form.fields.get(f_name)
                label = getattr(field_obj, "label", None) or f_name.replace("_", " ").title()
                for err in f_errs:
                    err_list.append(f"{label}: {err}")
            if err_list:
                messages.error(request, f"Please fix the following error(s): {'; '.join(err_list)}")
            else:
                messages.error(request, "Please fix the errors in the habit form.")
    else:
        form = HabitForm(
            tenant=tenant,
            user=request.user,
            habit_type_initial=requested_type,
            is_template_initial=is_template_req,
        )

    available_rule_strategies = RuleStrategy.objects.filter(tenant=tenant, is_active=True)

    action_title = "Create a New Habit"
    submit_label = "Create Habit"
    if is_admin_or_tech and is_template_req:
        if requested_type == Habit.HabitType.PREDEFINED_PURPOSE:
            action_title = "Publish a Predefined Purposeful Habit Template"
            submit_label = "Publish Predefined Habit"
        elif requested_type == Habit.HabitType.EXPERT_PRESCRIBED:
            action_title = "Publish an Expert Prescribed Habit Template"
            submit_label = "Publish Expert Habit"

    return render(request, "habits/habit_form.html", {
        "form": form,
        "available_rule_strategies": available_rule_strategies,
        "action_title": action_title,
        "submit_label": submit_label,
        "is_admin_or_tech": is_admin_or_tech,
    })


@login_required
def habit_update_view(request, pk):
    """
    Updates an existing habit or catalog template.
    Super Admins have full access to edit any habit across the system.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    habit = get_object_or_404(Habit, pk=pk)
    is_admin_or_tech = bool(request.user.is_super_admin or request.user.is_technical_user)

    if habit.is_template:
        if not is_admin_or_tech:
            raise PermissionDenied("Only Super Admins and Technical Users can edit catalog templates.")
    else:
        if habit.tenant != tenant and not request.user.is_super_admin:
            raise Http404("Habit not found in workspace.")

    target_tenant = habit.tenant if habit.tenant else tenant

    if request.method == "POST":
        form = HabitForm(request.POST, instance=habit, tenant=target_tenant, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Habit "{habit.name}" updated successfully!')
            if habit.is_template:
                return redirect("habit_list")
            return redirect("dashboard")
        else:
            err_list = []
            for f_name, f_errs in form.errors.items():
                field_obj = form.fields.get(f_name)
                label = getattr(field_obj, "label", None) or f_name.replace("_", " ").title()
                for err in f_errs:
                    err_list.append(f"{label}: {err}")
            if err_list:
                messages.error(request, f"Please fix the following error(s): {'; '.join(err_list)}")
            else:
                messages.error(request, "Please fix the errors below.")
    else:
        form = HabitForm(instance=habit, tenant=target_tenant, user=request.user)

    available_rule_strategies = RuleStrategy.objects.filter(tenant=target_tenant, is_active=True)

    action_title = f'Edit Template "{habit.name}"' if habit.is_template else f'Edit "{habit.name}"'
    return render(request, "habits/habit_form.html", {
        "form": form,
        "habit": habit,
        "available_rule_strategies": available_rule_strategies,
        "action_title": action_title,
        "submit_label": "Save Changes",
        "is_admin_or_tech": is_admin_or_tech,
    })


@login_required
@require_POST
def habit_adopt_view(request, pk):
    """
    Adopts a Predefined Purposeful or Expert Prescribed habit template from the catalog
    and adds it to the user's active habit list within their workspace.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    template_habit = get_object_or_404(Habit, pk=pk, is_template=True)

    # Check if already added in this workspace
    existing = Habit.objects.filter(
        tenant=tenant,
        template_source=template_habit,
        is_active=True,
    ).first()

    if existing:
        messages.info(request, f'You are already tracking "{existing.name}" in your habit list.')
        return redirect("habit_list")

    # Clone template habit into user's workspace
    try:
        with transaction.atomic():
            adopted_habit = Habit.objects.create(
                tenant=tenant,
                created_by=request.user,
                name=template_habit.name,
                description=template_habit.description,
                habit_type=template_habit.habit_type,
                is_template=False,
                template_source=template_habit,
                category=template_habit.category,
                category_ref=template_habit.category_ref,
                rule_strategy_ref=template_habit.rule_strategy_ref,
                validation_rule=template_habit.validation_rule,
                window_start_time=template_habit.window_start_time,
                window_end_time=template_habit.window_end_time,
                target_value=template_habit.target_value,
                unit_label=template_habit.unit_label,
                pixel_score=template_habit.pixel_score,
                frequency=template_habit.frequency,
                selected_weekdays=template_habit.selected_weekdays,
                start_date=timezone.localdate(),
                is_active=True,
            )
        messages.success(request, f'Habit "{adopted_habit.name}" has been added to your habit list!')
    except IntegrityError:
        # Concurrent adoption collision caught by unique constraint
        messages.info(request, f'You are already tracking "{template_habit.name}" in your habit list.')

    return redirect("habit_list")


@login_required
@require_POST
def habit_delete_view(request, pk):
    """
    Deletes a habit from workspace or removes a template.
    Super Admins can delete any habit across the entire system.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    habit = get_object_or_404(Habit, pk=pk)
    is_admin_or_tech = bool(request.user.is_super_admin or request.user.is_technical_user)

    if habit.is_template:
        if not is_admin_or_tech:
            raise PermissionDenied("Only Super Admins and Technical Users can delete catalog templates.")
    else:
        if habit.tenant != tenant and not request.user.is_super_admin:
            raise Http404("Habit not found in workspace.")

    name = habit.name
    habit.delete()
    messages.success(request, f'Habit "{name}" was deleted successfully.')
    return redirect("habit_list")


@login_required
@require_POST
def habit_toggle_active_view(request, pk):
    """
    Toggles the active status of a habit.
    Super Admins can toggle active status of any habit across the system.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    habit = get_object_or_404(Habit, pk=pk)
    is_admin_or_tech = bool(request.user.is_super_admin or request.user.is_technical_user)

    if habit.is_template:
        if not is_admin_or_tech:
            raise PermissionDenied("Only Super Admins and Technical Users can toggle catalog templates.")
    else:
        if habit.tenant != tenant and not request.user.is_super_admin:
            raise Http404("Habit not found in workspace.")

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
    Super Admins can complete any habit across the platform.
    Supports both HTMX/JSON and standard form submission.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

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
                tenant=habit.tenant,
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
    Undoes completion for today (or specified date).
    Super Admins can undo completion for any habit across the platform.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

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

    with transaction.atomic():
        deleted_count, _ = HabitCompletion.objects.filter(
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
    Super Admins can view calendar for any habit across the platform.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    if request.user.is_super_admin:
        habit = get_object_or_404(Habit, pk=pk)
    else:
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
    Super Admins can view stats for any habit across the platform.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    if request.user.is_super_admin:
        habit = get_object_or_404(Habit, pk=pk)
    else:
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
    Master Data: Lists all Habit Categories in the user's active workspace (or all for Super Admin).
    Supports search query (?q=).
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    if not HabitCategory.objects.filter(tenant=tenant).exists():
        seed_default_master_data_for_tenant(tenant)

    q = request.GET.get("q", "").strip()
    if request.user.is_super_admin:
        categories = HabitCategory.objects.all().annotate(
            total_habits=Count("habits")
        )
    else:
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
    Master Data: Edit an existing Habit Category.
    Super Admins can edit any category.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    category = get_object_or_404(HabitCategory, pk=pk) if request.user.is_super_admin else get_object_or_404(HabitCategory, pk=pk, tenant=tenant)
    target_tenant = category.tenant if category.tenant else tenant

    if request.method == "POST":
        form = HabitCategoryForm(request.POST, instance=category, tenant=target_tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Category "{category.name}" updated successfully!')
            return redirect("category_list")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = HabitCategoryForm(instance=category, tenant=target_tenant)

    return render(request, "habits/category_form.html", {
        "form": form,
        "category": category,
        "action_title": f'Edit Category: "{category.name}"',
        "submit_label": "Save Changes",
    })


@category_permission_required
def category_delete_view(request, pk):
    """
    Master Data: Delete a Habit Category.
    Super Admins can delete any category.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    category = get_object_or_404(HabitCategory, pk=pk) if request.user.is_super_admin else get_object_or_404(HabitCategory, pk=pk, tenant=tenant)
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
    Master Data: Lists all Rule Strategies in the user's active workspace (or all for Super Admin).
    Supports search query (?q=).
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    if not RuleStrategy.objects.filter(tenant=tenant).exists():
        seed_default_master_data_for_tenant(tenant)

    q = request.GET.get("q", "").strip()
    if request.user.is_super_admin:
        strategies = RuleStrategy.objects.all().annotate(
            total_habits=Count("habits")
        )
    else:
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
    Master Data: Edit an existing Rule Strategy.
    Super Admins can edit any rule strategy across the platform.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    strategy = get_object_or_404(RuleStrategy, pk=pk) if request.user.is_super_admin else get_object_or_404(RuleStrategy, pk=pk, tenant=tenant)
    target_tenant = strategy.tenant if strategy.tenant else tenant

    if request.method == "POST":
        form = RuleStrategyForm(request.POST, instance=strategy, tenant=target_tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Rule Strategy "{strategy.name}" updated successfully!')
            return redirect("rule_strategy_list")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = RuleStrategyForm(instance=strategy, tenant=target_tenant)

    return render(request, "habits/rule_strategy_form.html", {
        "form": form,
        "strategy": strategy,
        "action_title": f'Edit Rule Strategy: "{strategy.name}"',
        "submit_label": "Save Changes",
    })


@rule_strategy_permission_required
def rule_strategy_delete_view(request, pk):
    """
    Master Data: Delete a Rule Strategy.
    Super Admins can delete any rule strategy across the platform.
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        raise Http404("Workspace not found.")

    strategy = get_object_or_404(RuleStrategy, pk=pk) if request.user.is_super_admin else get_object_or_404(RuleStrategy, pk=pk, tenant=tenant)
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

