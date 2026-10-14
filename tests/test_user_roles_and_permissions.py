import datetime
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from habits.models import HabitCategory, RuleStrategy
from tenants.models import Membership, Tenant

User = get_user_model()


class UserRolesAndPermissionsTestCase(TestCase):
    """
    Comprehensive test suite for the three-tier access-based role system:
    1. SUPER_ADMIN: Unrestricted access to frontend, backend, Admin Panel,
       master data, and database operations.
    2. TECHNICAL_USER: Full access to all functional application parts (Dashboard,
       Habits, Categories CRUD, Rule Strategies CRUD), but strictly forbidden
       from Admin Panel and user management.
    3. REGULAR_USER: Access strictly limited to their own dashboard and personal habits.
    """

    def setUp(self):
        self.client = Client()

        # Workspace / Tenant
        self.tenant = Tenant.objects.create(name="HabitPulse HQ", slug="habitpulse-hq")

        # 1. Super Admin
        self.super_admin = User.objects.create_user(
            username="Shrinath_super",
            email="shrinath@habitpulse.com",
            password="AdminPassword123!",
            role=User.Role.SUPER_ADMIN,
        )
        Membership.objects.create(
            user=self.super_admin,
            tenant=self.tenant,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
        )

        # 2. Technical User
        self.tech_user = User.objects.create_user(
            username="Akash_tech",
            email="akash@habitpulse.com",
            password="TechPassword123!",
            role=User.Role.TECHNICAL_USER,
        )
        Membership.objects.create(
            user=self.tech_user,
            tenant=self.tenant,
            role=Membership.Role.MEMBER,
            status=Membership.Status.ACTIVE,
        )

        # 3. Regular User
        self.regular_user = User.objects.create_user(
            username="Romy_reg",
            email="romy@habitpulse.com",
            password="UserPassword123!",
            role=User.Role.REGULAR_USER,
        )
        Membership.objects.create(
            user=self.regular_user,
            tenant=self.tenant,
            role=Membership.Role.MEMBER,
            status=Membership.Status.ACTIVE,
        )

        # URLs
        self.roles_list_url = reverse("admin_roles_list")
        self.users_list_url = reverse("admin_users_list")
        self.user_create_url = reverse("admin_user_create")
        self.user_edit_url = reverse("admin_user_edit", kwargs={"user_id": self.regular_user.id})
        self.role_change_url = reverse("admin_user_role_change", kwargs={"user_id": self.regular_user.id})
        self.categories_list_url = reverse("category_list")
        self.categories_create_url = reverse("category_create")
        self.rules_list_url = reverse("rule_strategy_list")
        self.rules_create_url = reverse("rule_strategy_create")
        self.dashboard_url = reverse("dashboard")
        self.habits_list_url = reverse("habit_list")

        # Create active habit so dashboard does not redirect to onboarding
        from habits.models import Habit
        self.habit = Habit.objects.create(
            tenant=self.tenant,
            name="Daily Focus Session",
            frequency=Habit.Frequency.DAILY,
            start_date=datetime.date.today(),
            created_by=self.super_admin,
            is_active=True,
        )

    # -------------------------------------------------------------
    # 1. Model & Helper Properties Tests
    # -------------------------------------------------------------
    def test_super_admin_properties(self):
        self.assertTrue(self.super_admin.is_super_admin)
        self.assertFalse(self.super_admin.is_technical_user)
        self.assertFalse(self.super_admin.is_regular_user)
        self.assertTrue(self.super_admin.is_superuser)
        self.assertTrue(self.super_admin.is_staff)
        badge = self.super_admin.get_role_badge()
        self.assertEqual(badge["label"], "Super Admin")
        self.assertEqual(badge["class"], "badge-super-admin")

    def test_technical_user_properties(self):
        self.assertFalse(self.tech_user.is_super_admin)
        self.assertTrue(self.tech_user.is_technical_user)
        self.assertFalse(self.tech_user.is_regular_user)
        self.assertFalse(self.tech_user.is_superuser)
        self.assertFalse(self.tech_user.is_staff)
        badge = self.tech_user.get_role_badge()
        self.assertEqual(badge["label"], "Technical User")
        self.assertEqual(badge["class"], "badge-technical-user")

    def test_regular_user_properties(self):
        self.assertFalse(self.regular_user.is_super_admin)
        self.assertFalse(self.regular_user.is_technical_user)
        self.assertTrue(self.regular_user.is_regular_user)
        self.assertFalse(self.regular_user.is_superuser)
        self.assertFalse(self.regular_user.is_staff)
        badge = self.regular_user.get_role_badge()
        self.assertEqual(badge["label"], "Regular User")
        self.assertEqual(badge["class"], "badge-regular-user")

    # -------------------------------------------------------------
    # 2. Super Admin Access Tests
    # -------------------------------------------------------------
    def test_super_admin_has_unrestricted_access(self):
        """Super Admin can access User Roles, Admin Users list, and Master Data."""
        self.client.force_login(self.super_admin)

        # Admin Roles page
        resp = self.client.get(self.roles_list_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "User Roles &amp; Access Control")
        self.assertContains(resp, "SUPER_ADMIN")
        self.assertContains(resp, "TECHNICAL_USER")
        self.assertContains(resp, "REGULAR_USER")

        # Admin Users List
        resp = self.client.get(self.users_list_url)
        self.assertEqual(resp.status_code, 200)

        # Categories & Rule Strategies
        self.assertEqual(self.client.get(self.categories_list_url).status_code, 200)
        self.assertEqual(self.client.get(self.rules_list_url).status_code, 200)

        # Dashboard & Habits
        self.assertEqual(self.client.get(self.dashboard_url).status_code, 200)
        self.assertEqual(self.client.get(self.habits_list_url).status_code, 200)

    # -------------------------------------------------------------
    # 3. Technical User Access & Restrictions Tests
    # -------------------------------------------------------------
    def test_technical_user_access_and_admin_restrictions(self):
        """
        Technical users have access to Dashboard, Habits, and Master Data (Categories/Rules),
        but are strictly forbidden (403) from the Admin Panel.
        """
        self.client.force_login(self.tech_user)

        # Allowed: Dashboard & Habits
        self.assertEqual(self.client.get(self.dashboard_url).status_code, 200)
        self.assertEqual(self.client.get(self.habits_list_url).status_code, 200)

        # Allowed: Master Data CRUD
        self.assertEqual(self.client.get(self.categories_list_url).status_code, 200)
        self.assertEqual(self.client.get(self.categories_create_url).status_code, 200)
        self.assertEqual(self.client.get(self.rules_list_url).status_code, 200)
        self.assertEqual(self.client.get(self.rules_create_url).status_code, 200)

        # FORBIDDEN: Admin Panel & User Roles
        self.assertEqual(self.client.get(self.roles_list_url).status_code, 403)
        self.assertEqual(self.client.get(self.users_list_url).status_code, 403)
        self.assertEqual(self.client.get(self.user_create_url).status_code, 403)
        self.assertEqual(self.client.get(self.user_edit_url).status_code, 403)
        self.assertEqual(self.client.post(self.role_change_url, {"role": "SUPER_ADMIN"}).status_code, 403)

    # -------------------------------------------------------------
    # 4. Regular User Access & Restrictions Tests
    # -------------------------------------------------------------
    def test_regular_user_access_and_master_data_restrictions(self):
        """
        Regular users have access only to personal dashboard and habits.
        They are strictly forbidden (403) from Master Data CRUD and Admin Panel.
        """
        self.client.force_login(self.regular_user)

        # Allowed: Dashboard & Habits
        self.assertEqual(self.client.get(self.dashboard_url).status_code, 200)
        self.assertEqual(self.client.get(self.habits_list_url).status_code, 200)

        # FORBIDDEN: Master Data CRUD
        self.assertEqual(self.client.get(self.categories_list_url).status_code, 403)
        self.assertEqual(self.client.get(self.categories_create_url).status_code, 403)
        self.assertEqual(self.client.get(self.rules_list_url).status_code, 403)
        self.assertEqual(self.client.get(self.rules_create_url).status_code, 403)

        # FORBIDDEN: Admin Panel & User Roles
        self.assertEqual(self.client.get(self.roles_list_url).status_code, 403)
        self.assertEqual(self.client.get(self.users_list_url).status_code, 403)
        self.assertEqual(self.client.get(self.user_create_url).status_code, 403)

    # -------------------------------------------------------------
    # 5. Quick Role Reassignment & Self-Demotion Safety
    # -------------------------------------------------------------
    def test_super_admin_can_reassign_user_role(self):
        """Super Admin can promote/reassign a regular user to Technical User."""
        self.client.force_login(self.super_admin)

        resp = self.client.post(self.role_change_url, {"role": User.Role.TECHNICAL_USER})
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, self.roles_list_url)

        self.regular_user.refresh_from_db()
        self.assertEqual(self.regular_user.role, User.Role.TECHNICAL_USER)
        self.assertTrue(self.regular_user.is_technical_user)
        self.assertFalse(self.regular_user.is_superuser)

    def test_super_admin_cannot_self_demote(self):
        """Super Admin cannot demote their own account to prevent lockout."""
        self.client.force_login(self.super_admin)
        self_demote_url = reverse("admin_user_role_change", kwargs={"user_id": self.super_admin.id})

        resp = self.client.post(self_demote_url, {"role": User.Role.REGULAR_USER})
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, self.roles_list_url)

        # Role remains SUPER_ADMIN
        self.super_admin.refresh_from_db()
        self.assertEqual(self.super_admin.role, User.Role.SUPER_ADMIN)
        self.assertTrue(self.super_admin.is_super_admin)

    # -------------------------------------------------------------
    # 6. Navbar Scoping Verification
    # -------------------------------------------------------------
    def test_navbar_renders_correctly_per_role(self):
        """Navbar displays Admin Panel and Master Data only to entitled roles."""
        # Super Admin sees Categories, Rule Strategies, and Admin Panel
        self.client.force_login(self.super_admin)
        resp_sa = self.client.get(self.dashboard_url)
        self.assertContains(resp_sa, "Admin Panel")
        self.assertContains(resp_sa, "User Roles")
        self.assertContains(resp_sa, "Categories")
        self.assertContains(resp_sa, "Rule Strategies")

        # Technical User sees Categories & Rule Strategies, but NOT Admin Panel
        self.client.force_login(self.tech_user)
        resp_tu = self.client.get(self.dashboard_url)
        self.assertContains(resp_tu, "Categories")
        self.assertContains(resp_tu, "Rule Strategies")
        self.assertNotContains(resp_tu, "Admin Panel")

        # Regular User sees Dashboard & Habits, but NOT Categories, Rule Strategies, or Admin Panel
        self.client.force_login(self.regular_user)
        resp_ru = self.client.get(self.dashboard_url)
        self.assertContains(resp_ru, "Dashboard")
        self.assertContains(resp_ru, "Habits")
        self.assertNotContains(resp_ru, "Admin Panel")
        # In navbar menu, Categories and Rule Strategies links shouldn't appear
        self.assertNotContains(resp_ru, reverse("category_list"))
        self.assertNotContains(resp_ru, reverse("rule_strategy_list"))

    # -------------------------------------------------------------
    # 7. Customizable Role Permission Checkboxes Tests
    # -------------------------------------------------------------
    def test_super_admin_can_customize_role_permissions(self):
        """
        Super Admin can toggle checkboxes for any role.
        When manage_categories is granted to Regular User, regular users immediately gain access.
        """
        self.client.force_login(self.super_admin)
        role_perm_url = reverse("admin_role_permissions_update", kwargs={"role_code": User.Role.REGULAR_USER})

        # Initially, regular user gets 403 on categories
        self.client.force_login(self.regular_user)
        self.assertEqual(self.client.get(self.categories_list_url).status_code, 403)

        # Super Admin checks 'manage_categories' and 'view_dashboard' for Regular User
        self.client.force_login(self.super_admin)
        resp = self.client.post(role_perm_url, {
            "view_dashboard": "on",
            "manage_habits": "on",
            "manage_categories": "on",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, self.roles_list_url)

        # Regular user now has permission and can access category list!
        self.client.force_login(self.regular_user)
        self.assertEqual(self.client.get(self.categories_list_url).status_code, 200)

        # Navbar for regular user now shows Categories
        resp_ru = self.client.get(self.dashboard_url)
        self.assertContains(resp_ru, "Categories")

        # Super Admin revokes 'manage_categories' from Regular User
        self.client.force_login(self.super_admin)
        self.client.post(role_perm_url, {
            "view_dashboard": "on",
            "manage_habits": "on",
        })

        # Regular user immediately receives 403 again
        self.client.force_login(self.regular_user)
        self.assertEqual(self.client.get(self.categories_list_url).status_code, 403)

    # -------------------------------------------------------------
    # 8. User-Level Custom Permission Overrides Tests
    # -------------------------------------------------------------
    def test_super_admin_can_set_individual_user_permission_override(self):
        """
        Super Admin can configure custom checkboxes for an individual user,
        granting them specific menu/page privileges independently of their role.
        """
        self.client.force_login(self.super_admin)
        user_perm_url = reverse("admin_user_permissions_update", kwargs={"user_id": self.regular_user.id})

        # Enable custom override granting categories CRUD specifically to regular_user
        resp = self.client.post(user_perm_url, {
            "enable_custom": "on",
            "view_dashboard": "on",
            "manage_habits": "on",
            "manage_categories": "on",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, self.roles_list_url)

        # regular_user now has custom access
        self.client.force_login(self.regular_user)
        self.assertTrue(self.regular_user.can_manage_categories)
        self.assertEqual(self.client.get(self.categories_list_url).status_code, 200)

        # Another regular user without overrides is still blocked
        other_user = User.objects.create_user(
            username="OtherRegular",
            email="other@example.com",
            password="Password123!",
            role=User.Role.REGULAR_USER,
        )
        Membership.objects.create(user=other_user, tenant=self.tenant, role=Membership.Role.MEMBER, status=Membership.Status.ACTIVE)
        self.client.force_login(other_user)
        self.assertFalse(other_user.can_manage_categories)
        self.assertEqual(self.client.get(self.categories_list_url).status_code, 403)

        # Super Admin disables custom override for regular_user
        self.client.force_login(self.super_admin)
        self.client.post(user_perm_url, {
            # enable_custom omitted -> reverts to role inheritance
            "view_dashboard": "on",
            "manage_habits": "on",
        })

        # regular_user reverts to role inheritance (no categories)
        self.client.force_login(self.regular_user)
        self.assertFalse(self.regular_user.can_manage_categories)
        self.assertEqual(self.client.get(self.categories_list_url).status_code, 403)
