from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from habits.models import Habit
from tenants.models import Membership, Tenant


class AdminViewModeToggleTests(TestCase):
    """
    Tests for the Super Admin View Mode Switcher:
    - Allows Super Admins (like Shrinath) to temporarily preview the UI as a Regular User.
    - Hides all admin menus, dropdowns, and elevated permissions without modifying the database.
    - Allows 1-click return to full Admin Mode.
    - Prevents non-super-admins from switching modes.
    """

    def setUp(self):
        self.client = Client()

        self.tenant = Tenant.objects.create(name="Shrinath HQ", slug="shrinath-hq")

        # Super Admin user (Shrinath)
        self.super_admin = User.objects.create_user(
            username="Shrinath",
            email="shrinath@habitpulse.com",
            password="AdminPassword123!",
            role=User.Role.SUPER_ADMIN,
        )
        Membership.objects.create(
            tenant=self.tenant,
            user=self.super_admin,
            role="OWNER",
            status="ACTIVE",
        )

        # Super admin habit so dashboard does not redirect to onboarding
        Habit.objects.create(
            tenant=self.tenant,
            created_by=self.super_admin,
            name="Super Admin Focus",
            frequency=Habit.Frequency.DAILY,
            start_date=timezone.localdate(),
            pixel_score=10,
            is_active=True,
        )

        # Standard Regular user
        self.regular_user = User.objects.create_user(
            username="regular_bob",
            email="bob@habitpulse.com",
            password="BobPassword123!",
            role=User.Role.REGULAR_USER,
        )
        Membership.objects.create(
            tenant=self.tenant,
            user=self.regular_user,
            role="MEMBER",
            status="ACTIVE",
        )

        # Regular user habit so dashboard does not redirect to onboarding
        Habit.objects.create(
            tenant=self.tenant,
            created_by=self.regular_user,
            name="Morning Jog",
            frequency=Habit.Frequency.DAILY,
            start_date=timezone.localdate(),
            pixel_score=10,
            is_active=True,
        )

    def test_default_mode_is_admin_for_super_admin(self):
        """
        By default, Super Admin sees the full admin interface with Admin Panel dropdown.
        """
        self.client.force_login(self.super_admin)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Admin Panel")
        self.assertContains(resp, "adminDropdownBtn")
        self.assertContains(resp, "Admin Mode")
        self.assertContains(resp, "Switch to User")

    def test_toggle_to_user_mode_hides_admin_panel_and_shows_preview_banner(self):
        """
        When Super Admin toggles to User Mode:
        - Admin Panel dropdown button is hidden.
        - User Mode sticky preview banner is displayed.
        - User role badge reflects Regular User preview.
        - Database record remains untouched.
        """
        self.client.force_login(self.super_admin)

        # 1. Post to toggle view mode
        toggle_resp = self.client.post(reverse("toggle_view_mode"), {
            "mode": "user",
            "next": reverse("dashboard"),
        })
        self.assertEqual(toggle_resp.status_code, 302)
        self.assertEqual(self.client.session.get("admin_view_mode"), "user")

        # 2. View dashboard in User Mode
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)

        # Admin Panel dropdown button must be completely hidden
        self.assertNotContains(resp, "adminDropdownBtn")
        self.assertNotContains(resp, "Admin Panel")

        # User Preview Mode sticky alert banner must be displayed
        self.assertContains(resp, "User Preview Mode Active")
        self.assertContains(resp, "Return to Admin Mode")

        # Database record is 100% untouched
        self.super_admin.refresh_from_db()
        self.assertEqual(self.super_admin.role, User.Role.SUPER_ADMIN)
        self.assertTrue(self.super_admin.is_superuser)
        self.assertTrue(self.super_admin.is_real_super_admin)

    def test_toggle_back_to_admin_mode(self):
        """
        Super Admin can return to Admin Mode, restoring all admin controls.
        """
        self.client.force_login(self.super_admin)

        # Set session to user mode first
        session = self.client.session
        session["admin_view_mode"] = "user"
        session.save()

        # Verify currently in user mode
        resp_user = self.client.get(reverse("dashboard"))
        self.assertEqual(resp_user.status_code, 200)
        self.assertNotContains(resp_user, "adminDropdownBtn")
        self.assertNotContains(resp_user, "Admin Panel")

        # Toggle back to admin mode
        resp_toggle = self.client.post(reverse("toggle_view_mode"), {
            "mode": "admin",
            "next": reverse("dashboard"),
        })
        self.assertEqual(resp_toggle.status_code, 302)

        # Dashboard now has full admin controls restored
        resp_admin = self.client.get(reverse("dashboard"))
        self.assertEqual(resp_admin.status_code, 200)
        self.assertContains(resp_admin, "adminDropdownBtn")
        self.assertContains(resp_admin, "Admin Panel")

    def test_regular_user_cannot_switch_to_admin_mode(self):
        """
        A regular user cannot use the view mode switcher to gain admin access.
        """
        self.client.force_login(self.regular_user)

        # Regular user attempts to switch to admin mode
        resp = self.client.post(reverse("toggle_view_mode"), {
            "mode": "admin",
        })
        self.assertEqual(resp.status_code, 302)

        # Session must NOT have admin_view_mode set to admin
        self.assertNotEqual(self.client.session.get("admin_view_mode"), "admin")

        # Dashboard remains standard user view with zero admin panels
        resp_dash = self.client.get(reverse("dashboard"))
        self.assertEqual(resp_dash.status_code, 200)
        self.assertNotContains(resp_dash, "adminDropdownBtn")
        self.assertNotContains(resp_dash, "Admin Panel")
        self.assertNotContains(resp_dash, "Switch to User")
