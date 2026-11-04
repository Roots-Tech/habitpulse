from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User
from tenants.models import Membership, Tenant
from habits.models import Habit


class CollaboratorsViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Ecosystem Tenant", slug="ecosystem-tenant")
        self.user = User.objects.create_user(
            username="collaborator_user",
            email="collab@example.com",
            password="securepassword123",
            role=User.Role.REGULAR_USER,
        )
        Membership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role="MEMBER",
            status="ACTIVE",
        )

    def test_unauthenticated_user_redirected(self):
        """Unauthenticated access should redirect to login."""
        response = self.client.get(reverse("collaborators"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_authenticated_user_can_access_collaborators(self):
        """Authenticated user receives 200 OK with correct template."""
        self.client.login(username="collaborator_user", password="securepassword123")
        response = self.client.get(reverse("collaborators"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "collaborators/collaborators.html")
        self.assertContains(response, "Collaborators &amp; Ecosystem")

    def test_collaborators_page_contains_two_sections(self):
        """The page must render both Curated Offers and Trending Life Suggestions sections."""
        self.client.login(username="collaborator_user", password="securepassword123")
        response = self.client.get(reverse("collaborators"))
        self.assertEqual(response.status_code, 200)

        # Chevron Pipeline items
        self.assertContains(response, "chevron-btn-offers")
        self.assertContains(response, "chevron-btn-suggestions")
        self.assertContains(response, "Curated Offers")
        self.assertContains(response, "Trending Life Suggestions")

        # Two dedicated content panes
        self.assertContains(response, "pane-curated-offers")
        self.assertContains(response, "pane-trending-suggestions")

    def test_chevron_pipeline_ribbon_structure(self):
        """Verify the segmented chevron pipeline ribbon markup and transition node."""
        self.client.login(username="collaborator_user", password="securepassword123")
        response = self.client.get(reverse("collaborators"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="chevron-pipeline"')
        self.assertContains(response, 'class="chevron-node"')
        self.assertContains(response, "Partner Perks &amp; Rewards")
        self.assertContains(response, "Lifestyle &amp; Biohack Protocols")

    def test_tab_query_param_handling(self):
        """Passing ?tab=suggestions should set active_tab context variable to 'suggestions'."""
        self.client.login(username="collaborator_user", password="securepassword123")
        
        resp_suggestions = self.client.get(reverse("collaborators") + "?tab=suggestions")
        self.assertEqual(resp_suggestions.status_code, 200)
        self.assertEqual(resp_suggestions.context["active_tab"], "suggestions")

        resp_offers = self.client.get(reverse("collaborators") + "?tab=offers")
        self.assertEqual(resp_offers.status_code, 200)
        self.assertEqual(resp_offers.context["active_tab"], "offers")

    def test_partner_offers_and_life_suggestions_rendered(self):
        """Verify representative partner perks and lifestyle protocols are rendered."""
        self.client.login(username="collaborator_user", password="securepassword123")
        response = self.client.get(reverse("collaborators"))
        self.assertEqual(response.status_code, 200)

        # Curated Offers checks
        self.assertContains(response, "Oura Health")
        self.assertContains(response, "WHOOP")
        self.assertContains(response, "Eight Sleep")
        self.assertContains(response, "AG1 Nutrition")
        self.assertContains(response, "Notion Labs")

        # Trending Life Suggestions checks
        self.assertContains(response, "Huberman Early Morning Sunlight Protocol")
        self.assertContains(response, "Cold Plunge &amp; Sauna Contrast Therapy")
        self.assertContains(response, "Zone 2 Aerobic Base")
        self.assertContains(response, "90-Minute Ultradian Deep Work Blocks")

    def test_sidebar_active_state_on_collaborators(self):
        """Sidebar should display Collaborators menu link as active when on collaborators URL."""
        self.client.login(username="collaborator_user", password="securepassword123")
        response = self.client.get(reverse("collaborators"))
        self.assertEqual(response.status_code, 200)
        # Verify sidebar link is rendered with active class
        self.assertContains(response, 'href="/collaborators/" class="sidebar-menu-link active"')

    def test_habit_create_prefills_name_and_description(self):
        """Clicking 'Adopt as Habit' with query parameters pre-fills habit_create form."""
        self.client.login(username="collaborator_user", password="securepassword123")
        response = self.client.get(
            reverse("habit_create") + "?name=Huberman+Morning+Sunlight&description=Morning+photons"
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("name"), "Huberman Morning Sunlight")
        self.assertEqual(form.initial.get("description"), "Morning photons")
