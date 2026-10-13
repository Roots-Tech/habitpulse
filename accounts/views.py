from functools import wraps
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from .forms import AdminUserCreateForm, AdminUserEditForm, UserLoginForm, UserRegistrationForm

User = get_user_model()


def staff_required(view_func):
    """
    Decorator requiring user to be authenticated and have is_staff=True.
    Redirects anonymous visitors to login, raises 403 PermissionDenied for non-staff.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={request.path}")
        if not request.user.is_staff:
            raise PermissionDenied("Staff access required.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Explicitly specify the backend when logging in after registration
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, f"Welcome to Habit Tracker, {user.username}! Your personal workspace is ready.")
            return redirect("onboarding")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserRegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = UserLoginForm(request.POST)
        if form.is_valid():
            username_or_email = form.cleaned_data["username"]
            password = form.cleaned_data["password"]

            user = authenticate(request, username=username_or_email, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")

                # Redirect logic according to user journey:
                # No habits: first-time onboarding page
                # Existing habits: habit dashboard
                # Also honor ?next= parameter if safe
                next_url = request.GET.get("next")
                if next_url and next_url.startswith("/"):
                    return redirect(next_url)

                # Check if habits exist in the active tenant
                from habits.models import Habit
                tenant = getattr(request, "tenant", None)
                if tenant and Habit.objects.filter(tenant=tenant).exists():
                    return redirect("dashboard")
                else:
                    return redirect("onboarding")
            else:
                messages.error(request, "Invalid username/email or password.")
        else:
            messages.error(request, "Please enter your login credentials.")
    else:
        form = UserLoginForm()

    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("login")


@staff_required
def admin_users_list_view(request):
    """
    Admin panel view listing all users with essential details
    matching the ERP user view shown in the reference image.
    """
    search_query = request.GET.get("q", "").strip()
    users_qs = User.objects.all().order_by("-date_joined")

    if search_query:
        users_qs = users_qs.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )

    users_data = []
    for user in users_qs:
        membership = user.memberships.select_related("tenant").filter(status="ACTIVE").first()
        tenant = membership.tenant if membership else None
        habits_count = user.created_habits.count()

        # Status badge matching ERP style
        if user.is_superuser:
            status_label = "Superuser"
            status_class = "badge-staff"
        elif user.is_staff:
            status_label = "Staff"
            status_class = "badge-staff"
        elif user.last_login:
            status_label = "Confirmed"
            status_class = "badge-confirmed"
        else:
            status_label = "Never Connected"
            status_class = "badge-never-connected"

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
            "status_label": status_label,
            "status_class": status_class,
            "is_active": user.is_active,
        })

    total_count = User.objects.count()
    filtered_count = len(users_data)

    context = {
        "users": users_data,
        "search_query": search_query,
        "total_count": total_count,
        "filtered_count": filtered_count,
    }
    return render(request, "accounts/admin_users_list.html", context)


@staff_required
def admin_user_create_view(request):
    """
    Allows staff to provision a new user from the admin panel.
    """
    if request.method == "POST":
        form = AdminUserCreateForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            messages.success(request, f'User "{new_user.username}" created successfully with personal workspace!')
            return redirect("admin_users_list")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AdminUserCreateForm()

    return render(request, "accounts/admin_user_form.html", {"form": form})


@staff_required
def admin_user_edit_view(request, user_id):
    """
    Allows staff to edit a user's details, permissions, workspace name, or reset password.
    """
    target_user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        form = AdminUserEditForm(request.POST, instance=target_user)
        if form.is_valid():
            updated_user = form.save()
            messages.success(request, f'User "{updated_user.username}" updated successfully!')
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


@staff_required
@require_POST
def admin_user_delete_view(request, user_id):
    """
    Allows staff to delete a user and their associated data with safety protections.
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
