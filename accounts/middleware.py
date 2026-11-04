from accounts.models import User


class AdminViewModeMiddleware:
    """
    Middleware that manages the Admin / Regular User View Mode toggle for Super Admins.
    Allows Super Admins (like Shrinath) to preview the entire application as a Regular User
    without modifying their database credentials, permissions, or access records.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, "user") and request.user.is_authenticated:
            # Check real database role
            is_real_super = (
                request.user.role == User.Role.SUPER_ADMIN or
                request.user.is_superuser
            )
            request.is_real_super_admin = is_real_super

            if is_real_super:
                view_mode = request.session.get("admin_view_mode", "admin")
                request.admin_view_mode = view_mode
                request.is_user_view_mode = (view_mode == "user")
                if request.is_user_view_mode:
                    request.user._preview_mode = "user"
                else:
                    request.user._preview_mode = "admin"
            else:
                request.admin_view_mode = "user"
                request.is_user_view_mode = False
                request.user._preview_mode = None
        else:
            request.is_real_super_admin = False
            request.admin_view_mode = "admin"
            request.is_user_view_mode = False

        return self.get_response(request)

