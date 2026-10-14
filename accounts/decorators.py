from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from .models import User


def super_admin_required(view_func):
    """
    Decorator requiring the user to be authenticated and have the Super Admin role.
    Super Admins have unrestricted access to frontend, backend, Admin Panel,
    user credentials, and database operations.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={request.path}")
        user = request.user
        if not (getattr(user, "role", None) == User.Role.SUPER_ADMIN or user.is_superuser):
            raise PermissionDenied("Access Denied: Super Admin role required to access the Admin Panel.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def technical_or_admin_required(view_func):
    """
    Decorator requiring the user to be a Technical User or Super Admin.
    Technical Users have access to all application features (Dashboard, Habits, Master Data CRUD).
    Regular Users are strictly restricted to their personal dashboard and habits.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={request.path}")
        user = request.user
        is_admin = getattr(user, "role", None) == User.Role.SUPER_ADMIN or user.is_superuser
        is_technical = getattr(user, "role", None) == User.Role.TECHNICAL_USER
        if not (is_admin or is_technical):
            raise PermissionDenied("Access Denied: Master data management requires Technical User or Super Admin privileges.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view
