from functools import wraps
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from .decorators import super_admin_required, technical_or_admin_required
from .forms import AdminUserCreateForm, AdminUserEditForm, UserLoginForm, UserRegistrationForm

User = get_user_model()


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Explicitly specify the backend when logging in after registration
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, f"Welcome to HabitPulse, {user.username}! Your personal workspace is ready.")
            return redirect("onboarding")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserRegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = UserLoginForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            username_or_email = form.cleaned_data["username"]
            password = form.cleaned_data["password"]

            # Support login with either username or email
            user = None
            if "@" in username_or_email:
                try:
                    user_obj = User.objects.get(email__iexact=username_or_email)
                    user = authenticate(request, username=user_obj.username, password=password)
                except User.DoesNotExist:
                    pass
            else:
                user = authenticate(request, username=username_or_email, password=password)

            if user is not None:
                if user.is_active:
                    login(request, user)
                    messages.success(request, f"Welcome back, {user.username}!")
                    next_url = request.GET.get("next") or request.POST.get("next")
                    if next_url:
                        return redirect(next_url)

                    # Check if habits exist in the active tenant
                    from habits.models import Habit
                    tenant = getattr(request, "tenant", None)
                    if tenant and Habit.objects.filter(tenant=tenant).exists():
                        return redirect("dashboard")
                    elif Habit.objects.filter(created_by=user).exists():
                        return redirect("dashboard")
                    else:
                        return redirect("onboarding")
                else:
                    messages.error(request, "This account is inactive. Please contact an administrator.")
            else:
                messages.error(request, "Invalid username/email or password.")

    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("login")


# ==============================================================================
# ADMIN PANEL: USER MANAGEMENT
# ==============================================================================

@super_admin_required
def admin_users_list_view(request):
    """
    Admin panel view listing all users with access roles and essential details.
    Strictly restricted to Super Admin.
    """
    search_query = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "").strip()

    users_qs = User.objects.all().order_by("-date_joined")

    if search_query:
        users_qs = users_qs.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )

    if role_filter in User.Role.values:
        if role_filter == User.Role.SUPER_ADMIN:
            users_qs = users_qs.filter(Q(role=User.Role.SUPER_ADMIN) | Q(is_superuser=True))
        else:
            users_qs = users_qs.filter(role=role_filter, is_superuser=False)

    users_data = []
    for user in users_qs:
        membership = user.memberships.select_related("tenant").filter(status="ACTIVE").first()
        tenant = membership.tenant if membership else None
        habits_count = user.created_habits.count()
        role_badge = user.get_role_badge()

        display_name = user.get_full_name() or user.username

        users_data.append({
            "id": user.id,
            "user": user,
            "display_name": display_name,
            "login": user.username,
            "email": user.email,
            "language": "English (US)",
            "last_login": user.last_login,
            "company": tenant.name if tenant else "Personal Workspace",
            "role": membership.role if membership else "Owner",
            "habits_count": habits_count,
            "role_badge": role_badge,
            "system_role": user.role,
            "is_active": user.is_active,
        })

    total_count = User.objects.count()
    filtered_count = len(users_data)

    context = {
        "users": users_data,
        "search_query": search_query,
        "role_filter": role_filter,
        "total_count": total_count,
        "filtered_count": filtered_count,
        "role_choices": User.Role.choices,
    }
    return render(request, "accounts/admin_users_list.html", context)


@super_admin_required
def admin_user_create_view(request):
    """
    Allows Super Admins to provision a new user and assign their access role.
    """
    if request.method == "POST":
        form = AdminUserCreateForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            messages.success(request, f'User "{new_user.username}" created successfully with role {new_user.get_role_display()}!')
            return redirect("admin_users_list")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AdminUserCreateForm()

    return render(request, "accounts/admin_user_form.html", {"form": form})


@super_admin_required
def admin_user_edit_view(request, user_id):
    """
    Allows Super Admins to edit a user's details, role, workspace name, or reset password.
    """
    target_user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        form = AdminUserEditForm(request.POST, instance=target_user)
        if form.is_valid():
            updated_user = form.save()
            messages.success(request, f'User "{updated_user.username}" updated successfully (Role: {updated_user.get_role_display()})!')
            return redirect("admin_users_list")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AdminUserEditForm(instance=target_user)

    membership = target_user.memberships.select_related("tenant").filter(status="ACTIVE").first()
    tenant = membership.tenant if membership else None
    habits_count = target_user.created_habits.count()

    return render(request, "accounts/admin_user_edit.html", {
        "form": form,
        "target_user": target_user,
        "tenant": tenant,
        "habits_count": habits_count,
    })


@super_admin_required
@require_POST
def admin_user_delete_view(request, user_id):
    """
    Allows Super Admins to delete a user and their associated data with safety protections.
    """
    target_user = get_object_or_404(User, pk=user_id)

    # Protect against self-deletion
    if target_user == request.user:
        messages.error(request, "Security protection: You cannot delete your own active administrator account.")
        return redirect("admin_users_list")

    username = target_user.username
    target_user.delete()
    messages.success(request, f'User "{username}" and their workspace data were permanently deleted.')
    return redirect("admin_users_list")


# ==============================================================================
# ADMIN PANEL: USER ROLES MANAGEMENT
# ==============================================================================

@super_admin_required
def admin_roles_list_view(request):
    """
    Admin panel view for User Roles Management.
    Displays detailed role specifications, permissions matrix,
    assigned users, and role management controls.
    """
    roles_config = [
        {
            "code": User.Role.SUPER_ADMIN,
            "name": "Super Admin",
            "icon": "👑",
            "badge_class": "badge-super-admin",
            "badge_color": "#c084fc",
            "badge_bg": "rgba(168, 85, 247, 0.15)",
            "level": "Level 1 — Full System Access",
            "description": (
                "Complete unrestricted access across all layers of the application: "
                "Frontend, Backend, Admin Panel, Database admin, user management, passwords, and sensitive settings."
            ),
            "permissions": [
                {"name": "Frontend Application & Dashboard", "allowed": True},
                {"name": "Create, View & Track Personal Habits", "allowed": True},
                {"name": "Master Data Management (Categories & Rule Strategies)", "allowed": True},
                {"name": "Admin Panel (Users & Roles Management)", "allowed": True},
                {"name": "User Passwords & Account Provisioning", "allowed": True},
                {"name": "Django Admin & Database Operations (/admin/)", "allowed": True},
            ],
            "users": User.objects.filter(Q(role=User.Role.SUPER_ADMIN) | Q(is_superuser=True)).order_by("username"),
        },
        {
            "code": User.Role.TECHNICAL_USER,
            "name": "Technical User",
            "icon": "🛠️",
            "badge_class": "badge-technical-user",
            "badge_color": "#38bdf8",
            "badge_bg": "rgba(56, 189, 248, 0.15)",
            "level": "Level 2 — Technical & Master Data",
            "description": (
                "Technical team members and developers who configure and operate application features: "
                "Full access to habits, master data (Categories & Rule Strategies), and features. "
                "Strictly restricted from the Admin Panel, user credentials, and database admin."
            ),
            "permissions": [
                {"name": "Frontend Application & Dashboard", "allowed": True},
                {"name": "Create, View & Track Personal Habits", "allowed": True},
                {"name": "Master Data Management (Categories & Rule Strategies)", "allowed": True},
                {"name": "Admin Panel (Users & Roles Management)", "allowed": False},
                {"name": "User Passwords & Account Provisioning", "allowed": False},
                {"name": "Django Admin & Database Operations (/admin/)", "allowed": False},
            ],
            "users": User.objects.filter(role=User.Role.TECHNICAL_USER, is_superuser=False).order_by("username"),
        },
        {
            "code": User.Role.REGULAR_USER,
            "name": "Regular User",
            "icon": "👤",
            "badge_class": "badge-regular-user",
            "badge_color": "#34d399",
            "badge_bg": "rgba(16, 185, 129, 0.15)",
            "level": "Level 3 — Personal Workspace Only",
            "description": (
                "Standard end users restricted strictly to their own personal dashboard and habits they have created. "
                "They select from pre-configured categories and strategies, but cannot modify master data or access administrative panels."
            ),
            "permissions": [
                {"name": "Frontend Application & Dashboard (Personal)", "allowed": True},
                {"name": "Create, View & Track Personal Habits", "allowed": True},
                {"name": "Master Data Management (Categories & Rule Strategies)", "allowed": False},
                {"name": "Admin Panel (Users & Roles Management)", "allowed": False},
                {"name": "User Passwords & Account Provisioning", "allowed": False},
                {"name": "Django Admin & Database Operations (/admin/)", "allowed": False},
            ],
            "users": User.objects.filter(role=User.Role.REGULAR_USER, is_superuser=False).order_by("username"),
        },
    ]

    all_users = User.objects.all().order_by("username")
    return render(request, "accounts/admin_roles_list.html", {
        "roles": roles_config,
        "all_users": all_users,
        "role_choices": User.Role.choices,
    })


@super_admin_required
@require_POST
def admin_user_role_change_view(request, user_id):
    """
    Quickly updates a user's role from the User Roles management view.
    """
    target_user = get_object_or_404(User, pk=user_id)
    new_role = request.POST.get("role")

    if new_role not in User.Role.values:
        messages.error(request, "Invalid role selection.")
        return redirect("admin_roles_list")

    # Safety check: Prevent demoting the only super admin
    if target_user == request.user and new_role != User.Role.SUPER_ADMIN:
        super_admin_count = User.objects.filter(Q(role=User.Role.SUPER_ADMIN) | Q(is_superuser=True)).count()
        if super_admin_count <= 1:
            messages.error(request, "Security protection: You cannot demote yourself as you are the only Super Admin.")
            return redirect("admin_roles_list")

    target_user.role = new_role
    target_user.save()
    messages.success(request, f'Updated role for "{target_user.username}" to {target_user.get_role_display()} successfully!')
    return redirect("admin_roles_list")
