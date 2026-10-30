import logging
from typing import Optional
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


def create_bootstrap_admin(database_alias: str = "default") -> User:
    """
    Creates an initial temporary bootstrap administrator ('admin' / 'admin')
    to enable zero-terminal first-time access to a freshly created database.
    This temporary account exists solely to allow logging in and clicking 'Add Admin Data',
    which permanently deletes this account upon completion (self-destruction).
    """
    User = get_user_model()
    existing = User.objects.using(database_alias).filter(username__iexact="admin").first()
    if existing:
        return existing

    user = User.objects.using(database_alias).create(
        username="admin",
        email="admin@habitpulse.local",
        first_name="Bootstrap",
        last_name="Admin",
        role=User.Role.SUPER_ADMIN,
        is_superuser=True,
        is_staff=True,
        is_active=True,
        must_reset_password=False,
    )
    user.set_password("admin")
    user.save(using=database_alias)

    create_personal_workspace_for_user(user, workspace_name="Admin Setup Workspace")
    logger.info("Created temporary bootstrap administrator 'admin' on database '%s'", database_alias)
    return user


def are_admin_accounts_seeded() -> bool:
    """
    Evaluates whether all baseline administrative accounts are already provisioned.
    Used to hide the setup action from UI and block duplicate/conflicting provisioning attempts.
    """
    target_usernames = [acc["username"] for acc in INITIAL_ADMIN_PROFILES]
    existing_count = User.objects.filter(username__in=target_usernames).count()
    return existing_count >= len(target_usernames)


@transaction.atomic
def seed_admin_accounts(
    common_password: str,
    require_reset: bool = True,
    allow_overwrite: bool = False,
    executing_user: Optional[User] = None,
) -> dict:
    """
    Seeds/provisions baseline administrative accounts using a common initial password
    provided on demand by the Super Admin, flagging them to reset on first login.
    Strictly non-destructive: never purges pre-existing customer users or customer workspaces.
    Blocks duplicate execution unless allow_overwrite is explicitly set to True.

    If executing_user is provided and matches an existing account (e.g. Shrinath_jayakumar),
    their password and reset flags are preserved to avoid clobbering active sessions.

    If a temporary bootstrap 'admin' user exists, it is permanently deleted upon completion,
    achieving clean self-destruction so no default credentials remain active.
    """
    if not allow_overwrite and are_admin_accounts_seeded():
        raise ValueError(
            "Admin accounts have already been provisioned in this instance. "
            "Re-seeding is restricted to prevent overwriting existing user credentials."
        )

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
            # Check if this user is the one currently logged in (executing this request)
            is_executing = executing_user and (
                getattr(executing_user, "id", None) == user.id or
                executing_user.username.lower() == user.username.lower()
            )
            user.username = username
            user.email = email
            user.first_name = acc["first_name"]
            user.last_name = acc["last_name"]
            user.role = role
            user.is_active = True
            # Never overwrite credentials or force reset on the currently executing admin!
            if not is_executing:
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

    # SELF-DESTRUCTION: Look for temporary bootstrap 'admin' account
    bootstrap_deleted = False
    bootstrap_admin = User.objects.filter(username__iexact="admin").first()
    if bootstrap_admin:
        admin_usernames = [a["username"].lower() for a in INITIAL_ADMIN_PROFILES]
        if bootstrap_admin.username.lower() not in admin_usernames:
            logger.info("Self-destructing temporary bootstrap admin account '%s'", bootstrap_admin.username)
            bootstrap_admin.delete()
            bootstrap_deleted = True

    return {
        "created": created_users,
        "updated": updated_users,
        "total": len(INITIAL_ADMIN_PROFILES),
        "bootstrap_deleted": bootstrap_deleted,
    }
