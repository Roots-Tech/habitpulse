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
    },
    {
        "username": "Akash_ps",
        "email": "akash_ps@gmail.com",
        "first_name": "Akash",
        "last_name": "P S",
        "workspace_name": "Akash's Workspace",
        "password": "admin@123",
    },
    {
        "username": "Romy_fred",
        "email": "romy_fred@gmail.com",
        "first_name": "Romy",
        "last_name": "Fred",
        "workspace_name": "Romy's Workspace",
        "password": "admin@123",
    },
]


class Command(BaseCommand):
    help = "Configures exactly 3 superuser admin accounts (Shrinath_jayakumar, Akash_ps, Romy_fred) with password admin@123 and prunes all other users."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Setting up exact 3 admin superuser accounts..."))
        target_usernames = [acc["username"] for acc in ADMIN_ACCOUNTS]

        # 1. Provision or update each of the 3 specified admin users
        for acc in ADMIN_ACCOUNTS:
            username = acc["username"]
            email = acc["email"]
            password = acc["password"]
            workspace_name = acc["workspace_name"]

            user = User.objects.filter(
                Q(username__iexact=username) | Q(email__iexact=email)
            ).first()

            if user:
                user.username = username
                user.email = email
                user.first_name = acc["first_name"]
                user.last_name = acc["last_name"]
                user.is_staff = True
                user.is_superuser = True
                user.is_active = True
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Updated admin user '{username}' (Superuser)"))
            else:
                user = User.objects.create(
                    username=username,
                    email=email,
                    first_name=acc["first_name"],
                    last_name=acc["last_name"],
                    is_staff=True,
                    is_superuser=True,
                    is_active=True,
                )
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Created admin user '{username}' (Superuser)"))

            # Ensure workspace exists
            tenant = get_active_tenant_for_user(user)
            if not tenant:
                tenant, _ = create_personal_workspace_for_user(user, workspace_name=workspace_name)
                self.stdout.write(self.style.SUCCESS(f"  -> Created personal workspace: '{tenant.name}'"))
            else:
                tenant.name = workspace_name
                tenant.save(update_fields=["name"])
                self.stdout.write(self.style.SUCCESS(f"  -> Workspace set to: '{tenant.name}'"))

        # 2. Prune all other users who are NOT in the target list
        other_users = User.objects.exclude(username__in=target_usernames)
        count_pruned = other_users.count()
        if count_pruned > 0:
            pruned_names = list(other_users.values_list("username", flat=True))
            other_users.delete()
            self.stdout.write(self.style.WARNING(f"Pruned {count_pruned} other user(s): {', '.join(pruned_names)}"))

        # 3. Clean up orphaned tenants with no active memberships
        orphaned_tenants = Tenant.objects.filter(memberships__isnull=True)
        count_orphans = orphaned_tenants.count()
        if count_orphans > 0:
            orphaned_tenants.delete()
            self.stdout.write(self.style.WARNING(f"Cleaned up {count_orphans} orphaned tenant(s)"))

        # Verify final user count
        final_users = list(User.objects.values_list("username", "is_superuser"))
        self.stdout.write(self.style.SUCCESS(
            f"Successfully configured exactly {len(final_users)} admin accounts: {final_users}"
        ))
