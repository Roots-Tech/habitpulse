import json
from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User
from tenants.models import Tenant, Membership
from habits.models import Habit


class PWATests(TestCase):
    """
    Tests for Progressive Web App (PWA) installability:
    - /manifest.json returns valid JSON with standalone display and PWA icons
    - /sw.js returns Service Worker script with Service-Worker-Allowed header
    - /offline/ renders custom offline fallback template
    - base.html includes manifest link, meta tags, and Service Worker registration
    - Single stylish install button in topbar header, accessible from all screens
    - Duplicate install button removed from sidebar
    """

    def setUp(self):
        self.client = Client(SERVER_NAME="127.0.0.1")
        self.user = User.objects.create_user(
            username="pwa_tester",
            email="pwa_tester@example.com",
            password="Password123!",
        )
        self.tenant = Tenant.objects.create(
            name="PWA Workspace",
            slug="pwa-ws",
        )
        Membership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role="OWNER",
            status="ACTIVE",
        )

    def test_manifest_json(self):
        """Verify web app manifest is served with correct MIME type and structure."""
        response = self.client.get(reverse("pwa_manifest"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/manifest+json")

        data = json.loads(response.content.decode("utf-8"))
        self.assertEqual(data["short_name"], "HabitPulse")
        self.assertEqual(data["display"], "standalone")
        self.assertEqual(data["start_url"], "/")
        self.assertEqual(data["scope"], "/")
        self.assertGreaterEqual(len(data["icons"]), 2)

        icon_sizes = [icon["sizes"] for icon in data["icons"]]
        self.assertIn("192x192", icon_sizes)
        self.assertIn("512x512", icon_sizes)

    def test_service_worker_script(self):
        """Verify service worker is served with correct scope header."""
        response = self.client.get(reverse("pwa_service_worker"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/javascript")
        self.assertEqual(response.headers["Service-Worker-Allowed"], "/")

        content = response.content.decode("utf-8")
        self.assertIn("CACHE_NAME", content)
        self.assertIn("addEventListener('install'", content)
        self.assertIn("addEventListener('fetch'", content)

    def test_offline_fallback_page(self):
        """Verify offline fallback page renders successfully."""
        response = self.client.get(reverse("pwa_offline"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Offline", response.content.decode("utf-8"))

    def test_base_html_includes_pwa_assets(self):
        """Verify public pages render the manifest tag and service worker registration."""
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

        html = response.content.decode("utf-8")
        self.assertIn('rel="manifest"', html)
        self.assertIn('name="theme-color"', html)
        self.assertIn('apple-touch-icon', html)
        self.assertIn('serviceWorker.register', html)

    def test_single_stylish_install_button_in_topbar(self):
        """
        Verify exactly one stylish install button exists in the common topbar header,
        and no duplicate install button is in the sidebar.
        """
        Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="PWA Habit",
            frequency=Habit.Frequency.DAILY,
            habit_type=Habit.HabitType.GENERAL,
        )

        self.client.force_login(self.user)
        session = self.client.session
        session["current_tenant_id"] = str(self.tenant.id)
        session.save()

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        html = response.content.decode("utf-8")
        # Exactly 1 pwaInstallBtn element in the DOM
        self.assertEqual(html.count('id="pwaInstallBtn"'), 1)
        self.assertIn("pwa-install-btn", html)

        # No duplicate in sidebar
        self.assertNotIn("pwaSidebarItem", html)
        self.assertNotIn("pwaSidebarInstallBtn", html)
