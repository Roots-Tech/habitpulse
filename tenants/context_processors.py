def current_tenant(request):
    """
    Context processor providing current_tenant and available tenants to templates.
    """
    if hasattr(request, "tenant"):
        return {
            "current_tenant": request.tenant,
        }
    return {
        "current_tenant": None,
    }
