import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from tenants.models import Tenant, Membership
from tenants.utils import create_personal_workspace_for_user, get_active_tenant_for_user

logger = logging.getLogger(__name__)
User = get_user_model()

ADMIN_ACCOUNTS = [
    {
        "username": "Shrinath_jayakumar",
        "email": "shrinath_jayakumar@gmail.com",
        "first_name": "Shrinath",
        "last_name": "Jayakumar",
        "workspace_name": "Shrinath's Workspace",
        "password": "admin@123",
        "role": User.Role.SUPER_ADMIN,
    },
    {
        "username": "Akash_ps",
        "email": "akash_ps@gmail.com",
        "first_name": "Akash",
        "last_name": "P S",
        "workspace_name": "Akash's Workspace",
        "password": "admin@123",
        "role": User.Role.TECHNICAL_USER,
    },
    {
        "username": "Romy_fred",
        "email": "romy_fred@gmail.com",
        "first_name": "Romy",
        "last_name": "Fred",
        "workspace_name": "Romy's Workspace",
        "password": "admin@123",
        "role": User.Role.REGULAR_USER,
    },
]


class Command(BaseCommand):
    help = "Configures access-based user accounts with designated roles and passwords."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Setting up access-based user roles..."))
        target_usernames = [acc["username"] for acc in ADMIN_ACCOUNTS]

        # 1. Provision or update each of the 3 specified admin users
        for acc in ADMIN_ACCOUNTS:
            username = acc["username"]
            email = acc["email"]
            password = acc["password"]
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
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Updated user '{username}' (Role: {user.get_role_display()})"))
            else:
                user = User.objects.create(
                    username=username,
                    email=email,
                    first_name=acc["first_name"],
                    last_name=acc["last_name"],
                    role=role,
                    is_active=True,
                )
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Created user '{username}' (Role: {user.get_role_display()})"))

            # Ensure workspace exists
            tenant = get_active_tenant_for_user(user)
            if not tenant:
                tenant, _ = create_personal_workspace_for_user(user, workspace_name=workspace_name)
                self.stdout.write(self.style.SUCCESS(f"  -> Created personal workspace: '{tenant.name}'"))
            else:
                tenant.name = workspace_name
                tenant.save(update_fields=["name"])
                self.stdout.write(self.style.SUCCESS(f"  -> Workspace set to: '{tenant.name}'"))

        # 2. Seed default master data (Categories and Rule Strategies) for all active tenants
        from habits.models import seed_default_master_data_for_tenant
        for tenant in Tenant.objects.all():
            seed_default_master_data_for_tenant(tenant)
        self.stdout.write(self.style.SUCCESS("Seeded default master data for all active workspaces."))

        # Verify configured admin users
        configured_users = list(User.objects.filter(username__in=target_usernames).values_list("username", "is_superuser"))
        self.stdout.write(self.style.SUCCESS(
            f"Successfully configured {len(configured_users)} admin accounts: {configured_users}"
        ))
