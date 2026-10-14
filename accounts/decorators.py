from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from .models import User


def permission_required(perm_key):
    """
    Decorator requiring the user to have a specific permission granted
    either via their role or a user-level custom override.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"{reverse('login')}?next={request.path}")
            user = request.user
            if not user.has_perm_access(perm_key):
                raise PermissionDenied(f"Access Denied: Permission '{perm_key}' required to access this resource.")
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def super_admin_required(view_func):
    """
    Decorator requiring the user to be authenticated and have the Super Admin role
    or 'manage_roles' permission.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={request.path}")
        user = request.user
        if not (user.is_super_admin or user.can_manage_roles):
            raise PermissionDenied("Access Denied: Super Admin role required to access the Admin Panel.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def admin_users_required(view_func):
    """
    Decorator requiring the user to have permission to manage users.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={request.path}")
        user = request.user
        if not (user.is_super_admin or user.can_manage_users):
            raise PermissionDenied("Access Denied: User Accounts Management permission required.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def category_permission_required(view_func):
    """
    Decorator requiring the user to have permission to manage Habit Categories.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={request.path}")
        user = request.user
        if not (user.is_super_admin or user.can_manage_categories):
            raise PermissionDenied("Access Denied: Permission to manage Habit Categories required.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def rule_strategy_permission_required(view_func):
    """
    Decorator requiring the user to have permission to manage Rule Strategies.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={request.path}")
        user = request.user
        if not (user.is_super_admin or user.can_manage_rule_strategies):
            raise PermissionDenied("Access Denied: Permission to manage Rule Strategies required.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def technical_or_admin_required(view_func):
    """
    Decorator requiring the user to have Master Data permission (categories or rule strategies),
    or Technical/Super Admin privileges.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={request.path}")
        user = request.user
        if not (user.is_super_admin or user.can_manage_categories or user.can_manage_rule_strategies):
            raise PermissionDenied("Access Denied: Master data management requires Technical User or Super Admin privileges.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view
