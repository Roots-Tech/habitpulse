from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from tenants.models import Membership, Tenant

User = get_user_model()


class AdminUsersCrudTestCase(TestCase):
    """
    Test suite for the custom ERP/Odoo-style Admin Panel Users CRUD views.
    Ensures staff-only permissions, complete CRUD capabilities, and safeguards.
    """

    def setUp(self):
        self.client = Client()

        # Admin / staff user
        self.admin_user = User.objects.create_user(
            username="superadmin",
            email="admin@habitpulse.com",
            password="AdminPassword123!",
            is_staff=True,
            is_superuser=True,
        )

        # Regular non-staff user
        self.regular_user = User.objects.create_user(
            username="regular_joe",
            email="joe@example.com",
            password="UserPassword123!",
            is_staff=False,
        )

        # URLs
        self.list_url = reverse("admin_users_list")
        self.create_url = reverse("admin_user_create")
        self.edit_url = reverse("admin_user_edit", kwargs={"user_id": self.regular_user.id})
        self.delete_url = reverse("admin_user_delete", kwargs={"user_id": self.regular_user.id})

    def test_anonymous_access_redirects_to_login(self):
        """Unauthenticated requests must be redirected to the login page."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_non_staff_access_is_forbidden(self):
        """Regular users without is_staff permission must receive 403 Forbidden."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 403)

        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 403)

        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 403)

        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 403)

    def test_staff_can_view_users_list_and_search(self):
        """Staff members can view the user list and filter by search query."""
        self.client.force_login(self.admin_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "superadmin")
        self.assertContains(response, "regular_joe")
        self.assertContains(response, "admin@habitpulse.com")

        # Test search filter
        response_search = self.client.get(self.list_url, {"q": "joe"})
        self.assertEqual(response_search.status_code, 200)
        self.assertContains(response_search, "regular_joe")
        self.assertNotContains(response_search, "admin@habitpulse.com")

    def test_staff_can_create_new_user(self):
        """Staff members can create a user, setting workspace and credentials."""
        self.client.force_login(self.admin_user)
        response = self.client.post(self.create_url, {
            "username": "charlie_new",
            "email": "charlie@example.com",
            "first_name": "Charlie",
            "last_name": "Brown",
            "password": "NewSecretPassword123!",
            "password_confirm": "NewSecretPassword123!",
            "workspace_name": "Charlie's Growth Hub",
            "is_active": "on",
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.list_url)

        new_user = User.objects.filter(username="charlie_new").first()
        self.assertIsNotNone(new_user)
        self.assertEqual(new_user.email, "charlie@example.com")
        self.assertEqual(new_user.first_name, "Charlie")
        self.assertTrue(new_user.is_active)

        # Check workspace creation
        membership = Membership.objects.filter(user=new_user).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.tenant.name, "Charlie's Growth Hub")

    def test_staff_can_edit_user_and_workspace(self):
        """Staff members can edit profile fields and workspace name."""
        self.client.force_login(self.admin_user)
        
        # Give regular user a tenant first
        tenant = Tenant.objects.create(name="Joe Original Workspace", slug="joe-workspace")
        Membership.objects.create(user=self.regular_user, tenant=tenant, role=Membership.Role.OWNER)

        response = self.client.post(self.edit_url, {
            "username": "regular_joe",
            "email": "joe_updated@example.com",
            "first_name": "Joseph",
            "last_name": "Smith",
            "workspace_name": "Joe Renovated Space",
            "is_active": "on",
            "is_staff": "on",
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.list_url)

        self.regular_user.refresh_from_db()
        self.assertEqual(self.regular_user.email, "joe_updated@example.com")
        self.assertEqual(self.regular_user.first_name, "Joseph")
        self.assertTrue(self.regular_user.is_staff)

        tenant.refresh_from_db()
        self.assertEqual(tenant.name, "Joe Renovated Space")

    def test_staff_can_delete_user(self):
        """Staff members can delete another user."""
        self.client.force_login(self.admin_user)
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.list_url)

        self.assertFalse(User.objects.filter(id=self.regular_user.id).exists())

    def test_staff_cannot_delete_themselves(self):
        """Staff members cannot delete their own account."""
        self.client.force_login(self.admin_user)
        self_delete_url = reverse("admin_user_delete", kwargs={"user_id": self.admin_user.id})
        response = self.client.post(self_delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.list_url)

        # Admin must still exist
        self.assertTrue(User.objects.filter(id=self.admin_user.id).exists())

    def test_users_list_view_columns_and_pixel_score(self):
        """Users list view must contain only Name, Login/Email, System Access Role, Pixel Score, Actions."""
        self.client.force_login(self.admin_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)

        # Check required columns
        self.assertContains(response, "<th>Name</th>")
        self.assertContains(response, "<th>Login / Email</th>")
        self.assertContains(response, "System Access Role")
        self.assertContains(response, "Pixel Score")
        self.assertContains(response, "Actions")

        # Check removed table header columns are not in the table header
        self.assertNotContains(response, "<th>Workspace Role</th>")
        self.assertNotContains(response, "<th>Latest Authentication</th>")
        self.assertNotContains(response, "<th>Primary Workspace</th>")

        # Check pixel score badge is rendered
        self.assertContains(response, "0</span> Px")

    def test_user_edit_metadata_tab_renders(self):
        """User edit form view must include the Metadata tab with workspace and auth details."""
        self.client.force_login(self.admin_user)
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)

        # Metadata tab button and pane
        self.assertContains(response, 'data-tab="metadata"')
        self.assertContains(response, 'id="tab-metadata"')
        self.assertContains(response, "Primary Workspace")
        self.assertContains(response, "Workspace Role &amp; Locale")
        self.assertContains(response, "Latest Authentication")
