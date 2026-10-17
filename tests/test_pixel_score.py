from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import RolePermission
from habits.forms import HabitForm
from habits.models import Habit
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class PixelScoreTestCase(TestCase):
    """
    Test suite for Habit Pixel Score Allocation:
    1. USER_CREATED (GENERAL) habits are fixed at 2 pixel score.
    2. PREDEFINED_PURPOSE habits default to 5 pixel score and can be modified to any amount.
    3. EXPERT_PRESCRIBED habits default to 10 pixel score and can be modified to any amount.
    4. Adopting a catalog template into a personal workspace preserves its allotted pixel score.
    5. Habit creation forms and views display the allocated pixel score clearly.
    """

    def setUp(self):
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

    def test_model_level_user_created_habit_fixed_at_two(self):
        """
        Model level: A GENERAL habit created without specifying pixel_score defaults to 2.
        Even if an attempt is made to set another value, it is strictly enforced as 2.
        """
        habit = Habit.objects.create(
            tenant=self.reg_tenant,
            created_by=self.regular_user,
            name="Morning Water",
            habit_type=Habit.HabitType.GENERAL,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )
        self.assertEqual(habit.pixel_score, 2)
        self.assertEqual(habit.pixel_badge["score"], 2)

        # Attempt to bypass in model clean
        habit.pixel_score = 99
        with self.assertRaises(ValidationError):
            habit.clean()

        # Save automatically resets it to 2
        habit.save()
        habit.refresh_from_db()
        self.assertEqual(habit.pixel_score, 2)

    def test_model_level_predefined_purpose_defaults_to_five_and_allows_custom(self):
        """
        Model level: PREDEFINED_PURPOSE habits default to 5, and can be customized to any amount.
        """
        # Default
        habit_default = Habit.objects.create(
            tenant=self.admin_tenant,
            created_by=self.super_admin,
            name="Deep Focus Block",
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
            is_template=True,
        )
        self.assertEqual(habit_default.pixel_score, 5)

        # Custom score (e.g. 8)
        habit_custom = Habit.objects.create(
            tenant=self.admin_tenant,
            created_by=self.super_admin,
            name="Ultra Focus Sprint",
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            pixel_score=8,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
            is_template=True,
        )
        self.assertEqual(habit_custom.pixel_score, 8)

    def test_model_level_expert_prescribed_defaults_to_ten_and_allows_custom(self):
        """
        Model level: EXPERT_PRESCRIBED habits default to 10, and can be customized to any amount.
        """
        # Default
        habit_default = Habit.objects.create(
            tenant=self.admin_tenant,
            created_by=self.super_admin,
            name="Circadian Light Routine",
            habit_type=Habit.HabitType.EXPERT_PRESCRIBED,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
            is_template=True,
        )
        self.assertEqual(habit_default.pixel_score, 10)

        # Custom score (e.g. 15)
        habit_custom = Habit.objects.create(
            tenant=self.admin_tenant,
            created_by=self.super_admin,
            name="High Intensity VO2 Max",
            habit_type=Habit.HabitType.EXPERT_PRESCRIBED,
            pixel_score=15,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
            is_template=True,
        )
        self.assertEqual(habit_custom.pixel_score, 15)

    def test_regular_user_form_creation_enforces_fixed_score_two(self):
        """
        When a regular user creates a personal habit through POST, pixel_score is 2,
        even if an attacker attempts to inject a different pixel_score in the POST data.
        """
        response = self.client_regular.post(reverse("habit_create"), {
            "name": "Evening Stretching",
            "category": "Health",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "pixel_score": "50",  # Injected tamper attempt
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)

        created = Habit.objects.get(tenant=self.reg_tenant, name="Evening Stretching")
        self.assertEqual(created.habit_type, Habit.HabitType.GENERAL)
        self.assertEqual(created.pixel_score, 2)

    def test_admin_can_publish_predefined_habit_with_custom_pixel_score(self):
        """
        Admin can publish a Predefined Purpose habit with a custom pixel score (e.g. 6).
        """
        response = self.client_admin.post(reverse("habit_create"), {
            "name": "Hydration Sprint",
            "description": "Drink 2.5L water",
            "category": "Health",
            "habit_type": Habit.HabitType.PREDEFINED_PURPOSE,
            "is_template": "on",
            "pixel_score": "6",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)

        template = Habit.objects.get(name="Hydration Sprint", is_template=True)
        self.assertEqual(template.pixel_score, 6)

    def test_admin_can_publish_expert_prescribed_habit_with_custom_pixel_score(self):
        """
        Admin can publish an Expert Prescribed habit with a custom pixel score (e.g. 14).
        """
        response = self.client_admin.post(reverse("habit_create"), {
            "name": "Clinical Cold Immersion",
            "description": "3 mins cold exposure",
            "category": "Health",
            "habit_type": Habit.HabitType.EXPERT_PRESCRIBED,
            "is_template": "on",
            "pixel_score": "14",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)

        template = Habit.objects.get(name="Clinical Cold Immersion", is_template=True)
        self.assertEqual(template.pixel_score, 14)

    def test_template_adoption_preserves_allotted_pixel_score(self):
        """
        When a regular user adopts a template from the catalog, the cloned habit in their
        personal workspace inherits the exact pixel score allotted to that template.
        """
        template = Habit.objects.create(
            tenant=self.admin_tenant,
            created_by=self.super_admin,
            name="Cardio Zone 2 Protocol",
            habit_type=Habit.HabitType.EXPERT_PRESCRIBED,
            pixel_score=12,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
            is_template=True,
        )

        adopt_url = reverse("habit_adopt", args=[template.pk])
        response = self.client_regular.post(adopt_url)
        self.assertEqual(response.status_code, 302)

        adopted = Habit.objects.filter(tenant=self.reg_tenant, template_source=template).first()
        self.assertIsNotNone(adopted)
        self.assertEqual(adopted.pixel_score, 12)

    def test_ui_renders_pixel_score_section_and_badges(self):
        """
        Verifies:
        1. Habits homepage (/habits/) displays the common Pixel Score Allocation section (#pixel-score-section).
        2. Habit creation form does NOT render the section (it is common on habits homepage).
        3. Habit cards in habit list and dashboard render pixel score badges.
        """
        # Habits Homepage (habit_list) renders common Pixel Score Allocation section
        response_list = self.client_regular.get(reverse("habit_list"))
        self.assertEqual(response_list.status_code, 200)
        content_list = response_list.content.decode("utf-8")
        self.assertIn("Pixel Score Allocation", content_list)
        self.assertIn('id="pixel-score-section"', content_list)
        self.assertIn("2 Pixels Allotted", content_list)
        self.assertIn("5 Pixels Allotted", content_list)
        self.assertIn("10 Pixels Allotted", content_list)
        self.assertIn("User Created Habits", content_list)
        self.assertIn("Predefined Purpose Habits", content_list)
        self.assertIn("Expert Prescribed Habits", content_list)

        # Habit form does not render the section within the habit
        response_form = self.client_regular.get(reverse("habit_create"))
        self.assertEqual(response_form.status_code, 200)
        content_form = response_form.content.decode("utf-8")
        self.assertNotIn('id="pixel-score-section"', content_form)

        # Create a habit and check habit list & dashboard badges
        habit = Habit.objects.create(
            tenant=self.reg_tenant,
            created_by=self.regular_user,
            name="Daily Code Kata",
            habit_type=Habit.HabitType.GENERAL,
            pixel_score=2,
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
            is_active=True,
        )

        response_list_with_habit = self.client_regular.get(reverse("habit_list"))
        self.assertEqual(response_list_with_habit.status_code, 200)
        self.assertIn("2 Pixels", response_list_with_habit.content.decode("utf-8"))

        response_dash = self.client_regular.get(reverse("dashboard"))
        self.assertEqual(response_dash.status_code, 200)
        self.assertIn("2 Pixels", response_dash.content.decode("utf-8"))
