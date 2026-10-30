import os
import tempfile
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from tenants.models import Membership, Tenant

User = get_user_model()


class ProtectedMediaViewTestCase(TestCase):
    """
    Test suite for multi-tenant protected media access (SEC-03).
    Ensures authentication, workspace boundary isolation, super-admin privileges,
    and path traversal prevention.
    """

    def setUp(self):
        self.temp_media_dir = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.temp_media_dir.name)
        self.override.enable()

        self.client = Client()

        # Tenant A and its user
        self.user_a = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="AlicePassword123!",
        )
        self.tenant_a = Tenant.objects.create(name="Tenant Alpha", slug="tenant-alpha")
        Membership.objects.create(
            user=self.user_a,
            tenant=self.tenant_a,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
        )

        # Tenant B and its user
        self.user_b = User.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="BobPassword123!",
        )
        self.tenant_b = Tenant.objects.create(name="Tenant Beta", slug="tenant-beta")
        Membership.objects.create(
            user=self.user_b,
            tenant=self.tenant_b,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
        )

        # Super Admin
        self.super_admin = User.objects.create_user(
            username="super_hero",
            email="super@example.com",
            password="SuperPassword123!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
            is_superuser=True,
        )

        # Create a sample evidence file in Tenant A's folder
        self.file_rel_path = "tenants/tenant-alpha/evidence/workout_proof.png"
        self.file_abs_path = os.path.join(self.temp_media_dir.name, "tenants", "tenant-alpha", "evidence", "workout_proof.png")
        os.makedirs(os.path.dirname(self.file_abs_path), exist_ok=True)
        with open(self.file_abs_path, "wb") as f:
            f.write(b"PNG_SAMPLE_BINARY_EVIDENCE_DATA")

        self.media_url = f"/media/{self.file_rel_path}"

    def tearDown(self):
        self.override.disable()
        self.temp_media_dir.cleanup()

    def test_anonymous_user_is_redirected_to_login(self):
        """Unauthenticated requests must be blocked and redirected to login."""
        response = self.client.get(self.media_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_same_tenant_member_can_access_media(self):
        """Users belonging to Tenant Alpha must be able to view their evidence files."""
        self.client.force_login(self.user_a)
        response = self.client.get(self.media_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        # Consume streaming content
        content = b"".join(response.streaming_content)
        self.assertEqual(content, b"PNG_SAMPLE_BINARY_EVIDENCE_DATA")

    def test_cross_tenant_user_is_forbidden(self):
        """Users belonging to Tenant Beta must receive 403 Forbidden when accessing Tenant Alpha's files (IDOR protection)."""
        self.client.force_login(self.user_b)
        response = self.client.get(self.media_url)
        self.assertEqual(response.status_code, 403)

    def test_super_admin_can_access_any_tenant_media(self):
        """Super Admins must be allowed access to evidence files across all tenants."""
        self.client.force_login(self.super_admin)
        response = self.client.get(self.media_url)
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content)
        self.assertEqual(content, b"PNG_SAMPLE_BINARY_EVIDENCE_DATA")

    def test_nonexistent_file_returns_404(self):
        """Missing files must return 404 Not Found."""
        self.client.force_login(self.user_a)
        response = self.client.get("/media/tenants/tenant-alpha/evidence/does_not_exist.png")
        self.assertEqual(response.status_code, 404)

    def test_path_traversal_is_blocked(self):
        """Directory traversal attempts (e.g. ../../) must return 404."""
        self.client.force_login(self.user_a)
        response = self.client.get("/media/../config/settings.py")
        self.assertEqual(response.status_code, 404)
