from .utils import get_active_tenant_for_user


class TenantMiddleware:
    """
    Middleware that identifies and attaches the active tenant to the request.
    Validates that the authenticated user actually has an active membership
    in the selected tenant, preventing tenant spoofing.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            session_tenant_id = request.session.get("active_tenant_id")
            tenant = get_active_tenant_for_user(request.user, session_tenant_id)
            if tenant:
                request.tenant = tenant
                request.session["active_tenant_id"] = tenant.id
            else:
                request.tenant = None
        else:
            request.tenant = None

        return self.get_response(request)
