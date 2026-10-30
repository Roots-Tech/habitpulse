import mimetypes
import os
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.utils._os import safe_join
from tenants.models import Membership


@login_required
def protected_media_view(request, path):
    """
    Secure multi-tenant media file serving view (SEC-03).
    Ensures:
    1. Only authenticated users can access uploaded media.
    2. Tenant evidence files (tenants/<tenant_slug>/evidence/...) are restricted
       strictly to active members of that specific tenant workspace or Super Admins.
    3. Blocks path traversal attacks via safe_join.
    4. Serves files with security headers (X-Content-Type-Options: nosniff).
    """
    # 1. Prevent directory traversal and normalize path
    try:
        full_path = safe_join(settings.MEDIA_ROOT, path)
    except SuspiciousFileOperation:
        raise Http404("Invalid file path.")

    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        raise Http404("Requested media file not found.")

    # 2. Multi-Tenant Authorization Check
    # Evidence files follow: tenants/<tenant_slug>/evidence/...
    normalized_rel = os.path.relpath(full_path, settings.MEDIA_ROOT).replace("\\", "/")
    parts = normalized_rel.split("/")

    if len(parts) >= 2 and parts[0] == "tenants":
        tenant_slug = parts[1]
        is_super = getattr(request.user, "is_super_admin", False) or request.user.is_superuser

        if not is_super:
            has_membership = Membership.objects.filter(
                user=request.user,
                tenant__slug=tenant_slug,
                status=Membership.Status.ACTIVE,
            ).exists()

            if not has_membership:
                return HttpResponseForbidden("Access denied: You do not have permission to view this workspace file.")

    # 3. Serve file securely
    content_type, _ = mimetypes.guess_type(full_path)
    content_type = content_type or "application/octet-stream"

    response = FileResponse(open(full_path, "rb"), content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=3600"
    return response
