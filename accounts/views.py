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
from .models import RolePermission, UserPermissionOverride, PERMISSIONS_DEFINITIONS


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


def _handle_user_edit(request, target_user, is_super_admin, redirect_url):
    """
    Shared handler for user form views:
    - Super Admins can view and edit any user's profile, role, and system permissions.
    - Standard users can view their own profile and granted permissions/capabilities
      in read-only mode, but cannot make changes to roles or permissions.
    """
    is_self = (request.user.id == target_user.id)

    if request.method == "POST":
        form = AdminUserEditForm(request.POST, instance=target_user, is_super_admin=is_super_admin)
        if form.is_valid():
            updated_user = form.save()
            if is_super_admin:
                messages.success(request, f'User "{updated_user.username}" updated successfully (Role: {updated_user.get_role_display()})!')
            else:
                messages.success(request, "Your profile details have been saved successfully!")
            return redirect(redirect_url)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AdminUserEditForm(instance=target_user, is_super_admin=is_super_admin)

    membership = target_user.memberships.select_related("tenant").filter(status="ACTIVE").first()
    tenant = membership.tenant if membership else None

    from habits.models import Habit
    from habits.services import calculate_user_pixel_wallet
    from django.db.models import Sum

    if tenant:
        user_habits_qs = Habit.objects.filter(tenant=tenant, is_template=False).order_by("-is_active", "name")
    else:
        user_habits_qs = Habit.objects.filter(created_by=target_user, is_template=False).order_by("-is_active", "name")

    habits_count = user_habits_qs.count()
    total_pixels = user_habits_qs.aggregate(total=Sum("pixel_score"))["total"] or 0
    user_habits_list = list(user_habits_qs)
    wallet_data = calculate_user_pixel_wallet(target_user, tenant=tenant)

    override = getattr(target_user, "permission_override", None)
    has_custom = bool(override and override.enable_custom)

    user_permissions_data = []
    for defn in PERMISSIONS_DEFINITIONS:
        key = defn["key"]
        field_name = f"perm_{key}"
        user_permissions_data.append({
            "key": key,
            "label": defn["label"],
            "description": defn["description"],
            "menu": defn["menu"],
            "is_granted": target_user.has_perm_access(key),
            "field": form[field_name] if field_name in form.fields else None,
        })

    active_tab = request.GET.get("tab", "account")
    if active_tab not in ["account", "pixels", "permissions", "security"]:
        active_tab = "account"

    return render(request, "accounts/admin_user_edit.html", {
        "form": form,
        "target_user": target_user,
        "tenant": tenant,
        "habits_count": habits_count,
        "total_pixels": total_pixels,
        "user_habits": user_habits_list,
        "wallet_data": wallet_data,
        "is_super_admin": is_super_admin,
        "is_self": is_self,
        "user_permissions_data": user_permissions_data,
        "has_custom_override": has_custom,
        "active_tab": active_tab,
    })


@super_admin_required
def admin_user_edit_view(request, user_id):
    """
    Allows Super Admins to view and edit a user's details, role, workspace name,
    reset password, and customize system access permissions.
    """
    target_user = get_object_or_404(User, pk=user_id)
    return _handle_user_edit(
        request,
        target_user=target_user,
        is_super_admin=True,
        redirect_url="admin_users_list",
    )


def profile_view(request):
    """
    Profile and Access Capabilities view for the currently logged-in user.
    Standard users see what access they are provided and what they can do (read-only).
    Super Admins can view and edit their own profile and permissions.
    """
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={request.path}")
    return _handle_user_edit(
        request,
        target_user=request.user,
        is_super_admin=bool(request.user.is_super_admin),
        redirect_url="profile",
    )


def general_settings_view(request):
    """
    General Settings and Application Preferences view, accessible to all authenticated users.
    Displays theme options, workspace info, and pixel score breakdown.
    """
    if not request.user.is_authenticated:
        return redirect(f"{reverse('login')}?next={request.path}")

    membership = request.user.memberships.select_related("tenant").filter(status="ACTIVE").first()
    tenant = membership.tenant if membership else getattr(request, "tenant", None)

    from habits.models import Habit
    from habits.services import calculate_user_pixel_wallet
    from django.db.models import Sum

    if tenant:
        user_habits_qs = Habit.objects.filter(tenant=tenant, is_template=False).order_by("-is_active", "name")
    else:
        user_habits_qs = Habit.objects.filter(created_by=request.user, is_template=False).order_by("-is_active", "name")

    habits_count = user_habits_qs.count()
    total_pixels = user_habits_qs.aggregate(total=Sum("pixel_score"))["total"] or 0
    wallet_data = calculate_user_pixel_wallet(request.user, tenant=tenant)

    return render(request, "accounts/general_settings.html", {
        "tenant": tenant,
        "habits_count": habits_count,
        "total_pixels": total_pixels,
        "user_habits": list(user_habits_qs),
        "wallet_data": wallet_data,
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
# ADMIN PANEL: USER ROLES MANAGEMENT & CUSTOMIZABLE PERMISSIONS
# ==============================================================================

@super_admin_required
def admin_roles_list_view(request):
    """
    Admin panel view for User Roles Management.
    Displays detailed role specifications with customizable permission checkboxes,
    assigned users directory, and individual user permission overrides.
    """
    roles_meta = [
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
                "Can be granted or restricted from any page using the checkboxes below."
            ),
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
                "Super Admins can selectively check additional privileges to grant access to any page or menu."
            ),
            "users": User.objects.filter(role=User.Role.REGULAR_USER, is_superuser=False).order_by("username"),
        },
    ]

    roles_data = []
    for r in roles_meta:
        role_perm = RolePermission.get_for_role(r["code"])
        perm_dict = role_perm.to_dict()
        perms_list = []
        for defn in PERMISSIONS_DEFINITIONS:
            perms_list.append({
                "key": defn["key"],
                "label": defn["label"],
                "description": defn["description"],
                "menu": defn["menu"],
                "is_enabled": perm_dict.get(defn["key"], False),
            })
        roles_data.append({
            **r,
            "permissions": perms_list,
            "role_perm": role_perm,
        })

    all_users = User.objects.all().order_by("username").prefetch_related("permission_override", "memberships__tenant")
    user_rows = []
    for u in all_users:
        override = getattr(u, "permission_override", None)
        user_rows.append({
            "user": u,
            "override": override,
            "has_custom": bool(override and override.enable_custom),
            "user_perms": [
                {
                    "key": d["key"],
                    "label": d["label"],
                    "description": d["description"],
                    "menu": d["menu"],
                    "is_enabled": u.has_perm_access(d["key"]),
                    "override_enabled": getattr(override, d["key"], False) if override else False,
                }
                for d in PERMISSIONS_DEFINITIONS
            ]
        })

    return render(request, "accounts/admin_roles_list.html", {
        "roles": roles_data,
        "user_rows": user_rows,
        "permissions_definitions": PERMISSIONS_DEFINITIONS,
        "role_choices": User.Role.choices,
    })


@super_admin_required
@require_POST
def admin_role_permissions_update_view(request, role_code):
    """
    Updates the permissions matrix checkboxes for a specific system role.
    """
    if role_code not in User.Role.values:
        messages.error(request, "Invalid role selection.")
        return redirect("admin_roles_list")

    role_perm = RolePermission.get_for_role(role_code)
    for defn in PERMISSIONS_DEFINITIONS:
        key = defn["key"]
        # Super admin safeguard: keep manage_roles True for Super Admin
        if role_code == User.Role.SUPER_ADMIN and key == "manage_roles":
            setattr(role_perm, key, True)
        else:
            setattr(role_perm, key, key in request.POST)

    role_perm.save()
    messages.success(request, f'Configurable permissions for "{role_perm.get_role_display()}" saved successfully!')
    return redirect("admin_roles_list")


@super_admin_required
@require_POST
def admin_user_permissions_update_view(request, user_id):
    """
    Updates custom permission overrides for an individual user.
    Allows Super Admins to provide any specific user access to any page or menu.
    """
    target_user = get_object_or_404(User, pk=user_id)
    override, _ = UserPermissionOverride.objects.get_or_create(user=target_user)

    enable_custom = request.POST.get("enable_custom") in ["on", "true", "True", "1"]
    override.enable_custom = enable_custom

    for defn in PERMISSIONS_DEFINITIONS:
        key = defn["key"]
        setattr(override, key, key in request.POST)

    override.save()

    status_str = "Custom permissions applied" if enable_custom else "Reset to role default permissions"
    messages.success(request, f'{status_str} for user "{target_user.username}" successfully!')
    return redirect("admin_roles_list")


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
