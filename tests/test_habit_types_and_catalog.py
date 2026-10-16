from datetime import time
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import RolePermission
from habits.models import Habit, HabitCompletion
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class HabitTypesAndCatalogTestCase(TestCase):
    """
    Test suite for:
    1. Three distinct habit types: GENERAL, PREDEFINED_PURPOSE, EXPERT_PRESCRIBED.
    2. Three distinct sections rendered on the Habits hub:
       - My Habit List
       - Predefined Purpose Habits
       - Expert Prescribed Habits
    3. Creation & publishing of catalog templates by Super Admin & Technical Users.
    4. Regular users restricted to General habits defaulting to Honor System (STANDARD).
    5. Adoption of catalog templates by regular users into their workspace.
    6. Strict validation parameter enforcement on adopted habits prior to completion.
    7. Catalog template permissions (admin/technical only).
    """

    def setUp(self):
        # 1. Super Admin User
        self.super_admin = User.objects.create_user(
            username="super_admin_test",
            email="superadmin@example.com",
            password="AdminPassword123!",
            is_staff=True,
            is_superuser=True,
        )
        self.super_admin_tenant, _ = create_personal_workspace_for_user(self.super_admin, "Super Admin Space")

        # 2. Technical User
        self.technical_user = User.objects.create_user(
            username="tech_user_test",
            email="tech@example.com",
            password="TechPassword123!",
            role=User.Role.TECHNICAL_USER,
        )
        self.tech_tenant, _ = create_personal_workspace_for_user(self.technical_user, "Tech Space")

        # 3. Regular User
        self.regular_user = User.objects.create_user(
            username="reg_user_test",
            email="regular@example.com",
            password="RegPassword123!",
            role=User.Role.REGULAR_USER,
        )
        self.reg_tenant, _ = create_personal_workspace_for_user(self.regular_user, "Reg Space")

        # Ensure RolePermission defaults are present
        RolePermission.get_for_role(User.Role.SUPER_ADMIN)
        RolePermission.get_for_role(User.Role.TECHNICAL_USER)
        RolePermission.get_for_role(User.Role.REGULAR_USER)

        self.client_regular = Client()
        self.client_regular.login(username="reg_user_test", password="RegPassword123!")

        self.client_admin = Client()
        self.client_admin.login(username="super_admin_test", password="AdminPassword123!")

        self.client_tech = Client()
        self.client_tech.login(username="tech_user_test", password="TechPassword123!")

        self.today = timezone.localdate()

    def test_habit_list_page_displays_three_separate_sections(self):
        """
        GET /habits/ must render:
        1. My Habit List (#my-habits)
        2. Predefined Purpose Habits (#predefined-habits)
        3. Expert Prescribed Habits (#expert-habits)
        """
        response = self.client_regular.get(reverse("habit_list"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("My Habit List", content)
        self.assertIn("Predefined Purpose Habits", content)
        self.assertIn("Expert Prescribed Habits", content)

        self.assertIn('id="my-habits"', content)
        self.assertIn('id="predefined-habits"', content)
        self.assertIn('id="expert-habits"', content)

        # Default catalog habits seeded automatically
        self.assertTrue(Habit.objects.filter(is_template=True, habit_type=Habit.HabitType.PREDEFINED_PURPOSE).exists())
        self.assertTrue(Habit.objects.filter(is_template=True, habit_type=Habit.HabitType.EXPERT_PRESCRIBED).exists())

    def test_regular_user_creates_general_habit_defaults_to_honor_system(self):
        """
        Regular users create GENERAL habits defaulting to Honor System (STANDARD).
        Even if they attempt to post template=True or a different habit type, it is restricted.
        """
        # Valid creation by regular user
        response = self.client_regular.post(reverse("habit_create"), {
            "name": "Evening Journaling",
            "description": "Reflect on 3 wins today",
            "category": "Mindfulness",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)

        created_habit = Habit.objects.get(tenant=self.reg_tenant, name="Evening Journaling")
        self.assertEqual(created_habit.habit_type, Habit.HabitType.GENERAL)
        self.assertFalse(created_habit.is_template)
        self.assertEqual(created_habit.validation_rule, Habit.ValidationRule.STANDARD)
        self.assertTrue(created_habit.is_general)

        # Tampering attempt with unauthorized habit_type
        response_tamper = self.client_regular.post(reverse("habit_create"), {
            "name": "Unauthorized Template",
            "description": "Hacking the system",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "habit_type": Habit.HabitType.EXPERT_PRESCRIBED,
            "is_template": "on",
        })
        # Should stay on form with validation error or reject choice
        self.assertFalse(Habit.objects.filter(name="Unauthorized Template").exists())

    def test_super_admin_can_publish_predefined_purposeful_habit_template(self):
        """
        Super admin can create and publish a Predefined Purposeful habit template with validation rules.
        """
        response = self.client_admin.post(reverse("habit_create"), {
            "name": "Super Hydration Target",
            "description": "Drink at least 3000 ml water daily",
            "category": "Health",
            "habit_type": Habit.HabitType.PREDEFINED_PURPOSE,
            "is_template": "on",
            "validation_rule": Habit.ValidationRule.NUMERIC_TARGET,
            "target_value": "3000",
            "unit_label": "ml",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("habit_list"))

        template = Habit.objects.get(name="Super Hydration Target", is_template=True)
        self.assertEqual(template.habit_type, Habit.HabitType.PREDEFINED_PURPOSE)
        self.assertEqual(template.validation_rule, Habit.ValidationRule.NUMERIC_TARGET)
        self.assertEqual(template.target_value, Decimal("3000"))
        self.assertEqual(template.unit_label, "ml")
        self.assertTrue(template.is_predefined_purpose)

    def test_technical_user_can_publish_expert_prescribed_habit_template(self):
        """
        Technical user can create and publish an Expert Prescribed habit template with time window.
        """
        response = self.client_tech.post(reverse("habit_create"), {
            "name": "Morning Cold Exposure",
            "description": "Protocol: 3-5 minutes cold shower between 6:00 and 8:30 AM",
            "category": "Health",
            "habit_type": Habit.HabitType.EXPERT_PRESCRIBED,
            "is_template": "on",
            "validation_rule": Habit.ValidationRule.TIME_WINDOW,
            "window_start_time": "06:00:00",
            "window_end_time": "08:30:00",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("habit_list"))

        template = Habit.objects.get(name="Morning Cold Exposure", is_template=True)
        self.assertEqual(template.habit_type, Habit.HabitType.EXPERT_PRESCRIBED)
        self.assertEqual(template.validation_rule, Habit.ValidationRule.TIME_WINDOW)
        self.assertEqual(template.window_start_time, time(6, 0))
        self.assertEqual(template.window_end_time, time(8, 30))
        self.assertTrue(template.is_expert_prescribed)

    def test_regular_user_adopts_template_habit(self):
        """
        Regular user can add a catalog template habit to their habit list.
        It is cloned into their workspace with all validation parameters preserved.
        """
        template = Habit.objects.create(
            name="Deep Work Focus 90m",
            description="90 minutes uninterrupted single-tasking",
            category="Productivity",
            created_by=self.super_admin,
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            is_template=True,
            validation_rule=Habit.ValidationRule.NUMERIC_TARGET,
            target_value=Decimal("90"),
            unit_label="minutes",
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )

        adopt_url = reverse("habit_adopt", args=[template.pk])
        response = self.client_regular.post(adopt_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("habit_list"))

        # Verify cloned habit in user's tenant
        adopted = Habit.objects.filter(tenant=self.reg_tenant, template_source=template).first()
        self.assertIsNotNone(adopted)
        self.assertEqual(adopted.name, "Deep Work Focus 90m")
        self.assertEqual(adopted.habit_type, Habit.HabitType.PREDEFINED_PURPOSE)
        self.assertFalse(adopted.is_template)
        self.assertEqual(adopted.validation_rule, Habit.ValidationRule.NUMERIC_TARGET)
        self.assertEqual(adopted.target_value, Decimal("90"))
        self.assertEqual(adopted.unit_label, "minutes")

        # Attempting to adopt a second time does not create a duplicate
        response2 = self.client_regular.post(adopt_url)
        self.assertEqual(response2.status_code, 302)
        count = Habit.objects.filter(tenant=self.reg_tenant, template_source=template).count()
        self.assertEqual(count, 1)

    def test_adopted_predefined_habit_enforces_numeric_validation_parameter(self):
        """
        Predefined Purposeful Habit with a target requires fulfillment before marking complete.
        """
        template = Habit.objects.create(
            name="Daily Steps Target",
            category="Fitness",
            created_by=self.super_admin,
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            is_template=True,
            validation_rule=Habit.ValidationRule.NUMERIC_TARGET,
            target_value=Decimal("8000"),
            unit_label="steps",
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )

        # Adopt habit
        self.client_regular.post(reverse("habit_adopt", args=[template.pk]))
        adopted = Habit.objects.get(tenant=self.reg_tenant, template_source=template)

        complete_url = reverse("habit_complete", args=[adopted.pk])

        # Attempt 1: Complete with no logged value -> rejected
        resp_fail1 = self.client_regular.post(complete_url, {})
        self.assertEqual(resp_fail1.status_code, 302)
        self.assertFalse(HabitCompletion.objects.filter(habit=adopted, completion_date=self.today).exists())

        # Attempt 2: Complete with logged value 5000 (< 8000) -> rejected
        resp_fail2 = self.client_regular.post(complete_url, {"logged_value": "5000"})
        self.assertEqual(resp_fail2.status_code, 302)
        self.assertFalse(HabitCompletion.objects.filter(habit=adopted, completion_date=self.today).exists())

        # Attempt 3: Complete with logged value 8500 (>= 8000) -> accepted
        resp_success = self.client_regular.post(complete_url, {"logged_value": "8500"})
        self.assertEqual(resp_success.status_code, 302)
        completion = HabitCompletion.objects.filter(habit=adopted, completion_date=self.today).first()
        self.assertIsNotNone(completion)
        self.assertEqual(completion.logged_value, Decimal("8500"))

    def test_adopted_expert_prescribed_habit_enforces_time_window_validation(self):
        """
        Expert Prescribed Habit with a time window rejects completions outside the prescribed window.
        """
        template = Habit.objects.create(
            name="Circadian Dawn Sunlight",
            category="Health",
            created_by=self.super_admin,
            habit_type=Habit.HabitType.EXPERT_PRESCRIBED,
            is_template=True,
            validation_rule=Habit.ValidationRule.TIME_WINDOW,
            window_start_time=time(6, 0),
            window_end_time=time(9, 0),
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )

        # Adopt habit
        self.client_regular.post(reverse("habit_adopt", args=[template.pk]))
        adopted = Habit.objects.get(tenant=self.reg_tenant, template_source=template)
        complete_url = reverse("habit_complete", args=[adopted.pk])

        # Case A: User attempts completion at 14:30 (outside window) -> rejected
        outside_window_dt = timezone.make_aware(timezone.datetime(self.today.year, self.today.month, self.today.day, 14, 30, 0))
        with patch("habits.validators.timezone.now", return_value=outside_window_dt):
            with patch("habits.validators.timezone.localtime", return_value=outside_window_dt):
                resp = self.client_regular.post(complete_url, {})
                self.assertEqual(resp.status_code, 302)
                self.assertFalse(HabitCompletion.objects.filter(habit=adopted, completion_date=self.today).exists())

        # Case B: User attempts completion at 07:30 (inside window) -> accepted
        inside_window_dt = timezone.make_aware(timezone.datetime(self.today.year, self.today.month, self.today.day, 7, 30, 0))
        with patch("habits.validators.timezone.now", return_value=inside_window_dt):
            with patch("habits.validators.timezone.localtime", return_value=inside_window_dt):
                resp = self.client_regular.post(complete_url, {})
                self.assertEqual(resp.status_code, 302)
                self.assertTrue(HabitCompletion.objects.filter(habit=adopted, completion_date=self.today).exists())

    def test_template_catalog_permission_boundaries(self):
        """
        Regular users cannot edit or delete catalog templates.
        Super Admin and Technical users can manage templates.
        """
        template = Habit.objects.create(
            name="Restricted Catalog Item",
            category="Health",
            created_by=self.super_admin,
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            is_template=True,
            start_date=self.today,
        )

        # Regular user tries to delete template -> 403 Forbidden
        del_resp = self.client_regular.post(reverse("habit_delete", args=[template.pk]))
        self.assertEqual(del_resp.status_code, 403)
        self.assertTrue(Habit.objects.filter(pk=template.pk).exists())

        # Regular user tries to update template -> 403 Forbidden
        update_resp = self.client_regular.post(reverse("habit_edit", args=[template.pk]), {
            "name": "Hacked Name",
        })
        self.assertEqual(update_resp.status_code, 403)

        # Technical user can edit template
        tech_resp = self.client_tech.post(reverse("habit_edit", args=[template.pk]), {
            "name": "Updated by Tech User",
            "category": "Health",
            "habit_type": Habit.HabitType.PREDEFINED_PURPOSE,
            "is_template": "on",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(tech_resp.status_code, 302)
        template.refresh_from_db()
        self.assertEqual(template.name, "Updated by Tech User")

        # Super admin can delete template
        admin_del_resp = self.client_admin.post(reverse("habit_delete", args=[template.pk]))
        self.assertEqual(admin_del_resp.status_code, 302)
        self.assertFalse(Habit.objects.filter(pk=template.pk).exists())
