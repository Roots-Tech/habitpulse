from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from habits.forms import RuleStrategyForm, HabitForm
from habits.models import Habit, RuleStrategy
from tenants.models import Membership, Tenant

User = get_user_model()


class RuleStrategyPixelAllocationTests(TestCase):
    """
    Test suite verifying that:
    1. RuleStrategy has `pixel_reward` defaulting to 0.
    2. Admin can create and update rule strategies with custom pixel rewards.
    3. Habits derive their pixel awards directly from RuleStrategy, not from habit_type.
    4. RuleStrategy list and form properly display and manage pixel rewards.
    """

    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Pixel Test Org", slug="pixel-test-org")

        self.super_admin = User.objects.create_user(
            username="admin_user",
            email="admin@test.com",
            password="AdminPassword123!",
            role=User.Role.SUPER_ADMIN,
        )
        Membership.objects.create(
            tenant=self.tenant,
            user=self.super_admin,
            role="OWNER",
            status="ACTIVE",
        )

        self.regular_user = User.objects.create_user(
            username="regular_user",
            email="user@test.com",
            password="UserPassword123!",
            role=User.Role.REGULAR_USER,
        )
        Membership.objects.create(
            tenant=self.tenant,
            user=self.regular_user,
            role="MEMBER",
            status="ACTIVE",
        )

    def test_rule_strategy_default_pixel_reward_is_zero(self):
        """New RuleStrategy created without explicit pixel reward defaults to 0."""
        strat = RuleStrategy.objects.create(
            name="Custom Meditation Timer",
            engine_type=RuleStrategy.EngineType.STANDARD,
        )
        self.assertEqual(strat.pixel_reward, 0)

    def test_admin_creates_rule_strategy_with_allocated_pixels(self):
        """Admin can allocate specific pixel rewards during RuleStrategy creation."""
        self.client.force_login(self.super_admin)
        post_data = {
            "name": "Strict Evidence Protocol",
            "engine_type": RuleStrategy.EngineType.EVIDENCE_FILE,
            "pixel_reward": 7,
            "default_unit": "photo",
            "description": "Requires photo proof to complete.",
            "is_active": True,
        }
        resp = self.client.post(reverse("rule_strategy_create"), post_data)
        self.assertEqual(resp.status_code, 302)

        strat = RuleStrategy.objects.get(name="Strict Evidence Protocol")
        self.assertEqual(strat.pixel_reward, 7)

    def test_admin_updates_existing_rule_strategy_pixel_reward(self):
        """Admin can edit an existing strategy (e.g. Honor System) to adjust its pixel reward."""
        strat = RuleStrategy.objects.create(
            name="Flexible Honor System",
            engine_type=RuleStrategy.EngineType.STANDARD,
            pixel_reward=0,
        )
        self.client.force_login(self.super_admin)
        post_data = {
            "name": "Flexible Honor System",
            "engine_type": RuleStrategy.EngineType.STANDARD,
            "pixel_reward": 4,
            "default_unit": "",
            "description": "Updated to 4 pixels reward.",
            "is_active": True,
        }
        resp = self.client.post(reverse("rule_strategy_edit", args=[strat.pk]), post_data)
        self.assertEqual(resp.status_code, 302)

        strat.refresh_from_db()
        self.assertEqual(strat.pixel_reward, 4)

    def test_habit_derives_pixels_from_rule_strategy_not_habit_type(self):
        """
        Habit receives pixels based on the assigned RuleStrategy,
        regardless of whether it is GENERAL, PREDEFINED_PURPOSE, or EXPERT_PRESCRIBED.
        """
        high_effort_strat = RuleStrategy.objects.create(
            name="High Friction Proof",
            engine_type=RuleStrategy.EngineType.EVIDENCE_FILE,
            pixel_reward=8,
        )
        zero_effort_strat = RuleStrategy.objects.create(
            name="Zero Effort Checkoff",
            engine_type=RuleStrategy.EngineType.STANDARD,
            pixel_reward=0,
        )

        # 1. A General habit with High Friction Proof strategy gets 8 Px (not the old 2 Px default)
        h_general = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.regular_user,
            name="Evening Journal Photo",
            habit_type=Habit.HabitType.GENERAL,
            rule_strategy_ref=high_effort_strat,
        )
        self.assertEqual(h_general.pixel_score, 8)

        # 2. A Predefined habit with Zero Effort strategy gets 0 Px (not the old 5 Px default)
        h_predefined = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.super_admin,
            name="Casual Reading Check",
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            rule_strategy_ref=zero_effort_strat,
        )
        self.assertEqual(h_predefined.pixel_score, 0)

    def test_rule_strategy_list_displays_pixel_reward_column(self):
        """RuleStrategy list page renders the allocated pixel reward."""
        RuleStrategy.objects.create(
            name="Gym Location Check",
            engine_type=RuleStrategy.EngineType.STANDARD,
            pixel_reward=6,
        )
        self.client.force_login(self.super_admin)
        resp = self.client.get(reverse("rule_strategy_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pixel Reward")
        self.assertContains(resp, "6 Px")

    def test_updating_rule_strategy_syncs_linked_habits_and_navigation_uses_rule_strategies(self):
        """
        1. Editing pixel_reward on a RuleStrategy updates linked habits automatically.
        2. Admin topbar Master Data dropdown no longer links to separate Pixel Rewards Config page.
        """
        strat = RuleStrategy.objects.create(
            name="Honor Sync Strategy",
            engine_type=RuleStrategy.EngineType.STANDARD,
            pixel_reward=2,
        )
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.regular_user,
            name="Stretch 5 mins",
            rule_strategy_ref=strat,
        )
        self.assertEqual(habit.pixel_score, 2)

        self.client.force_login(self.super_admin)
        resp = self.client.post(reverse("rule_strategy_edit", args=[strat.pk]), {
            "name": strat.name,
            "engine_type": strat.engine_type,
            "pixel_reward": 1,
            "default_unit": "",
            "description": "Adjusted honor reward to 1 Px",
            "is_active": True,
        })
        self.assertEqual(resp.status_code, 302)

        habit.refresh_from_db()
        self.assertEqual(habit.pixel_score, 1)

        # Admin topbar Master Data menu does not expose separate Pixel Rewards Config link
        dash_resp = self.client.get(reverse("habit_list"))
        self.assertEqual(dash_resp.status_code, 200)
        self.assertNotContains(dash_resp, "Pixel Rewards Config")
        self.assertContains(dash_resp, reverse("rule_strategy_list"))
