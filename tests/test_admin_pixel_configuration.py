from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import RolePermission
from habits.forms import HabitForm
from habits.models import Habit, PixelRewardConfig
from habits.services import calculate_user_pixel_wallet
from tenants.models import Membership, Tenant

User = get_user_model()


class AdminPixelRewardConfigurationTests(TestCase):
    """
    Test suite for dynamic Admin Pixel Reward Configuration:
    1. Default configuration returns baseline 2, 5, 10 pixels.
    2. Admin configuration view renders and updates reward rates.
    3. Habit creation and adoption dynamically derive from configured values.
    4. Auto-synchronization updates existing active habits across workspace.
    5. Recalculates Pixel Wallet balances with updated accomplishment rates.
    6. Non-admins cannot access or modify configuration.
    7. Respects Super Admin View Mode switcher.
    """

    def setUp(self):
        self.client = Client()

        # Workspace
        self.tenant = Tenant.objects.create(name="Pixel Config HQ", slug="pixel-config-hq")

        # Super Admin
        self.super_admin = User.objects.create_user(
            username="admin_shrinath",
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

        # Regular User
        self.regular_user = User.objects.create_user(
            username="regular_alex",
            email="alex@habitpulse.com",
            password="UserPassword123!",
            role=User.Role.REGULAR_USER,
        )
        Membership.objects.create(
            tenant=self.tenant,
            user=self.regular_user,
            role="MEMBER",
            status="ACTIVE",
        )

        RolePermission.get_for_role(User.Role.SUPER_ADMIN)
        RolePermission.get_for_role(User.Role.REGULAR_USER)

        self.today = timezone.localdate()

    def test_default_pixel_reward_config(self):
        """
        When no custom configuration exists, defaults are 2 Px (User), 5 Px (Predefined), 10 Px (Expert).
        """
        cfg = PixelRewardConfig.get_config(tenant=self.tenant)
        self.assertEqual(cfg.user_defined_pixels, 2)
        self.assertEqual(cfg.predefined_pixels, 5)
        self.assertEqual(cfg.expert_prescribed_pixels, 10)

    def test_habit_creation_respects_rule_strategy_pixels_not_habit_type(self):
        """
        Habits inherit pixel_score from their RuleStrategy, NOT from habit_type.
        """
        from habits.models import RuleStrategy, seed_default_rule_strategies
        seed_default_rule_strategies()
        honor_strat = RuleStrategy.objects.get(engine_type=RuleStrategy.EngineType.STANDARD)

        # User defined, predefined, and expert all receive Honor System's pixel_reward when linked to Honor System
        for name, h_type in [
            ("Daily Stretching", Habit.HabitType.GENERAL),
            ("Hydration Protocol", Habit.HabitType.PREDEFINED_PURPOSE),
            ("Zone 2 Training", Habit.HabitType.EXPERT_PRESCRIBED),
        ]:
            h = Habit.objects.create(
                tenant=self.tenant,
                created_by=self.super_admin,
                name=name,
                habit_type=h_type,
                rule_strategy_ref=honor_strat,
                frequency=Habit.Frequency.DAILY,
                start_date=self.today,
            )
            self.assertEqual(h.pixel_score, honor_strat.pixel_reward)

    def test_admin_updates_rule_strategy_pixels_and_syncs_existing_habits(self):
        """
        Admin adjusts pixel reward on a RuleStrategy via Master Data edit page.
        Existing linked habits automatically sync to match the new rate, and new habits receive it.
        """
        from habits.models import RuleStrategy
        honor_strat = RuleStrategy.objects.create(
            name="Configurable Honor System",
            engine_type=RuleStrategy.EngineType.STANDARD,
            pixel_reward=2,
        )

        h_user = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.regular_user,
            name="User Routine",
            habit_type=Habit.HabitType.GENERAL,
            rule_strategy_ref=honor_strat,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )
        h_pred = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.super_admin,
            name="Predefined Routine",
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            rule_strategy_ref=honor_strat,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )
        self.assertEqual(h_user.pixel_score, 2)
        self.assertEqual(h_pred.pixel_score, 2)

        # Super admin updates Honor System pixel reward to 4 on Rule Strategy page
        self.client.force_login(self.super_admin)
        resp = self.client.post(reverse("rule_strategy_edit", args=[honor_strat.pk]), {
            "name": honor_strat.name,
            "engine_type": honor_strat.engine_type,
            "pixel_reward": 4,
            "description": "Updated to 4 Px.",
            "is_active": True,
        })
        self.assertEqual(resp.status_code, 302)

        honor_strat.refresh_from_db()
        self.assertEqual(honor_strat.pixel_reward, 4)

        h_user.refresh_from_db()
        h_pred.refresh_from_db()
        self.assertEqual(h_user.pixel_score, 4)
        self.assertEqual(h_pred.pixel_score, 4)

        # Wallet reflects synced 4 Px rate
        wallet = calculate_user_pixel_wallet(self.regular_user, tenant=self.tenant)
        self.assertGreaterEqual(wallet["total_pixels"], 8)  # 4 + 4 = 8 Px daily

    def test_regular_user_cannot_access_pixel_configuration(self):
        """
        Regular users are blocked with 403 PermissionDenied from accessing or posting to configuration.
        """
        self.client.force_login(self.regular_user)
        resp = self.client.get(reverse("admin_pixel_configuration"))
        self.assertEqual(resp.status_code, 403)

        post_resp = self.client.post(reverse("admin_pixel_configuration"), {
            "user_defined_pixels": 99,
            "predefined_pixels": 99,
            "expert_prescribed_pixels": 99,
        })
        self.assertEqual(post_resp.status_code, 403)

    def test_super_admin_view_mode_hides_and_blocks_configuration(self):
        """
        When Super Admin switches to User Preview Mode, admin pixel config is blocked.
        """
        self.client.force_login(self.super_admin)

        # Toggle to user mode
        session = self.client.session
        session["admin_view_mode"] = "user"
        session.save()

        resp = self.client.get(reverse("admin_pixel_configuration"))
        self.assertEqual(resp.status_code, 403)

    def test_general_settings_displays_rule_strategy_pixel_values(self):
        """
        General Settings page reflects dynamic Rule Strategy pixel allocations.
        """
        from habits.models import RuleStrategy
        RuleStrategy.objects.create(
            name="Custom Location Check",
            engine_type=RuleStrategy.EngineType.STANDARD,
            pixel_reward=7,
        )

        self.client.force_login(self.regular_user)
        # Add habit so settings renders habit list
        Habit.objects.create(
            tenant=self.tenant,
            created_by=self.regular_user,
            name="Morning Habit",
            habit_type=Habit.HabitType.GENERAL,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )

        resp = self.client.get(reverse("general_settings"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "By Rule Strategy")
        self.assertContains(resp, "Custom Location Check")
        self.assertContains(resp, "7 Pixels")

