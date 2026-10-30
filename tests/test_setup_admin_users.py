from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from tenants.models import Membership, Tenant
from tenants.utils import create_personal_workspace_for_user
from habits.models import HabitCategory, RuleStrategy

User = get_user_model()


class SetupAdminUsersCommandTestCase(TestCase):
    """
    Test suite ensuring setup_admin_users provisions required admin accounts
    without destructively purging existing user accounts or workspaces (SEC-01).
    """

    def test_setup_admin_users_preserves_existing_users_and_tenants(self):
        # 1. Create a pre-existing regular customer/user and workspace
        customer = User.objects.create_user(
            username="existing_customer",
            email="customer@example.com",
            password="CustomerPassword123!",
        )
        customer_tenant, _ = create_personal_workspace_for_user(customer, workspace_name="Customer's Team")

        # Confirm customer exists before running command
        self.assertTrue(User.objects.filter(username="existing_customer").exists())
        self.assertTrue(Tenant.objects.filter(name="Customer's Team").exists())

        # 2. Run setup_admin_users command
        out = StringIO()
        call_command("setup_admin_users", stdout=out)

        # 3. Verify admin accounts are provisioned
        self.assertTrue(User.objects.filter(username="Shrinath_jayakumar").exists())
        self.assertTrue(User.objects.filter(username="Akash_ps").exists())
        self.assertTrue(User.objects.filter(username="Romy_fred").exists())

        # 4. Verify existing regular user and workspace were NOT deleted (SEC-01 safeguard)
        self.assertTrue(
            User.objects.filter(username="existing_customer").exists(),
            "Non-admin users must not be purged when setup_admin_users is executed.",
        )
        self.assertTrue(
            Tenant.objects.filter(name="Customer's Team").exists(),
            "Non-admin workspaces must not be purged when setup_admin_users is executed.",
        )

        # 5. Verify master data seeding ran successfully
        self.assertTrue(HabitCategory.objects.filter(tenant=customer_tenant).exists())
        self.assertTrue(RuleStrategy.objects.exists())
