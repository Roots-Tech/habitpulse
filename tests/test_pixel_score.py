from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import RolePermission
from habits.models import Habit, RuleStrategy, seed_default_rule_strategies
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class PixelScoreTestCase(TestCase):
    """
    Test suite for Rule-Strategy-Based Pixel Score Allocation:
    1. Pixel awards are governed by the linked RuleStrategy, NOT by habit_type.
    2. Newly created RuleStrategies default to 0 Px when no allocation is specified.
    3. Regular users cannot tamper with pixel_score during POST; habits receive their RuleStrategy's pixel_reward.
    4. Admins publishing Predefined/Expert templates receive their linked RuleStrategy's pixel_reward.
    5. Adopting a catalog template preserves the template's RuleStrategy pixel allocation.
    6. Habits homepage (/habits/) displays the Rule Strategy Pixel Allocation overview (#pixel-score-section).
    """

    def setUp(self):
        seed_default_rule_strategies()

        # 1. Super Admin
        self.super_admin = User.objects.create_user(
            username="admin_pixel",
            email="admin_pixel@example.com",
            password="AdminPassword123!",
            is_staff=True,
            is_superuser=True,
        )
        self.admin_tenant, _ = create_personal_workspace_for_user(self.super_admin, "Admin Space")

        # 2. Regular User
        self.regular_user = User.objects.create_user(
            username="regular_pixel",
            email="regular_pixel@example.com",
            password="RegularPassword123!",
            role=User.Role.REGULAR_USER,
        )
        self.reg_tenant, _ = create_personal_workspace_for_user(self.regular_user, "Reg Space")

        RolePermission.get_for_role(User.Role.SUPER_ADMIN)
        RolePermission.get_for_role(User.Role.REGULAR_USER)

        self.client_admin = Client()
        self.client_admin.login(username="admin_pixel", password="AdminPassword123!")

        self.client_regular = Client()
        self.client_regular.login(username="regular_pixel", password="RegularPassword123!")

        self.today = timezone.localdate()

    def test_model_level_rule_strategy_governs_habit_pixels(self):
        """
        Model level: Habits of any habit_type derive their pixel_score from rule_strategy_ref.pixel_reward.
        """
        honor_strat = RuleStrategy.objects.get(engine_type=RuleStrategy.EngineType.STANDARD)
        custom_zero = RuleStrategy.objects.create(
            name="Unrewarded Strategy",
            engine_type=RuleStrategy.EngineType.STANDARD,
        )
        self.assertEqual(custom_zero.pixel_reward, 0)

        habit = Habit.objects.create(
            tenant=self.reg_tenant,
            created_by=self.regular_user,
            name="Morning Water",
            habit_type=Habit.HabitType.GENERAL,
            rule_strategy_ref=honor_strat,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )
        self.assertEqual(habit.pixel_score, honor_strat.pixel_reward)
        self.assertEqual(habit.pixel_badge["score"], honor_strat.pixel_reward)

        # Negative pixel scores raise ValidationError in clean()
        habit.pixel_score = -5
        with self.assertRaises(ValidationError):
            habit.clean()

        # Re-saving resets to linked RuleStrategy pixel_reward
        habit.rule_strategy_ref = custom_zero
        habit.save()
        habit.refresh_from_db()
        self.assertEqual(habit.pixel_score, 0)

    def test_habit_type_does_not_override_rule_strategy_pixels(self):
        """
        GENERAL, PREDEFINED_PURPOSE, and EXPERT_PRESCRIBED all use their RuleStrategy's pixel_reward
        rather than fixed 2/5/10 habit-type rates.
        """
        strat_six = RuleStrategy.objects.create(
            name="Six Pixel Protocol",
            engine_type=RuleStrategy.EngineType.STANDARD,
            pixel_reward=6,
        )
        strat_zero = RuleStrategy.objects.create(
            name="Zero Pixel Check",
            engine_type=RuleStrategy.EngineType.STANDARD,
            pixel_reward=0,
        )

        h_general = Habit.objects.create(
            tenant=self.reg_tenant,
            created_by=self.regular_user,
            name="General Six Px",
            habit_type=Habit.HabitType.GENERAL,
            rule_strategy_ref=strat_six,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )
        h_pred = Habit.objects.create(
            tenant=self.admin_tenant,
            created_by=self.super_admin,
            name="Predefined Zero Px",
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            rule_strategy_ref=strat_zero,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
            is_template=True,
        )
        h_expert = Habit.objects.create(
            tenant=self.admin_tenant,
            created_by=self.super_admin,
            name="Expert Six Px",
            habit_type=Habit.HabitType.EXPERT_PRESCRIBED,
            rule_strategy_ref=strat_six,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
            is_template=True,
        )

        self.assertEqual(h_general.pixel_score, 6)
        self.assertEqual(h_pred.pixel_score, 0)
        self.assertEqual(h_expert.pixel_score, 6)

    def test_regular_user_form_creation_uses_selected_rule_strategy_and_blocks_tampering(self):
        """
        When a regular user creates a habit via POST, injected pixel_score values are ignored
        and the habit receives its selected RuleStrategy's pixel_reward.
        """
        proof_strat = RuleStrategy.objects.get(engine_type=RuleStrategy.EngineType.EVIDENCE_FILE)
        response = self.client_regular.post(reverse("habit_create"), {
            "name": "Evening Stretching",
            "category": "Health",
            "rule_strategy_ref": proof_strat.pk,
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "pixel_score": "50",  # Injected tamper attempt
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)

        created = Habit.objects.get(tenant=self.reg_tenant, name="Evening Stretching")
        self.assertEqual(created.habit_type, Habit.HabitType.GENERAL)
        self.assertEqual(created.rule_strategy_ref, proof_strat)
        self.assertEqual(created.pixel_score, proof_strat.pixel_reward)

    def test_admin_can_publish_predefined_habit_deriving_rule_strategy_pixels(self):
        """
        Admin publishing a Predefined Purpose habit receives the selected RuleStrategy's pixel_reward.
        """
        strat = RuleStrategy.objects.create(
            name="Hydration Proof Rule",
            engine_type=RuleStrategy.EngineType.EVIDENCE_FILE,
            pixel_reward=6,
        )
        response = self.client_admin.post(reverse("habit_create"), {
            "name": "Hydration Sprint",
            "description": "Drink 2.5L water",
            "category": "Health",
            "habit_type": Habit.HabitType.PREDEFINED_PURPOSE,
            "rule_strategy_ref": strat.pk,
            "is_template": "on",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)

        template = Habit.objects.get(name="Hydration Sprint", is_template=True)
        self.assertEqual(template.pixel_score, 6)

    def test_admin_can_publish_expert_prescribed_habit_deriving_rule_strategy_pixels(self):
        """
        Admin publishing an Expert Prescribed habit receives the selected RuleStrategy's pixel_reward.
        """
        strat = RuleStrategy.objects.create(
            name="Clinical High Verification",
            engine_type=RuleStrategy.EngineType.EVIDENCE_FILE,
            pixel_reward=14,
        )
        response = self.client_admin.post(reverse("habit_create"), {
            "name": "Clinical Cold Immersion",
            "description": "3 mins cold exposure",
            "category": "Health",
            "habit_type": Habit.HabitType.EXPERT_PRESCRIBED,
            "rule_strategy_ref": strat.pk,
            "is_template": "on",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)

        template = Habit.objects.get(name="Clinical Cold Immersion", is_template=True)
        self.assertEqual(template.pixel_score, 14)

    def test_template_adoption_preserves_rule_strategy_pixel_score(self):
        """
        When a regular user adopts a template from the catalog, the cloned habit in their
        personal workspace inherits the template's RuleStrategy and its pixel score.
        """
        strat = RuleStrategy.objects.create(
            name="Zone 2 Proof Strategy",
            engine_type=RuleStrategy.EngineType.EVIDENCE_FILE,
            pixel_reward=12,
        )
        template = Habit.objects.create(
            tenant=self.admin_tenant,
            created_by=self.super_admin,
            name="Cardio Zone 2 Protocol",
            habit_type=Habit.HabitType.EXPERT_PRESCRIBED,
            rule_strategy_ref=strat,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
            is_template=True,
        )

        adopt_url = reverse("habit_adopt", args=[template.pk])
        response = self.client_regular.post(adopt_url)
        self.assertEqual(response.status_code, 302)

        adopted = Habit.objects.filter(tenant=self.reg_tenant, template_source=template).first()
        self.assertIsNotNone(adopted)
        self.assertEqual(adopted.rule_strategy_ref, strat)
        self.assertEqual(adopted.pixel_score, 12)

    def test_ui_renders_pixel_score_section_and_badges(self):
        """
        Verifies:
        1. Habits homepage (/habits/) displays the Rule Strategy Pixel Score Allocation section (#pixel-score-section).
        2. Habit creation form renders id_rule_strategy_ref and NOT #pixel-score-section.
        3. Habit cards in habit list and dashboard render pixel score badges.
        """
        honor_strat = RuleStrategy.objects.get(engine_type=RuleStrategy.EngineType.STANDARD)

        # Habits Homepage (habit_list) renders Rule Strategy Pixel Allocation overview
        response_list = self.client_regular.get(reverse("habit_list"))
        self.assertEqual(response_list.status_code, 200)
        content_list = response_list.content.decode("utf-8")
        self.assertIn("Pixel Score Allocation (By Rule Strategy)", content_list)
        self.assertIn('id="pixel-score-section"', content_list)
        self.assertIn(honor_strat.name, content_list)
        self.assertIn(f"{honor_strat.pixel_reward} Px", content_list)

        # Habit form renders Rule Strategy select field and not #pixel-score-section
        response_form = self.client_regular.get(reverse("habit_create"))
        self.assertEqual(response_form.status_code, 200)
        content_form = response_form.content.decode("utf-8")
        self.assertNotIn('id="pixel-score-section"', content_form)
        self.assertIn('id="id_rule_strategy_ref"', content_form)

        # Create a habit and check habit list & dashboard badges
        Habit.objects.create(
            tenant=self.reg_tenant,
            created_by=self.regular_user,
            name="Daily Code Kata",
            habit_type=Habit.HabitType.GENERAL,
            rule_strategy_ref=honor_strat,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
            is_active=True,
        )

        response_list_with_habit = self.client_regular.get(reverse("habit_list"))
        self.assertEqual(response_list_with_habit.status_code, 200)
        self.assertIn(f"{honor_strat.pixel_reward} Pixels", response_list_with_habit.content.decode("utf-8"))

        response_dash = self.client_regular.get(reverse("dashboard"))
        self.assertEqual(response_dash.status_code, 200)
        self.assertIn(f"{honor_strat.pixel_reward} Pixels", response_dash.content.decode("utf-8"))
