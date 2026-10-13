from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from tenants.models import Membership, Tenant

User = get_user_model()


class AuthAndTenantsTestCase(TestCase):
    """
    Tests user registration, automatic personal workspace provisioning,
    login/logout workflows, and anonymous visitor access restrictions.
    """

    def setUp(self):
        self.client = Client()
        self.register_url = reverse("register")
        self.login_url = reverse("login")
        self.logout_url = reverse("logout")
        self.dashboard_url = reverse("dashboard")
        self.onboarding_url = reverse("onboarding")

    def test_registration_provisions_user_and_personal_workspace(self):
        """
        Verify that registering a new user creates the user, provisions a personal
        workspace tenant, and sets up an OWNER active membership.
        """
        response = self.client.post(self.register_url, {
            "username": "alex",
            "email": "alex@example.com",
            "password": "StrongPassword123!",
            "password_confirm": "StrongPassword123!",
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.onboarding_url)

        user = User.objects.filter(username="alex").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.email, "alex@example.com")

        # Verify automatic workspace creation
        membership = Membership.objects.filter(user=user).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, Membership.Role.OWNER)
        self.assertEqual(membership.status, Membership.Status.ACTIVE)

        tenant = membership.tenant
        self.assertIsNotNone(tenant)
        self.assertIn("alex", tenant.name.lower())
        self.assertTrue(tenant.slug.startswith("alex-"))

    def test_login_with_username_and_email(self):
        """
        Verify login succeeds with both username and email credentials.
        """
        # Create user via registration flow
        self.client.post(self.register_url, {
            "username": "sarah",
            "email": "sarah@example.com",
            "password": "StrongPassword123!",
            "password_confirm": "StrongPassword123!",
        })
        self.client.get(self.logout_url)

        # Login with username
        resp_user = self.client.post(self.login_url, {
            "username": "sarah",
            "password": "StrongPassword123!",
        })
        self.assertEqual(resp_user.status_code, 302)

        self.client.get(self.logout_url)

        # Login with email
        resp_email = self.client.post(self.login_url, {
            "username": "sarah@example.com",
            "password": "StrongPassword123!",
        })
        self.assertEqual(resp_email.status_code, 302)

    def test_login_invalid_credentials_fails(self):
        """
        Verify that invalid credentials display an error and reject login.
        """
        response = self.client.post(self.login_url, {
            "username": "nonexistent",
            "password": "wrongpassword",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username/email or password.")

    def test_logout_terminates_session(self):
        """
        Verify logout terminates the session and redirects to login.
        """
        user = User.objects.create_user(username="bob", email="bob@example.com", password="Password123!")
        self.client.login(username="bob", password="Password123!")

        response = self.client.get(self.logout_url)
        self.assertRedirects(response, self.login_url)

        # Verify user is now anonymous on protected page
        dash_resp = self.client.get(self.dashboard_url)
        self.assertEqual(dash_resp.status_code, 302)
        self.assertIn("/accounts/login/", dash_resp.url)

    def test_anonymous_access_restrictions(self):
        """
        Verify that unauthenticated visitors are redirected to login for protected pages.
        """
        protected_urls = [
            self.dashboard_url,
            self.onboarding_url,
            reverse("habit_list"),
            reverse("habit_create"),
        ]
        for url in protected_urls:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302, f"URL {url} must redirect anonymous visitors")
            self.assertIn("/accounts/login/", resp.url)

    def test_registration_weak_password_displays_field_error(self):
        """
        Verify that a weak password generates specific field errors on password.
        """
        response = self.client.post(self.register_url, {
            "username": "shrinath_admin",
            "email": "admin@example.com",
            "password": "123",
            "password_confirm": "123",
        })
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn("password", form.errors)
        self.assertTrue(len(form.errors["password"]) > 0)
        self.assertContains(response, form.errors["password"][0])

    def test_admin_users_list_staff_access_and_non_staff_rejection(self):
        """
        Non-staff users are rejected, staff users see users list and search.
        """
        admin_users_url = reverse("admin_users_list")

        # Non-staff user
        regular_user = User.objects.create_user(username="regular", email="reg@example.com", password="Password123!")
        self.client.force_login(regular_user)
        resp = self.client.get(admin_users_url)
        self.assertEqual(resp.status_code, 403)  # Forbidden for non-staff

        # Staff user
        staff_user = User.objects.create_user(username="boss", email="boss@example.com", password="Password123!", is_staff=True)
        self.client.login(username="boss", password="Password123!")
        resp_staff = self.client.get(admin_users_url)
        self.assertEqual(resp_staff.status_code, 200)
        self.assertContains(resp_staff, "boss")
        self.assertContains(resp_staff, "reg@example.com")

        # Search functionality
        resp_search = self.client.get(admin_users_url + "?q=boss")
        self.assertEqual(resp_search.status_code, 200)
        self.assertContains(resp_search, "boss")
        self.assertNotContains(resp_search, "reg@example.com")

    def test_admin_user_create_by_staff(self):
        """
        Staff user creates a new user from the admin panel with workspace.
        """
        staff_user = User.objects.create_user(username="chief", email="chief@example.com", password="Password123!", is_staff=True)
        self.client.login(username="chief", password="Password123!")

        resp = self.client.post(reverse("admin_user_create"), {
            "username": "newbie",
            "email": "newbie@example.com",
            "first_name": "New",
            "last_name": "User",
            "password": "StrongPassword123!",
            "workspace_name": "Newbie Tech Workspace",
        })
        self.assertEqual(resp.status_code, 302)
        created_user = User.objects.filter(username="newbie").first()
        self.assertIsNotNone(created_user)
        self.assertTrue(created_user.memberships.filter(tenant__name="Newbie Tech Workspace").exists())

    def test_admin_user_edit_by_staff(self):
        """
        Staff user edits an existing user's profile and resets their password.
        """
        staff_user = User.objects.create_user(username="moderator", email="mod@example.com", password="Password123!", is_staff=True)
        target = User.objects.create_user(username="targetuser", email="target@example.com", password="OldPassword123!")
        self.client.login(username="moderator", password="Password123!")

        edit_url = reverse("admin_user_edit", kwargs={"user_id": target.pk})

        # GET edit page
        resp_get = self.client.get(edit_url)
        self.assertEqual(resp_get.status_code, 200)

        # POST update
        resp_post = self.client.post(edit_url, {
            "username": "target_updated",
            "email": "target_updated@example.com",
            "first_name": "Target",
            "last_name": "Updated",
            "new_password": "NewStrongPassword123!",
            "is_active": "on",
            "is_staff": "on",
        })
        self.assertEqual(resp_post.status_code, 302)

        target.refresh_from_db()
        self.assertEqual(target.username, "target_updated")
        self.assertEqual(target.email, "target_updated@example.com")
        self.assertTrue(target.is_staff)
        self.assertTrue(target.check_password("NewStrongPassword123!"))

    def test_admin_user_delete_by_staff(self):
        """
        Staff user can delete another user, but cannot delete themselves.
        """
        staff_user = User.objects.create_user(username="superadmin", email="super@example.com", password="Password123!", is_staff=True)
        victim = User.objects.create_user(username="victim", email="victim@example.com", password="Password123!")
        self.client.login(username="superadmin", password="Password123!")

        delete_url = reverse("admin_user_delete", kwargs={"user_id": victim.pk})

        # Delete victim
        resp = self.client.post(delete_url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(User.objects.filter(username="victim").exists())

        # Self-delete is blocked
        self_delete_url = reverse("admin_user_delete", kwargs={"user_id": staff_user.pk})
        resp_self = self.client.post(self_delete_url)
        self.assertEqual(resp_self.status_code, 302)
        self.assertTrue(User.objects.filter(username="superadmin").exists())



