from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from tenants.models import Tenant
from tenants.utils import create_personal_workspace_for_user
from habits.models import HabitCategory, RuleStrategy

User = get_user_model()


class AdminSeedDataFeatureTestCase(TestCase):
    """
    Test suite for the on-demand Odoo-style 'Add Admin Data' feature,
    common password configuration, and password-reset banner notification.
    """

    def setUp(self):
        self.client = Client()
        self.super_admin = User.objects.create_user(
            username="main_admin",
            email="main_admin@example.com",
            password="InitialAdminPass123!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.regular_user = User.objects.create_user(
            username="regular_bob",
            email="bob@example.com",
            password="BobPassword123!",
            role=User.Role.REGULAR_USER,
        )
        self.seed_url = reverse("admin_seed_data")
        self.users_list_url = reverse("admin_users_list")
        self.profile_url = reverse("profile")

    def test_anonymous_and_non_superadmin_access_restricted(self):
        # Anonymous users redirected to login
        res = self.client.post(self.seed_url, {"common_password": "NewSecret123!"})
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("login"), res.url)

        # Regular user gets 403 Forbidden
        self.client.force_login(self.regular_user)
        res = self.client.post(self.seed_url, {"common_password": "NewSecret123!"})
        self.assertEqual(res.status_code, 403)

    def test_super_admin_can_provision_admin_data_with_common_password(self):
        self.client.force_login(self.super_admin)

        # Pre-create an existing customer and workspace
        customer = User.objects.create_user(
            username="existing_customer",
            email="customer@example.com",
            password="CustomerPass123!",
        )
        customer_tenant, _ = create_personal_workspace_for_user(customer, workspace_name="Customer Workspace")

        # Submit seed data request with a chosen common password
        res = self.client.post(self.seed_url, {"common_password": "CompanySecret2026!"})
        self.assertEqual(res.status_code, 302)
        self.assertRedirects(res, self.users_list_url)

        # Verify all 3 designated admin accounts exist
        shrinath = User.objects.get(username="Shrinath_jayakumar")
        akash = User.objects.get(username="Akash_ps")
        romy = User.objects.get(username="Romy_fred")

        self.assertEqual(shrinath.role, User.Role.SUPER_ADMIN)
        self.assertEqual(akash.role, User.Role.TECHNICAL_USER)
        self.assertEqual(romy.role, User.Role.REGULAR_USER)

        # Verify password is valid for each user
        self.assertTrue(shrinath.check_password("CompanySecret2026!"))
        self.assertTrue(akash.check_password("CompanySecret2026!"))
        self.assertTrue(romy.check_password("CompanySecret2026!"))

        # Verify must_reset_password flag is set to True
        self.assertTrue(shrinath.must_reset_password)
        self.assertTrue(akash.must_reset_password)
        self.assertTrue(romy.must_reset_password)

        # Verify customer data was preserved and NOT deleted
        self.assertTrue(User.objects.filter(username="existing_customer").exists())
        self.assertTrue(Tenant.objects.filter(name="Customer Workspace").exists())

        # Verify master data seeded
        self.assertTrue(HabitCategory.objects.filter(tenant=customer_tenant).exists())
        self.assertTrue(RuleStrategy.objects.exists())

    def test_password_reset_banner_lifecycle(self):
        """
        Tests that when must_reset_password is True, the header banner is rendered.
        When user changes their password on their profile, must_reset_password is reset to False.
        """
        # 1. Create a user with must_reset_password = True
        user = User.objects.create_user(
            username="fresh_admin",
            email="fresh@example.com",
            password="CommonPassword123!",
            must_reset_password=True,
            role=User.Role.TECHNICAL_USER,
        )
        create_personal_workspace_for_user(user, workspace_name="Fresh Admin Workspace")

        # 2. Login as this user and visit dashboard or profile
        self.client.force_login(user)
        res = self.client.get(self.profile_url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Security Action Required:")
        self.assertContains(res, "Your workspace was provisioned with a temporary common password.")

        # 3. User submits a new password via profile edit form
        res_post = self.client.post(self.profile_url, {
            "first_name": "Fresh",
            "last_name": "Admin",
            "email": "fresh@example.com",
            "workspace_name": "Fresh Admin Workspace",
            "new_password": "MyNewSecurePersonalPassword123!",
        })
        self.assertEqual(res_post.status_code, 302)

        # 4. Reload user from DB and verify must_reset_password is now False
        user.refresh_from_db()
        self.assertFalse(user.must_reset_password)
        self.assertTrue(user.check_password("MyNewSecurePersonalPassword123!"))

        # 5. Banner should now be gone
        res_after = self.client.get(self.profile_url)
        self.assertEqual(res_after.status_code, 200)
        self.assertNotContains(res_after, "Security Action Required:")
