def current_tenant(request):
    """
    Context processor providing current_tenant and available tenants to templates.
    """
    tenant = getattr(request, "tenant", None)
    if tenant:
        from django.db.models import Sum
        from habits.models import Habit
        tenant_pixels = Habit.objects.filter(tenant=tenant, is_template=False).aggregate(total=Sum("pixel_score"))["total"] or 0
        return {
            "current_tenant": tenant,
            "current_tenant_pixels": tenant_pixels,
        }
    return {
        "current_tenant": None,
        "current_tenant_pixels": 0,
    }
