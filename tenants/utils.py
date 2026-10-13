import uuid
from django.db import transaction
from django.utils.text import slugify
from .models import Tenant, Membership


@transaction.atomic
def create_personal_workspace_for_user(user, workspace_name=None):
    """
    Creates a personal workspace tenant for a user and assigns them as OWNER.
    This guarantees that every registered user has an isolated workspace ready.
    """
    if not workspace_name:
        workspace_name = f"{user.username}'s Personal Workspace"

    base_slug = slugify(user.username) or "workspace"
    slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"

    tenant = Tenant.objects.create(
        name=workspace_name,
        slug=slug,
    )

    membership = Membership.objects.create(
        user=user,
        tenant=tenant,
        role=Membership.Role.OWNER,
        status=Membership.Status.ACTIVE,
    )

    from habits.models import seed_default_master_data_for_tenant
    seed_default_master_data_for_tenant(tenant)

    return tenant, membership


def get_user_tenants(user):
    """
    Returns queryset of active tenants the user is a member of.
    """
    if not user.is_authenticated:
        return Tenant.objects.none()
    return Tenant.objects.filter(
        memberships__user=user,
        memberships__status=Membership.Status.ACTIVE,
    ).distinct()


def get_active_tenant_for_user(user, tenant_id=None):
    """
    Retrieves the designated tenant for the user, verifying active membership.
    """
    if not user.is_authenticated:
        return None

    qs = get_user_tenants(user)
    if tenant_id:
        tenant = qs.filter(id=tenant_id).first()
        if tenant:
            return tenant

    # Fallback to the first active tenant
    return qs.first()
