import logging
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from tenants.models import Tenant
from tenants.utils import create_personal_workspace_for_user, get_active_tenant_for_user
from habits.models import seed_default_master_data_for_tenant

logger = logging.getLogger(__name__)
User = get_user_model()

INITIAL_ADMIN_PROFILES = [
    {
        "username": "Shrinath_jayakumar",
        "email": "shrinath_jayakumar@gmail.com",
        "first_name": "Shrinath",
        "last_name": "Jayakumar",
        "workspace_name": "Shrinath's Workspace",
        "role": User.Role.SUPER_ADMIN,
    },
    {
        "username": "Akash_ps",
        "email": "akash_ps@gmail.com",
        "first_name": "Akash",
        "last_name": "P S",
        "workspace_name": "Akash's Workspace",
        "role": User.Role.TECHNICAL_USER,
    },
    {
        "username": "Romy_fred",
        "email": "romy_fred@gmail.com",
        "first_name": "Romy",
        "last_name": "Fred",
        "workspace_name": "Romy's Workspace",
        "role": User.Role.REGULAR_USER,
    },
]


@transaction.atomic
def seed_admin_accounts(common_password: str, require_reset: bool = True):
    """
    Seeds/provisions baseline administrative accounts using a common initial password
    provided on demand by the Super Admin, flagging them to reset on first login.
    Strictly non-destructive: never purges pre-existing users or workspaces.
    """
    if not common_password or len(common_password) < 6:
        raise ValueError("Common initial password must be at least 6 characters.")

    created_users = []
    updated_users = []

    for acc in INITIAL_ADMIN_PROFILES:
        username = acc["username"]
        email = acc["email"]
        workspace_name = acc["workspace_name"]
        role = acc.get("role", User.Role.REGULAR_USER)

        user = User.objects.filter(
            Q(username__iexact=username) | Q(email__iexact=email)
        ).first()

        if user:
            user.username = username
            user.email = email
            user.first_name = acc["first_name"]
            user.last_name = acc["last_name"]
            user.role = role
            user.is_active = True
            user.set_password(common_password)
            user.must_reset_password = require_reset
            user.save()
            updated_users.append(username)
        else:
            user = User.objects.create(
                username=username,
                email=email,
                first_name=acc["first_name"],
                last_name=acc["last_name"],
                role=role,
                is_active=True,
                must_reset_password=require_reset,
            )
            user.set_password(common_password)
            user.save()
            created_users.append(username)

        # Ensure personal workspace exists
        tenant = get_active_tenant_for_user(user)
        if not tenant:
            tenant, _ = create_personal_workspace_for_user(user, workspace_name=workspace_name)
        else:
            tenant.name = workspace_name
            tenant.save(update_fields=["name"])

    # Seed master data for all active workspaces
    for tenant in Tenant.objects.all():
        seed_default_master_data_for_tenant(tenant)

    return {
        "created": created_users,
        "updated": updated_users,
        "total": len(INITIAL_ADMIN_PROFILES),
    }
